"""DB Config module: relational-style services / instances / metadata backed by Mongo.

Mirrors the SQL schema:
  db_services(id, service_name UNIQUE)
  db_instances(id, service_id FK, instance_name, host, port, instance_type,
               aws_instance_id UNIQUE, all_dns, srv_record, aws_region,
               environment ENUM, status ENUM, created_at, updated_at)
  db_instance_metadata(id, instance_id FK, attribute_key, attribute_value,
                       UNIQUE(instance_id, attribute_key))  -- embedded here
"""
import io
import os
import csv
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Literal

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict
import openpyxl

from auth import get_current_user, require_admin

_db = None
ENVIRONMENTS = ["DEV", "QA", "UAT", "DR", "PROD"]
STATUSES = ["Running", "Stopped", "Terminated"]
KNOWN_COLS = {
    "service_name", "instance_name", "host", "port", "instance_type",
    "aws_instance_id", "all_dns", "srv_record", "aws_region",
    "environment", "status",
}


def init(db):
    global _db
    _db = db


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def _next_seq(name: str) -> int:
    doc = await _db.db_counters.find_one_and_update(
        {"_id": name}, {"$inc": {"seq": 1}}, upsert=True, return_document=True
    )
    return doc["seq"]


# ----------------------------- models -----------------------------
class MetaItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    attribute_key: str
    attribute_value: str = ""


class ServiceCreate(BaseModel):
    service_name: str


class InstanceBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    service_id: str
    instance_name: str
    host: str = ""
    port: Optional[int] = None
    instance_type: str = ""
    aws_instance_id: str = ""
    all_dns: str = ""
    srv_record: str = ""
    aws_region: str = ""
    environment: Literal["DEV", "QA", "UAT", "DR", "PROD"] = "DEV"
    status: Literal["Running", "Stopped", "Terminated"] = "Running"
    metadata: List[MetaItem] = Field(default_factory=list)


# ----------------------------- helpers -----------------------------
def _dedup_meta(items):
    seen, out = set(), []
    for m in items:
        k = m["attribute_key"] if isinstance(m, dict) else m.attribute_key
        v = m["attribute_value"] if isinstance(m, dict) else m.attribute_value
        k = (k or "").strip()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append({"attribute_key": k, "attribute_value": v})
    return out


async def _assert_unique_awsid(aws_id, exclude_id=None):
    aws_id = (aws_id or "").strip()
    if not aws_id:
        return
    q = {"aws_instance_id": aws_id}
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    if await _db.db_instances.find_one(q):
        raise HTTPException(status_code=409, detail=f"aws_instance_id '{aws_id}' already exists")


# ----------------------------- router -----------------------------
router = APIRouter(prefix="/api/db", dependencies=[Depends(get_current_user)])


# --- services ---
@router.get("/services")
async def list_services():
    docs = await _db.db_services.find({}, {"_id": 0}).sort("seq", 1).to_list(2000)
    for d in docs:
        d["instance_count"] = await _db.db_instances.count_documents({"service_id": d["id"]})
    return docs


@router.post("/services")
async def create_service(payload: ServiceCreate):
    name = payload.service_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="service_name required")
    if await _db.db_services.find_one({"service_name": name}):
        raise HTTPException(status_code=409, detail="service_name already exists")
    doc = {"id": str(uuid.uuid4()), "seq": await _next_seq("services"), "service_name": name}
    await _db.db_services.insert_one(dict(doc))
    return doc


@router.put("/services/{service_id}")
async def update_service(service_id: str, payload: ServiceCreate):
    name = payload.service_name.strip()
    existing = await _db.db_services.find_one({"id": service_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Service not found")
    dup = await _db.db_services.find_one({"service_name": name, "id": {"$ne": service_id}})
    if dup:
        raise HTTPException(status_code=409, detail="service_name already exists")
    await _db.db_services.update_one({"id": service_id}, {"$set": {"service_name": name}})
    return {"id": service_id, "seq": existing["seq"], "service_name": name}


@router.delete("/services/{service_id}")
async def delete_service(service_id: str, current=Depends(require_admin)):
    count = await _db.db_instances.count_documents({"service_id": service_id})
    if count:
        raise HTTPException(status_code=409, detail=f"Service has {count} instance(s); delete them first")
    res = await _db.db_services.delete_one({"id": service_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Service not found")
    return {"deleted": True}


# --- instances ---
@router.get("/instances")
async def list_instances(service_id: Optional[str] = None, search: Optional[str] = None):
    query = {}
    if service_id:
        query["service_id"] = service_id
    if search:
        rx = {"$regex": search, "$options": "i"}
        query["$or"] = [{"instance_name": rx}, {"host": rx}, {"aws_instance_id": rx},
                        {"all_dns": rx}, {"aws_region": rx}]
    docs = await _db.db_instances.find(query, {"_id": 0}).sort("seq", 1).to_list(5000)
    svc = {s["id"]: s["service_name"] async for s in _db.db_services.find({}, {"_id": 0})}
    for d in docs:
        d["service_name"] = svc.get(d.get("service_id"), "")
    return docs


@router.post("/instances")
async def create_instance(payload: InstanceBase):
    if not await _db.db_services.find_one({"id": payload.service_id}):
        raise HTTPException(status_code=400, detail="Invalid service_id")
    await _assert_unique_awsid(payload.aws_instance_id)
    data = payload.model_dump()
    data["metadata"] = _dedup_meta(data.get("metadata", []))
    data["id"] = str(uuid.uuid4())
    data["seq"] = await _next_seq("instances")
    data["created_at"] = now_iso()
    data["updated_at"] = now_iso()
    await _db.db_instances.insert_one(dict(data))
    data.pop("_id", None)
    return data


@router.put("/instances/{instance_id}")
async def update_instance(instance_id: str, payload: InstanceBase):
    existing = await _db.db_instances.find_one({"id": instance_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Instance not found")
    if not await _db.db_services.find_one({"id": payload.service_id}):
        raise HTTPException(status_code=400, detail="Invalid service_id")
    await _assert_unique_awsid(payload.aws_instance_id, exclude_id=instance_id)
    data = payload.model_dump()
    data["metadata"] = _dedup_meta(data.get("metadata", []))
    data["updated_at"] = now_iso()
    await _db.db_instances.update_one({"id": instance_id}, {"$set": data})
    return await _db.db_instances.find_one({"id": instance_id}, {"_id": 0})


@router.delete("/instances/{instance_id}")
async def delete_instance(instance_id: str, current=Depends(require_admin)):
    res = await _db.db_instances.delete_one({"id": instance_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Instance not found")
    return {"deleted": True}


# --- excel/csv import ---
FIELD_ALIASES = {
    "service_name": ["service_name", "service", "servicename", "group", "groupname", "group_name"],
    "instance_name": ["instance_name", "instancename", "name"],
    "host_port": ["host_port", "hostport"],
    "host": ["host", "private_ip", "ip", "address"],
    "port": ["port"],
    "instance_type": ["instance_type", "instance", "type", "role", "instance_role"],
    "aws_instance_id": ["aws_instance_id", "instance_id", "ec2_instance_id", "ec2_id", "awsid"],
    "all_dns": ["all_dns", "dns", "dns_record", "alldns"],
    "srv_record": ["srv_record", "srv", "srv_records"],
    "aws_region": ["aws_region", "region"],
    "environment": ["environment", "env"],
    "status": ["status"],
}


def _norm_header(h):
    return str(h).strip().lower().replace(" ", "_") if h is not None else ""


def _dedup_list(items):
    seen, out = set(), []
    for x in items:
        x = (x or "").strip()
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


@router.post("/import-excel")
async def import_excel(file: UploadFile = File(...)):
    fname = (file.filename or "").lower()
    if not fname.endswith((".xlsx", ".xlsm", ".csv")):
        raise HTTPException(status_code=400, detail="Only .xlsx or .csv files are supported")
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    # Read into a list of rows (tuples of cell values).
    if fname.endswith(".csv"):
        text = raw.decode("utf-8-sig", errors="replace")
        rows = list(csv.reader(io.StringIO(text)))
    else:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
        except Exception:
            raise HTTPException(status_code=400, detail="Could not read Excel file")
        rows = [tuple(r) for r in wb.active.iter_rows(values_only=True)]
    rows = [r for r in rows if r is not None and any(c not in (None, "") for c in r)]
    if not rows:
        raise HTTPException(status_code=400, detail="Empty sheet")

    headers = [_norm_header(h) for h in rows[0]]
    rev = {}
    for canon, aliases in FIELD_ALIASES.items():
        for a in aliases:
            rev.setdefault(a, canon)
    # header -> canonical field, and list of metadata headers
    header_field = {h: rev.get(h) for h in headers if h}
    meta_headers = [h for h in headers if h and h != "id" and not header_field.get(h)]

    default_service = (os.path.splitext(file.filename or "")[0] or "Imported").strip()[:60] or "Imported"

    def rowdict(r):
        return {headers[i]: r[i] for i in range(min(len(headers), len(r))) if headers[i]}

    def val(row, canon):
        for h, c in header_field.items():
            if c == canon:
                v = row.get(h)
                if v not in (None, ""):
                    return str(v).strip()
        return ""

    # Host-grouped parse: a row with an instance_name starts a new record; rows
    # with a blank name append their DNS/SRV to the previous record.
    collected, current, skipped = [], None, 0
    for r in rows[1:]:
        row = rowdict(r)
        name = val(row, "instance_name")
        dns = val(row, "all_dns")
        srv = val(row, "srv_record")
        if name:
            host = val(row, "host")
            port = None
            hp = val(row, "host_port")
            if hp and not host:
                if ":" in hp:
                    h2, _, p = hp.rpartition(":")
                    host = h2.strip()
                    try:
                        port = int(p.strip())
                    except ValueError:
                        host = hp
                else:
                    host = hp
            if port is None and val(row, "port"):
                try:
                    port = int(val(row, "port"))
                except ValueError:
                    port = None
            env = val(row, "environment").upper() or "DEV"
            if env not in ENVIRONMENTS:
                env = "DEV"
            status = (val(row, "status") or "Running").capitalize()
            if status not in STATUSES:
                status = "Running"
            meta = {}
            for h in meta_headers:
                v = row.get(h)
                if v not in (None, ""):
                    meta[h] = str(v).strip()
            current = {
                "service_name": val(row, "service_name") or default_service,
                "instance_name": name, "host": host, "port": port,
                "instance_type": val(row, "instance_type"),
                "aws_instance_id": val(row, "aws_instance_id"),
                "aws_region": val(row, "aws_region"),
                "environment": env, "status": status,
                "dns": [dns] if dns else [], "srv": [srv] if srv else [],
                "meta": meta,
            }
            collected.append(current)
        elif current is not None:
            if dns:
                current["dns"].append(dns)
            if srv:
                current["srv"].append(srv)
        else:
            skipped += 1

    svc_cache = {s["service_name"]: s["id"] async for s in _db.db_services.find({}, {"_id": 0})}
    existing_awsids = {i["aws_instance_id"] async for i in _db.db_instances.find({"aws_instance_id": {"$ne": ""}}, {"_id": 0, "aws_instance_id": 1})}

    imported = 0
    for ins in collected:
        aws_id = ins["aws_instance_id"]
        if aws_id and aws_id in existing_awsids:
            skipped += 1
            continue
        sid = svc_cache.get(ins["service_name"])
        if not sid:
            sid = str(uuid.uuid4())
            await _db.db_services.insert_one(
                {"id": sid, "seq": await _next_seq("services"), "service_name": ins["service_name"]})
            svc_cache[ins["service_name"]] = sid
        metadata = [{"attribute_key": k, "attribute_value": v} for k, v in ins["meta"].items()]
        doc = {
            "id": str(uuid.uuid4()), "seq": await _next_seq("instances"),
            "service_id": sid, "instance_name": ins["instance_name"],
            "host": ins["host"], "port": ins["port"],
            "instance_type": ins["instance_type"], "aws_instance_id": aws_id,
            "all_dns": "; ".join(_dedup_list(ins["dns"])),
            "srv_record": "; ".join(_dedup_list(ins["srv"])),
            "aws_region": ins["aws_region"],
            "environment": ins["environment"], "status": ins["status"],
            "metadata": _dedup_meta(metadata),
            "created_at": now_iso(), "updated_at": now_iso(),
        }
        await _db.db_instances.insert_one(doc)
        if aws_id:
            existing_awsids.add(aws_id)
        imported += 1

    return {"imported": imported, "skipped": skipped}


# --- json export (relational shape) ---
async def build_export():
    services = await _db.db_services.find({}, {"_id": 0}).sort("seq", 1).to_list(5000)
    instances = await _db.db_instances.find({}, {"_id": 0}).sort("seq", 1).to_list(20000)

    svc_seq = {s["id"]: s["seq"] for s in services}
    db_services = [{"id": s["seq"], "service_name": s["service_name"]} for s in services]

    db_instances, db_meta = [], []
    meta_seq = 0
    for ins in instances:
        db_instances.append({
            "id": ins["seq"],
            "service_id": svc_seq.get(ins.get("service_id")),
            "instance_name": ins.get("instance_name", ""),
            "host": ins.get("host", ""),
            "port": ins.get("port"),
            "instance_type": ins.get("instance_type", ""),
            "aws_instance_id": ins.get("aws_instance_id", ""),
            "all_dns": ins.get("all_dns", ""),
            "srv_record": ins.get("srv_record", ""),
            "aws_region": ins.get("aws_region", ""),
            "environment": ins.get("environment", "DEV"),
            "status": ins.get("status", "Running"),
            "created_at": ins.get("created_at"),
            "updated_at": ins.get("updated_at"),
        })
        for m in ins.get("metadata", []):
            meta_seq += 1
            db_meta.append({
                "id": meta_seq,
                "instance_id": ins["seq"],
                "attribute_key": m.get("attribute_key"),
                "attribute_value": m.get("attribute_value"),
            })
    return {"db_services": db_services, "db_instances": db_instances,
            "db_instance_metadata": db_meta}


@router.get("/export-json")
async def export_json():
    payload = await build_export()
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": "attachment; filename=db_config.json"},
    )

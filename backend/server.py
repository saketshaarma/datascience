from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import io
import csv
import uuid
import logging
from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal
from datetime import datetime, timezone

import auth
from auth import auth_router, get_current_user, require_admin
from terraform_generator import generate_terraform
from k8s_generator import generate_k8s, build_config_json

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]
auth.init(db)

app = FastAPI(title="AWS Infra Inventory & Terraform Portal")

# protected router (requires auth)
api_router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])
# open router (health)
open_router = APIRouter(prefix="/api")

MAX_CSV_BYTES = 5 * 1024 * 1024  # 5 MB


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ----------------------------- Models -----------------------------
class EbsVolume(BaseModel):
    model_config = ConfigDict(extra="ignore")
    device_name: str = ""
    size_gb: Optional[int] = None
    volume_type: str = "gp3"


class InstanceBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    instance_name: str = ""
    environment: str = ""                # dev / staging / prod
    host: str = ""                       # legacy IP field
    port: Optional[int] = None
    instance_role: str = ""              # slave / master / etc
    region: str = "us-east-1"
    ec2_instance_id: str = ""            # i-xxxx
    ec2_instance_type: str = ""          # t3.medium
    ami_id: str = ""
    vpc_id: str = ""
    subnet_id: str = ""
    availability_zone: str = ""
    private_ip: str = ""
    public_ip: str = ""
    security_groups: List[str] = Field(default_factory=list)
    iam_instance_profile: str = ""
    ebs_volumes: List[EbsVolume] = Field(default_factory=list)
    key_name: str = ""
    dns_records: List[str] = Field(default_factory=list)
    srv_records: List[str] = Field(default_factory=list)
    tags: dict = Field(default_factory=dict)
    custom_metadata: dict = Field(default_factory=dict)
    notes: str = ""


class InstanceCreate(InstanceBase):
    pass


class Instance(InstanceBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class TerraformRequest(BaseModel):
    instance_ids: Optional[List[str]] = None
    resources: List[str] = Field(default_factory=lambda: ["ec2", "dns", "srv", "sg"])
    output_format: Literal["hcl", "json", "both"] = "both"
    dns_target: Literal["instance_private", "instance_public", "host"] = "instance_private"
    zone_id: str = "REPLACE_WITH_ZONE_ID"
    default_ami: str = "ami-0c55b159cbfafe1f0"
    default_instance_type: str = "t3.medium"


class K8sNode(BaseModel):
    model_config = ConfigDict(extra="ignore")
    hostname: str = ""
    instance_type: str = "t3.medium"
    root_volume_size: int = 50


class K8sClusterBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = "cluster"
    aws_region: str = "ap-south-1"
    vpc_tag: str = ""
    subnet_tag: str = ""
    key_name: str = ""
    private_zone_name: str = ""
    ami_id: str = ""
    security_group_tags: dict = Field(default_factory=dict)
    instance_tags: dict = Field(default_factory=dict)
    volume_tags: dict = Field(default_factory=dict)
    nodes: List[K8sNode] = Field(default_factory=list)
    extra: dict = Field(default_factory=dict)


class K8sClusterCreate(K8sClusterBase):
    pass


class K8sCluster(K8sClusterBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


# ----------------------------- Open -----------------------------
@open_router.get("/")
async def root():
    return {"message": "AWS Infra Inventory API"}


@open_router.get("/health")
async def health():
    return {"status": "ok"}


# ----------------------------- Instances -----------------------------
@api_router.get("/instances", response_model=List[Instance])
async def list_instances(search: Optional[str] = None):
    query = {}
    if search:
        rx = {"$regex": search, "$options": "i"}
        query = {"$or": [
            {"instance_name": rx}, {"host": rx}, {"instance_role": rx},
            {"ec2_instance_type": rx}, {"ec2_instance_id": rx}, {"environment": rx},
            {"private_ip": rx}, {"public_ip": rx}, {"dns_records": rx}, {"srv_records": rx},
        ]}
    docs = await db.instances.find(query, {"_id": 0}).sort("created_at", -1).to_list(5000)
    return docs


@api_router.get("/instances/export")
async def export_csv():
    docs = await db.instances.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    buf = io.StringIO()
    cols = [
        "instance_name", "environment", "host", "port", "instance_role", "region",
        "ec2_instance_id", "ec2_instance_type", "ami_id", "vpc_id", "subnet_id",
        "availability_zone", "private_ip", "public_ip", "security_groups",
        "iam_instance_profile", "ebs_volumes", "key_name", "dns_records", "srv_records",
        "tags", "custom_metadata", "notes",
    ]
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for d in docs:
        row = dict(d)
        row["security_groups"] = ";".join(d.get("security_groups", []))
        row["dns_records"] = ";".join(d.get("dns_records", []))
        row["srv_records"] = ";".join(d.get("srv_records", []))
        row["ebs_volumes"] = ";".join(
            f"{v.get('device_name','')}:{v.get('size_gb','')}:{v.get('volume_type','')}"
            for v in d.get("ebs_volumes", [])
        )
        row["tags"] = ";".join(f"{k}={v}" for k, v in d.get("tags", {}).items())
        row["custom_metadata"] = ";".join(f"{k}={v}" for k, v in d.get("custom_metadata", {}).items())
        writer.writerow(row)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=infra_inventory.csv"},
    )


@api_router.get("/instances/{instance_id}", response_model=Instance)
async def get_instance(instance_id: str):
    doc = await db.instances.find_one({"id": instance_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Instance not found")
    return doc


async def _assert_unique_hostport(host, port, exclude_id=None):
    host = (host or "").strip()
    if not host:
        return
    q = {"host": host, "port": port}
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    if await db.instances.find_one(q):
        label = f"{host}:{port}" if port is not None else host
        raise HTTPException(status_code=409, detail=f"An instance with host {label} already exists")



@api_router.post("/instances", response_model=Instance)
async def create_instance(payload: InstanceCreate):
    await _assert_unique_hostport(payload.host, payload.port)
    obj = Instance(**payload.model_dump())
    await db.instances.insert_one(obj.model_dump())
    return obj


@api_router.put("/instances/{instance_id}", response_model=Instance)
async def update_instance(instance_id: str, payload: InstanceCreate):
    existing = await db.instances.find_one({"id": instance_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Instance not found")
    await _assert_unique_hostport(payload.host, payload.port, exclude_id=instance_id)
    data = payload.model_dump()
    data["updated_at"] = now_iso()
    await db.instances.update_one({"id": instance_id}, {"$set": data})
    return await db.instances.find_one({"id": instance_id}, {"_id": 0})


@api_router.delete("/instances/{instance_id}")
async def delete_instance(instance_id: str, current=Depends(require_admin)):
    res = await db.instances.delete_one({"id": instance_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Instance not found")
    return {"deleted": True}


@api_router.delete("/instances")
async def delete_all_instances(confirm: str = "", current=Depends(require_admin)):
    if confirm != "DELETE_ALL":
        raise HTTPException(status_code=400, detail="Confirmation required")
    res = await db.instances.delete_many({})
    return {"deleted": res.deleted_count}


@api_router.get("/stats")
async def stats():
    docs = await db.instances.find({}, {"_id": 0}).to_list(5000)
    total_hosts = len(docs)
    total_dns = sum(len(d.get("dns_records", [])) for d in docs)
    total_srv = sum(len(d.get("srv_records", [])) for d in docs)
    roles, types, envs = {}, {}, {}
    for d in docs:
        r = d.get("instance_role") or "unknown"
        roles[r] = roles.get(r, 0) + 1
        t = d.get("ec2_instance_type") or "unspecified"
        types[t] = types.get(t, 0) + 1
        e = d.get("environment") or "unset"
        envs[e] = envs.get(e, 0) + 1
    return {
        "total_hosts": total_hosts,
        "total_dns": total_dns,
        "total_srv": total_srv,
        "role_breakdown": [{"name": k, "value": v} for k, v in roles.items()],
        "type_breakdown": [{"name": k, "value": v} for k, v in types.items()],
        "env_breakdown": [{"name": k, "value": v} for k, v in envs.items()],
    }


def _parse_hostport(value: str):
    value = (value or "").strip()
    if not value:
        return "", None
    if ":" in value:
        host, _, port = value.rpartition(":")
        try:
            return host.strip(), int(port.strip())
        except ValueError:
            return value, None
    return value, None


@api_router.post("/instances/import-csv")
async def import_csv(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are allowed")
    raw = await file.read()
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 5 MB)")
    if not raw.strip():
        raise HTTPException(status_code=400, detail="Empty file")
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="Invalid CSV")

    def norm(k):
        return (k or "").strip().lower().replace(" ", "_")

    fmap = {norm(k): k for k in reader.fieldnames}

    def col(row, *names):
        for n in names:
            if n in fmap:
                v = row.get(fmap[n])
                if v is not None and str(v).strip() != "":
                    return str(v).strip()
        return ""

    instances, current, last_name = [], None, ""

    for row in reader:
        hostport = col(row, "host_port", "hostport", "host")
        dns = col(row, "all_dns", "dns", "dns_record")
        srv = col(row, "srv", "srv_record")
        role = col(row, "instance_type", "instance_role", "role")
        name = col(row, "instancename", "instance_name", "name")
        ec2type = col(row, "ec2_instance_type", "ec2_type")
        ami = col(row, "ami", "ami_id", "ami_details")
        region = col(row, "region")
        env = col(row, "environment", "env")
        ec2id = col(row, "ec2_instance_id", "instance_id")

        if hostport:
            host, port = _parse_hostport(hostport)
            if name:
                last_name = name
            current = Instance(
                instance_name=name or last_name, environment=env, host=host, port=port,
                instance_role=role, ec2_instance_type=ec2type, ami_id=ami,
                ec2_instance_id=ec2id, region=region or "us-east-1",
            ).model_dump()
            if dns:
                current["dns_records"].append(dns)
            if srv:
                current["srv_records"].append(srv)
            instances.append(current)
        elif current is not None:
            if dns:
                current["dns_records"].append(dns)
            if srv:
                current["srv_records"].append(srv)
        else:
            if dns or srv or name:
                current = Instance(
                    instance_name=name or last_name, instance_role=role,
                    ec2_instance_type=ec2type, ami_id=ami,
                    dns_records=[dns] if dns else [], srv_records=[srv] if srv else [],
                ).model_dump()
                instances.append(current)

    for ins in instances:
        ins["dns_records"] = list(dict.fromkeys(ins["dns_records"]))
        ins["srv_records"] = list(dict.fromkeys(ins["srv_records"]))

    # enforce unique host:port — skip combos that already exist in DB or repeat in-file
    existing = await db.instances.find({}, {"_id": 0, "host": 1, "port": 1}).to_list(10000)
    seen = {(e.get("host"), e.get("port")) for e in existing}
    to_insert, skipped = [], 0
    for ins in instances:
        key = (ins.get("host"), ins.get("port"))
        if ins.get("host") and key in seen:
            skipped += 1
            continue
        if ins.get("host"):
            seen.add(key)
        to_insert.append(ins)

    if to_insert:
        await db.instances.insert_many(to_insert)
    return {"imported": len(to_insert), "skipped": skipped}


@api_router.post("/terraform/generate")
async def terraform_generate(req: TerraformRequest):
    query = {"id": {"$in": req.instance_ids}} if req.instance_ids else {}
    docs = await db.instances.find(query, {"_id": 0}).to_list(5000)
    if not docs:
        raise HTTPException(status_code=400, detail="No instances selected")
    return generate_terraform(
        docs, resources=req.resources, output_format=req.output_format,
        zone_id=req.zone_id, default_ami=req.default_ami,
        default_instance_type=req.default_instance_type, dns_target=req.dns_target,
    )


@api_router.get("/k8s/clusters", response_model=List[K8sCluster])
async def list_clusters():
    docs = await db.k8s_clusters.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return docs


@api_router.post("/k8s/clusters", response_model=K8sCluster)
async def create_cluster(payload: K8sClusterCreate):
    obj = K8sCluster(**payload.model_dump())
    await db.k8s_clusters.insert_one(obj.model_dump())
    return obj


@api_router.get("/k8s/clusters/{cluster_id}", response_model=K8sCluster)
async def get_cluster(cluster_id: str):
    doc = await db.k8s_clusters.find_one({"id": cluster_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return doc


@api_router.put("/k8s/clusters/{cluster_id}", response_model=K8sCluster)
async def update_cluster(cluster_id: str, payload: K8sClusterCreate):
    existing = await db.k8s_clusters.find_one({"id": cluster_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Cluster not found")
    data = payload.model_dump()
    data["updated_at"] = now_iso()
    await db.k8s_clusters.update_one({"id": cluster_id}, {"$set": data})
    return await db.k8s_clusters.find_one({"id": cluster_id}, {"_id": 0})


@api_router.delete("/k8s/clusters/{cluster_id}")
async def delete_cluster(cluster_id: str, current=Depends(require_admin)):
    res = await db.k8s_clusters.delete_one({"id": cluster_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return {"deleted": True}


@api_router.post("/k8s/clusters/{cluster_id}/generate")
async def generate_cluster(cluster_id: str):
    doc = await db.k8s_clusters.find_one({"id": cluster_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return generate_k8s(doc)


@api_router.post("/k8s/preview")
async def preview_cluster(payload: K8sClusterCreate):
    """Generate config JSON + Terraform from an unsaved cluster spec."""
    return generate_k8s(payload.model_dump())



app.include_router(auth_router)
app.include_router(open_router)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000"), "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def on_startup():
    await auth.ensure_indexes()
    await auth.seed_admin()


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

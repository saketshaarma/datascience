from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import io
import csv
import logging
import uuid
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal
from datetime import datetime, timezone

from terraform_generator import generate_terraform

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="AWS Infra Inventory & Terraform Portal")
api_router = APIRouter(prefix="/api")


# ----------------------------- Models -----------------------------
def now_iso():
    return datetime.now(timezone.utc).isoformat()


class InstanceBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    instance_name: str = ""
    host: str = ""                      # IP address
    port: Optional[int] = None
    instance_role: str = ""             # slave / master / etc
    ec2_instance_type: str = ""         # t3.medium etc
    ami_id: str = ""
    region: str = "us-east-1"
    availability_zone: str = ""
    vpc_id: str = ""
    subnet_id: str = ""
    key_name: str = ""
    dns_records: List[str] = Field(default_factory=list)
    srv_records: List[str] = Field(default_factory=list)
    tags: dict = Field(default_factory=dict)
    notes: str = ""


class InstanceCreate(InstanceBase):
    pass


class Instance(InstanceBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class TerraformRequest(BaseModel):
    instance_ids: Optional[List[str]] = None   # None -> all
    resources: List[str] = Field(default_factory=lambda: ["ec2", "dns", "srv", "sg"])
    output_format: Literal["hcl", "json", "both"] = "both"
    zone_id: str = "REPLACE_WITH_ZONE_ID"
    default_ami: str = "ami-0c55b159cbfafe1f0"
    default_instance_type: str = "t3.medium"


# ----------------------------- Routes -----------------------------
@api_router.get("/")
async def root():
    return {"message": "AWS Infra Inventory API"}


@api_router.get("/instances", response_model=List[Instance])
async def list_instances(search: Optional[str] = None):
    query = {}
    if search:
        rx = {"$regex": search, "$options": "i"}
        query = {"$or": [
            {"instance_name": rx}, {"host": rx}, {"instance_role": rx},
            {"ec2_instance_type": rx}, {"dns_records": rx}, {"srv_records": rx},
        ]}
    docs = await db.instances.find(query, {"_id": 0}).sort("created_at", -1).to_list(5000)
    return docs


@api_router.get("/instances/{instance_id}", response_model=Instance)
async def get_instance(instance_id: str):
    doc = await db.instances.find_one({"id": instance_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Instance not found")
    return doc


@api_router.post("/instances", response_model=Instance)
async def create_instance(payload: InstanceCreate):
    obj = Instance(**payload.model_dump())
    await db.instances.insert_one(obj.model_dump())
    return obj


@api_router.put("/instances/{instance_id}", response_model=Instance)
async def update_instance(instance_id: str, payload: InstanceCreate):
    existing = await db.instances.find_one({"id": instance_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Instance not found")
    data = payload.model_dump()
    data["updated_at"] = now_iso()
    await db.instances.update_one({"id": instance_id}, {"$set": data})
    updated = await db.instances.find_one({"id": instance_id}, {"_id": 0})
    return updated


@api_router.delete("/instances/{instance_id}")
async def delete_instance(instance_id: str):
    res = await db.instances.delete_one({"id": instance_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Instance not found")
    return {"deleted": True}


@api_router.delete("/instances")
async def delete_all_instances():
    res = await db.instances.delete_many({})
    return {"deleted": res.deleted_count}


@api_router.get("/stats")
async def stats():
    docs = await db.instances.find({}, {"_id": 0}).to_list(5000)
    total_hosts = len(docs)
    total_dns = sum(len(d.get("dns_records", [])) for d in docs)
    total_srv = sum(len(d.get("srv_records", [])) for d in docs)
    roles = {}
    types = {}
    for d in docs:
        r = d.get("instance_role") or "unknown"
        roles[r] = roles.get(r, 0) + 1
        t = d.get("ec2_instance_type") or "unspecified"
        types[t] = types.get(t, 0) + 1
    return {
        "total_hosts": total_hosts,
        "total_dns": total_dns,
        "total_srv": total_srv,
        "role_breakdown": [{"name": k, "value": v} for k, v in roles.items()],
        "type_breakdown": [{"name": k, "value": v} for k, v in types.items()],
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
    raw = await file.read()
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="Empty or invalid CSV")

    # normalize header keys
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

    instances = []
    current = None
    last_name = ""

    for row in reader:
        hostport = col(row, "host_port", "hostport", "host")
        dns = col(row, "all_dns", "dns", "dns_record")
        srv = col(row, "srv", "srv_record")
        role = col(row, "instance_type", "instance_role", "role")
        name = col(row, "instancename", "instance_name", "name")
        ec2type = col(row, "ec2_instance_type", "ec2_type", "type")
        ami = col(row, "ami", "ami_id", "ami_details")
        region = col(row, "region")

        if hostport:  # new instance row
            host, port = _parse_hostport(hostport)
            if name:
                last_name = name
            current = Instance(
                instance_name=name or last_name,
                host=host,
                port=port,
                instance_role=role,
                ec2_instance_type=ec2type,
                ami_id=ami,
                region=region or "us-east-1",
            ).model_dump()
            if dns:
                current["dns_records"].append(dns)
            if srv:
                current["srv_records"].append(srv)
            instances.append(current)
        elif current is not None:
            # continuation row: accumulate dns/srv into current
            if dns:
                current["dns_records"].append(dns)
            if srv:
                current["srv_records"].append(srv)
        else:
            # flat CSV row with no grouping and no host: skip if empty
            if dns or srv or name:
                current = Instance(
                    instance_name=name or last_name,
                    instance_role=role,
                    ec2_instance_type=ec2type,
                    ami_id=ami,
                    dns_records=[dns] if dns else [],
                    srv_records=[srv] if srv else [],
                ).model_dump()
                instances.append(current)

    # de-dup dns/srv within each instance
    for ins in instances:
        ins["dns_records"] = list(dict.fromkeys(ins["dns_records"]))
        ins["srv_records"] = list(dict.fromkeys(ins["srv_records"]))

    if instances:
        await db.instances.insert_many(instances)

    return {"imported": len(instances)}


@api_router.post("/terraform/generate")
async def terraform_generate(req: TerraformRequest):
    query = {}
    if req.instance_ids:
        query = {"id": {"$in": req.instance_ids}}
    docs = await db.instances.find(query, {"_id": 0}).to_list(5000)
    if not docs:
        raise HTTPException(status_code=400, detail="No instances selected")
    result = generate_terraform(
        docs,
        resources=req.resources,
        output_format=req.output_format,
        zone_id=req.zone_id,
        default_ami=req.default_ami,
        default_instance_type=req.default_instance_type,
    )
    return result


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

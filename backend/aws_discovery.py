"""AWS resource discovery (demo/mock + optional live via boto3).

Aggregates resources from the portal's own data (inventory, DB config, k8s
clusters) as "discovered" AWS resources, filterable by a tag key/value.
When live mode is enabled and valid AWS credentials are configured, it uses
boto3 + the Resource Groups Tagging API instead.
"""
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from auth import get_current_user, require_admin

_db = None
SETTINGS_ID = "aws"


def init(db):
    global _db
    _db = db


# ----------------------------- settings -----------------------------
class AwsSettings(BaseModel):
    access_key_id: str = ""
    secret_access_key: str = ""
    region: str = "us-east-1"
    use_live: bool = False


def _mask(v: str) -> str:
    v = v or ""
    if len(v) <= 4:
        return "••••" if v else ""
    return "••••" + v[-4:]


async def _get_settings():
    return await _db.aws_settings.find_one({"_id": SETTINGS_ID}) or {}


# ----------------------------- mock discovery -----------------------------
async def _collect_resources():
    res = []

    async for ins in _db.instances.find({}, {"_id": 0}):
        tags = dict(ins.get("tags") or {})
        tags.update(ins.get("custom_metadata") or {})
        if ins.get("environment"):
            tags["Environment"] = ins["environment"]
        if ins.get("instance_role"):
            tags["Role"] = ins["instance_role"]
        name = ins.get("instance_name") or ins.get("host") or "instance"
        region = ins.get("region", "")
        res.append({"id": ins.get("ec2_instance_id") or ins.get("host") or name,
                    "kind": "ec2_instance", "name": name, "region": region,
                    "status": "Running", "source": "inventory", "tags": tags})
        if ins.get("port"):
            res.append({"id": f"sg-{name}", "kind": "security_group", "name": f"{name}-sg",
                        "region": region, "status": "active", "source": "inventory", "tags": tags})
        for d in ins.get("dns_records", []):
            res.append({"id": d, "kind": "route53_record", "name": d, "region": "global",
                        "status": "active", "source": "inventory", "tags": tags})
        for v in ins.get("ebs_volumes", []):
            dev = v.get("device_name") or "vol"
            res.append({"id": f"{name}-{dev}", "kind": "ebs_volume", "name": dev, "region": region,
                        "status": "in-use", "source": "inventory", "tags": tags})

    svc = {s["id"]: s["service_name"] async for s in _db.db_services.find({}, {"_id": 0})}
    async for d in _db.db_instances.find({}, {"_id": 0}):
        tags = {m["attribute_key"]: m["attribute_value"] for m in d.get("metadata", [])}
        tags["Environment"] = d.get("environment", "DEV")
        if svc.get(d.get("service_id")):
            tags["Service"] = svc[d["service_id"]]
        res.append({"id": d.get("aws_instance_id") or d.get("instance_name"),
                    "kind": "rds_instance", "name": d.get("instance_name"),
                    "region": d.get("aws_region", ""), "status": d.get("status", "Running"),
                    "source": "db_config", "tags": tags})

    async for c in _db.k8s_clusters.find({}, {"_id": 0}):
        itags = dict(c.get("instance_tags") or {})
        vtags = dict(c.get("volume_tags") or {})
        stags = dict(c.get("security_group_tags") or {})
        region = c.get("aws_region", "")
        cname = c.get("name", "cluster")
        for n in c.get("nodes", []):
            host = n.get("hostname") or "node"
            t = dict(itags); t["Name"] = host; t["Cluster"] = cname
            res.append({"id": f"{cname}-{host}", "kind": "ec2_instance", "name": host,
                        "region": region, "status": "Running", "source": "kubernetes", "tags": t})
            vt = dict(vtags); vt["Name"] = f"{host}-root"; vt["Cluster"] = cname
            res.append({"id": f"{cname}-{host}-vol", "kind": "ebs_volume", "name": f"{host}-root",
                        "region": region, "status": "in-use", "source": "kubernetes", "tags": vt})
        st = dict(stags); st["Name"] = f"{cname}-sg"; st["Cluster"] = cname
        res.append({"id": f"{cname}-sg", "kind": "security_group", "name": f"{cname}-sg",
                    "region": region, "status": "active", "source": "kubernetes", "tags": st})

    return res


def _summarize(resources, mode, region, account_id, tag_key, tag_value):
    by_kind, by_source = {}, {}
    for r in resources:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1
    return {
        "mode": mode, "account_id": account_id, "region": region,
        "filter": {"tag_key": tag_key, "tag_value": tag_value},
        "total": len(resources),
        "by_kind": [{"name": k, "value": v} for k, v in by_kind.items()],
        "by_source": [{"name": k, "value": v} for k, v in by_source.items()],
        "resources": resources,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _discover_live_sync(access_key, secret, region, tag_key, tag_value):
    import boto3
    from botocore.config import Config
    session = boto3.Session(aws_access_key_id=access_key, aws_secret_access_key=secret,
                            region_name=region)
    cfg = Config(read_timeout=15, connect_timeout=5, retries={"mode": "standard", "max_attempts": 3})
    account_id = session.client("sts", config=cfg).get_caller_identity()["Account"]
    tagging = session.client("resourcegroupstaggingapi", config=cfg)
    tag_filters = [{"Key": tag_key, "Values": [tag_value] if tag_value else []}] if tag_key else []
    out = []
    kind_map = {"instance": "ec2_instance", "volume": "ebs_volume",
                "security-group": "security_group", "db": "rds_instance"}
    for page in tagging.get_paginator("get_resources").paginate(
            TagFilters=tag_filters,
            ResourceTypeFilters=["ec2:instance", "ec2:volume", "ec2:security-group", "rds:db"],
            ResourcesPerPage=100):
        for item in page.get("ResourceTagMappingList", []):
            arn = item["ResourceARN"]
            rtype = arn.split(":")[5].split("/")[0].split(":")[0]
            out.append({"id": arn.rsplit("/", 1)[-1].rsplit(":", 1)[-1], "arn": arn,
                        "kind": kind_map.get(rtype, rtype), "name": arn.rsplit("/", 1)[-1],
                        "region": region, "status": "-", "source": "aws",
                        "tags": {t["Key"]: t.get("Value", "") for t in item.get("Tags", [])}})
    return account_id, out


# ----------------------------- router -----------------------------
router = APIRouter(prefix="/api/aws", dependencies=[Depends(get_current_user)])


@router.get("/settings")
async def get_aws_settings(current=Depends(require_admin)):
    s = await _get_settings()
    return {
        "configured": bool(s.get("access_key_id")),
        "access_key_id_masked": _mask(s.get("access_key_id", "")),
        "region": s.get("region", "us-east-1"),
        "use_live": s.get("use_live", False),
    }


@router.put("/settings")
async def save_aws_settings(payload: AwsSettings, current=Depends(require_admin)):
    doc = {"_id": SETTINGS_ID, "region": payload.region, "use_live": payload.use_live,
           "updated_at": datetime.now(timezone.utc).isoformat()}
    existing = await _get_settings()
    doc["access_key_id"] = payload.access_key_id or existing.get("access_key_id", "")
    # keep existing secret if left blank on update
    doc["secret_access_key"] = payload.secret_access_key or existing.get("secret_access_key", "")
    await _db.aws_settings.update_one({"_id": SETTINGS_ID}, {"$set": doc}, upsert=True)
    return {"ok": True, "configured": bool(doc["access_key_id"]), "use_live": doc["use_live"]}


@router.get("/tag-options")
async def tag_options():
    resources = await _collect_resources()
    keys = {}
    for r in resources:
        for k, v in (r.get("tags") or {}).items():
            keys.setdefault(k, set()).add(str(v))
    return {"keys": sorted(keys.keys()), "values": {k: sorted(v) for k, v in keys.items()}}


class DiscoverBody(BaseModel):
    tag_key: Optional[str] = None
    tag_value: Optional[str] = None


@router.post("/discover")
async def discover(body: DiscoverBody):
    s = await _get_settings()
    region = s.get("region", "us-east-1")
    tag_key = (body.tag_key or "").strip()
    tag_value = (body.tag_value or "").strip()

    if s.get("use_live") and s.get("access_key_id") and s.get("secret_access_key"):
        import asyncio
        try:
            account_id, resources = await asyncio.to_thread(
                _discover_live_sync, s["access_key_id"], s["secret_access_key"],
                region, tag_key, tag_value)
            return _summarize(resources, "live", region, account_id, tag_key, tag_value)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"AWS live discovery failed: {type(e).__name__}")

    # demo/mock
    resources = await _collect_resources()
    if tag_key:
        resources = [r for r in resources
                     if r.get("tags", {}).get(tag_key) == tag_value
                     or (not tag_value and tag_key in r.get("tags", {}))]
    return _summarize(resources, "demo", region, "DEMO-000000000000", tag_key, tag_value)

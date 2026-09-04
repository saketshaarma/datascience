"""AWS resource discovery (demo/mock + optional live via boto3).

Aggregates resources from the portal's own data (inventory, DB config, k8s
clusters) as "discovered" AWS resources, filterable by a tag key/value.
When live mode is enabled and valid AWS credentials are configured, it uses
boto3 + the Resource Groups Tagging API instead.
"""
import os
from datetime import datetime, timezone
from typing import Optional, Literal

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
    zones = {}  # zone_name -> {tags, source, count}

    def add_zone(name, tags, source):
        name = (name or "").strip().rstrip(".")
        if not name:
            return
        z = zones.setdefault(name, {"tags": tags, "source": source, "count": 0})
        z["count"] += 1

    def zone_of(dns):
        dns = (dns or "").strip().rstrip(".")
        parts = dns.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else dns

    # ---- inventory ----
    async for ins in _db.instances.find({}, {"_id": 0}):
        tags = dict(ins.get("tags") or {})
        tags.update(ins.get("custom_metadata") or {})
        if ins.get("environment"):
            tags["Environment"] = ins["environment"]
        if ins.get("instance_role"):
            tags["Role"] = ins["instance_role"]
        name = ins.get("instance_name") or ins.get("host") or "instance"
        region = ins.get("region", "")
        host = ins.get("host", "")
        res.append({"id": ins.get("ec2_instance_id") or host or name, "kind": "ec2_instance",
                    "name": name, "region": region, "status": "Running", "source": "inventory",
                    "tags": tags, "details": {
                        "instance_id": ins.get("ec2_instance_id", ""), "private_ip": host,
                        "public_ip": ins.get("public_ip", ""), "port": ins.get("port"),
                        "instance_type": ins.get("ec2_instance_type", ""), "ami": ins.get("ami_id", ""),
                        "vpc": ins.get("vpc_id", ""), "subnet": ins.get("subnet_id", ""),
                        "environment": ins.get("environment", ""), "role": ins.get("instance_role", "")}})
        if ins.get("port"):
            res.append({"id": f"sg-{name}", "kind": "security_group", "name": f"{name}-sg",
                        "region": region, "status": "active", "source": "inventory", "tags": tags,
                        "details": {"ports": [ins["port"]], "vpc": ins.get("vpc_id", ""),
                                    "protocol": "tcp"}})
        for v in ins.get("ebs_volumes", []):
            dev = v.get("device_name") or "vol"
            res.append({"id": f"{name}-{dev}", "kind": "ebs_volume", "name": dev, "region": region,
                        "status": "in-use", "source": "inventory", "tags": tags,
                        "details": {"device_name": dev, "size_gb": v.get("size_gb"),
                                    "volume_type": v.get("volume_type", "gp3"), "attached_to": name}})
        for d in ins.get("dns_records", []):
            d = d.strip()
            if not d:
                continue
            z = zone_of(d)
            add_zone(z, tags, "inventory")
            res.append({"id": d, "kind": "a_record", "name": d, "region": "global", "status": "active",
                        "source": "inventory", "tags": tags,
                        "details": {"record": d, "type": "A", "value": host, "ttl": 300, "zone": z}})

    # ---- db config ----
    svc = {s["id"]: s["service_name"] async for s in _db.db_services.find({}, {"_id": 0})}
    async for d in _db.db_instances.find({}, {"_id": 0}):
        tags = {m["attribute_key"]: m["attribute_value"] for m in d.get("metadata", [])}
        tags["Environment"] = d.get("environment", "DEV")
        if svc.get(d.get("service_id")):
            tags["Service"] = svc[d["service_id"]]
        host = d.get("host", "")
        res.append({"id": d.get("aws_instance_id") or d.get("instance_name"), "kind": "ec2_instance",
                    "name": d.get("instance_name"), "region": d.get("aws_region", ""),
                    "status": d.get("status", "Running"), "source": "db_config", "tags": tags,
                    "details": {"instance_id": d.get("aws_instance_id", ""), "private_ip": host,
                                "port": d.get("port"), "instance_type": d.get("instance_type", ""),
                                "service": tags.get("Service", ""), "environment": d.get("environment", "")}})
        adns = (d.get("all_dns") or "").strip()
        if adns:
            z = zone_of(adns)
            add_zone(z, tags, "db_config")
            res.append({"id": adns, "kind": "a_record", "name": adns, "region": "global", "status": "active",
                        "source": "db_config", "tags": tags,
                        "details": {"record": adns, "type": "A", "value": host, "ttl": 300, "zone": z}})

    # ---- kubernetes ----
    async for c in _db.k8s_clusters.find({}, {"_id": 0}):
        itags = dict(c.get("instance_tags") or {})
        vtags = dict(c.get("volume_tags") or {})
        stags = dict(c.get("security_group_tags") or {})
        region = c.get("aws_region", "")
        cname = c.get("name", "cluster")
        zone = c.get("private_zone_name", "")
        if zone:
            add_zone(zone, itags, "kubernetes")
        for n in c.get("nodes", []):
            host = n.get("hostname") or "node"
            t = dict(itags); t["Name"] = host; t["Cluster"] = cname
            res.append({"id": f"{cname}-{host}", "kind": "ec2_instance", "name": host, "region": region,
                        "status": "Running", "source": "kubernetes", "tags": t,
                        "details": {"instance_type": n.get("instance_type", ""), "cluster": cname,
                                    "root_volume_size": n.get("root_volume_size"), "hostname": host}})
            vt = dict(vtags); vt["Name"] = f"{host}-root"; vt["Cluster"] = cname
            res.append({"id": f"{cname}-{host}-vol", "kind": "ebs_volume", "name": f"{host}-root",
                        "region": region, "status": "in-use", "source": "kubernetes", "tags": vt,
                        "details": {"device_name": "/dev/xvda", "size_gb": n.get("root_volume_size"),
                                    "volume_type": "gp3", "attached_to": host}})
            if zone:
                rec = f"{host}.{zone}"
                res.append({"id": rec, "kind": "a_record", "name": rec, "region": "global",
                            "status": "active", "source": "kubernetes", "tags": t,
                            "details": {"record": rec, "type": "A", "value": "(instance private_ip)",
                                        "ttl": 300, "zone": zone}})
        st = dict(stags); st["Name"] = f"{cname}-sg"; st["Cluster"] = cname
        res.append({"id": f"{cname}-sg", "kind": "security_group", "name": f"{cname}-sg", "region": region,
                    "status": "active", "source": "kubernetes", "tags": st,
                    "details": {"ports": ["all (self)"], "cluster": cname, "protocol": "-1"}})

    # ---- route53 zones (derived) ----
    for zname, z in zones.items():
        res.append({"id": zname, "kind": "route53_zone", "name": zname, "region": "global",
                    "status": "private", "source": z["source"], "tags": z["tags"],
                    "details": {"zone_name": zname, "record_count": z["count"], "private": True}})

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


def _parse_arn(arn):
    """Return (service, resource_type, resource_id) from an ARN."""
    parts = arn.split(":", 5)
    service = parts[2] if len(parts) > 2 else ""
    resource = parts[5] if len(parts) > 5 else ""
    if "/" in resource:
        rtype, rid = resource.split("/", 1)
    elif ":" in resource:
        rtype, rid = resource.split(":", 1)
    else:
        rtype, rid = resource, resource
    return service, rtype, rid


def _kind_from_arn(service, rtype):
    m = {
        ("ec2", "instance"): "ec2_instance",
        ("ec2", "volume"): "ebs_volume",
        ("ec2", "security-group"): "security_group",
        ("route53", "hostedzone"): "route53_zone",
        ("rds", "db"): "rds_db",
    }
    return m.get((service, rtype)) or (f"{service}:{rtype}" if rtype else (service or "unknown"))


def _new_session(access_key, secret, region):
    import boto3
    return boto3.Session(aws_access_key_id=access_key, aws_secret_access_key=secret,
                         region_name=region)


def _boto_cfg():
    from botocore.config import Config
    return Config(read_timeout=25, connect_timeout=6, retries={"mode": "standard", "max_attempts": 3})


def _discover_live_sync(access_key, secret, region, tag_key, tag_value):
    session = _new_session(access_key, secret, region)
    cfg = _boto_cfg()
    account_id = session.client("sts", config=cfg).get_caller_identity()["Account"]
    tagging = session.client("resourcegroupstaggingapi", config=cfg)

    tag_filters = []
    if tag_key:
        tf = {"Key": tag_key}
        if tag_value:
            tf["Values"] = [tag_value]
        tag_filters.append(tf)

    # Discover EVERY tagged resource in the region (no resource-type restriction).
    raw = []
    for page in tagging.get_paginator("get_resources").paginate(
            TagFilters=tag_filters, ResourcesPerPage=100):
        raw.extend(page.get("ResourceTagMappingList", []))

    resources, instance_ids, volume_ids = [], [], []
    for item in raw:
        arn = item["ResourceARN"]
        tags = {t["Key"]: t.get("Value", "") for t in item.get("Tags", [])}
        service, rtype, rid = _parse_arn(arn)
        kind = _kind_from_arn(service, rtype)
        r = {
            "id": rid, "arn": arn, "kind": kind,
            "name": tags.get("Name") or rid,
            "region": "global" if service in ("route53", "iam", "cloudfront") else region,
            "status": "-", "source": "aws", "tags": tags,
            "details": {"arn": arn, "service": service, "resource_type": rtype},
        }
        resources.append(r)
        if kind == "ec2_instance" and rid.startswith("i-"):
            instance_ids.append(rid)
        elif kind == "ebs_volume" and rid.startswith("vol-"):
            volume_ids.append(rid)

    # Enrich EC2 instances with useful details for the dashboard table/popup.
    if instance_ids:
        try:
            ec2 = session.client("ec2", config=cfg)
            info = {}
            for i in range(0, len(instance_ids), 100):
                for res in ec2.describe_instances(InstanceIds=instance_ids[i:i + 100]).get("Reservations", []):
                    for inst in res.get("Instances", []):
                        info[inst["InstanceId"]] = inst
            for r in resources:
                inst = info.get(r["id"]) if r["kind"] == "ec2_instance" else None
                if inst:
                    r["status"] = inst.get("State", {}).get("Name", "-")
                    r["details"].update({
                        "instance_id": inst["InstanceId"],
                        "instance_type": inst.get("InstanceType", ""),
                        "private_ip": inst.get("PrivateIpAddress", ""),
                        "public_ip": inst.get("PublicIpAddress", ""),
                        "availability_zone": inst.get("Placement", {}).get("AvailabilityZone", ""),
                        "vpc": inst.get("VpcId", ""),
                        "subnet": inst.get("SubnetId", ""),
                        "ami": inst.get("ImageId", ""),
                    })
        except Exception:
            pass

    # Enrich EBS volumes.
    if volume_ids:
        try:
            ec2 = session.client("ec2", config=cfg)
            vinfo = {}
            for i in range(0, len(volume_ids), 200):
                for v in ec2.describe_volumes(VolumeIds=volume_ids[i:i + 200]).get("Volumes", []):
                    vinfo[v["VolumeId"]] = v
            for r in resources:
                v = vinfo.get(r["id"]) if r["kind"] == "ebs_volume" else None
                if v:
                    att = v.get("Attachments", [])
                    r["status"] = v.get("State", "-")
                    r["details"].update({
                        "size_gb": v.get("Size"),
                        "volume_type": v.get("VolumeType", ""),
                        "device_name": att[0].get("Device", "") if att else "",
                        "attached_to": att[0].get("InstanceId", "") if att else "",
                        "availability_zone": v.get("AvailabilityZone", ""),
                    })
        except Exception:
            pass

    return account_id, resources


def _live_tag_options_sync(access_key, secret, region):
    session = _new_session(access_key, secret, region)
    cfg = _boto_cfg()
    tagging = session.client("resourcegroupstaggingapi", config=cfg)
    keys = []
    for page in tagging.get_paginator("get_tag_keys").paginate():
        keys.extend(page.get("TagKeys", []))
    values = {}
    for k in keys:
        vals = []
        try:
            for page in tagging.get_paginator("get_tag_values").paginate(Key=k):
                vals.extend(page.get("TagValues", []))
        except Exception:
            pass
        values[k] = sorted({v for v in vals if v})
    return sorted(set(keys)), values


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


def _test_connection_sync(access_key, secret, region):
    session = _new_session(access_key, secret, region)
    cfg = _boto_cfg()
    ident = session.client("sts", config=cfg).get_caller_identity()
    tagging = session.client("resourcegroupstaggingapi", config=cfg)
    # sample the first page of tagged resources in the region
    page = tagging.get_resources(ResourcesPerPage=100)
    sample = len(page.get("ResourceTagMappingList", []))
    return {"account_id": ident["Account"], "arn": ident.get("Arn", ""),
            "region": region, "sample_resource_count": sample}


@router.post("/test-connection")
async def test_connection(current=Depends(require_admin)):
    """Verify saved AWS credentials actually work and report account + a sample count."""
    s = await _get_settings()
    if not (s.get("access_key_id") and s.get("secret_access_key")):
        return {"ok": False, "error": "No AWS credentials saved. Enter an access key and secret, then Save first."}
    region = s.get("region", "us-east-1")
    import asyncio
    try:
        info = await asyncio.to_thread(
            _test_connection_sync, s["access_key_id"], s["secret_access_key"], region)
        return {"ok": True, "use_live": bool(s.get("use_live")), **info}
    except Exception as e:
        detail = ""
        try:
            if getattr(e, "response", None):
                detail = e.response["Error"].get("Message", "")
        except Exception:
            detail = ""
        return {"ok": False, "region": region,
                "error": f"{type(e).__name__}: {detail or str(e)[:300]}"}


def _instance_action_sync(access_key, secret, region, instance_id, action):
    session = _new_session(access_key, secret, region)
    cfg = _boto_cfg()
    ec2 = session.client("ec2", config=cfg)
    if action == "start":
        ec2.start_instances(InstanceIds=[instance_id])
    elif action == "stop":
        ec2.stop_instances(InstanceIds=[instance_id])
    else:
        raise ValueError("Invalid action")
    desc = ec2.describe_instances(InstanceIds=[instance_id])
    state = desc["Reservations"][0]["Instances"][0]["State"]["Name"]
    return state


class InstanceActionBody(BaseModel):
    instance_id: str
    action: Literal["start", "stop"]


@router.post("/instance-action")
async def instance_action(body: InstanceActionBody, current=Depends(require_admin)):
    s = await _get_settings()
    if not (s.get("use_live") and s.get("access_key_id") and s.get("secret_access_key")):
        raise HTTPException(status_code=400,
                            detail="Live AWS mode with valid credentials is required to control instances")
    import asyncio
    try:
        state = await asyncio.to_thread(
            _instance_action_sync, s["access_key_id"], s["secret_access_key"],
            s.get("region", "us-east-1"), body.instance_id, body.action)
        return {"ok": True, "instance_id": body.instance_id, "state": state}
    except Exception as e:
        detail = ""
        try:
            if getattr(e, "response", None):
                detail = e.response["Error"].get("Message", "")
        except Exception:
            detail = ""
        raise HTTPException(status_code=502,
                            detail=f"EC2 {body.action} failed: {type(e).__name__}: {detail or str(e)[:300]}")


@router.get("/tag-options")
async def tag_options():
    s = await _get_settings()
    if s.get("use_live") and s.get("access_key_id") and s.get("secret_access_key"):
        import asyncio
        try:
            keys, values = await asyncio.to_thread(
                _live_tag_options_sync, s["access_key_id"], s["secret_access_key"],
                s.get("region", "us-east-1"))
            return {"keys": keys, "values": values, "mode": "live"}
        except Exception:
            pass  # fall back to portal-derived tags if live lookup fails
    resources = await _collect_resources()
    keys = {}
    for r in resources:
        for k, v in (r.get("tags") or {}).items():
            keys.setdefault(k, set()).add(str(v))
    return {"keys": sorted(keys.keys()), "values": {k: sorted(v) for k, v in keys.items()}, "mode": "demo"}


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
            detail = ""
            try:
                if getattr(e, "response", None):
                    detail = e.response["Error"].get("Message", "")
            except Exception:
                detail = ""
            raise HTTPException(
                status_code=502,
                detail=f"AWS live discovery failed: {type(e).__name__}: {detail or str(e)[:300]}")

    # demo/mock
    resources = await _collect_resources()
    if tag_key:
        resources = [r for r in resources
                     if r.get("tags", {}).get(tag_key) == tag_value
                     or (not tag_value and tag_key in r.get("tags", {}))]
    return _summarize(resources, "demo", region, "DEMO-000000000000", tag_key, tag_value)

"""Generate Terraform HCL and Terraform JSON from inventory instances."""
import json
import re


class Raw(str):
    """A string that renders as an unquoted HCL reference / a ${...} JSON interpolation."""
    pass


def _slug(*parts):
    raw = "_".join(str(p) for p in parts if p)
    raw = re.sub(r"[^a-zA-Z0-9]+", "_", raw).strip("_").lower()
    if not raw:
        raw = "resource"
    if raw[0].isdigit():
        raw = "r_" + raw
    return raw


def _esc(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"')


def _hcl_tags(tags: dict, indent="    "):
    lines = ["  tags = {"]
    for k, v in tags.items():
        lines.append(f'    {k} = "{_esc(v)}"')
    lines.append("  }")
    return "\n".join(lines)


def _build_resources(instances, resources, zone_id, default_ami, default_instance_type,
                     dns_target="instance_private"):
    """Return dict-of-lists describing every terraform resource block.

    dns_target: how DNS A records resolve —
      'instance_private' -> reference the created aws_instance.private_ip
      'instance_public'  -> reference the created aws_instance.public_ip
      'host'             -> literal host IP from inventory
    """
    blocks = []
    used_names = set()

    def uniq(name):
        base = name
        i = 1
        while name in used_names:
            i += 1
            name = f"{base}_{i}"
        used_names.add(name)
        return name

    for ins in instances:
        host = ins.get("host") or ""
        name = ins.get("instance_name") or "instance"
        role = ins.get("instance_role") or ""
        port = ins.get("port")
        base_slug = _slug(name, host.replace(".", "_"))
        ec2_rname = None  # set when an EC2 resource is generated for this instance

        # EC2 — new instance is provisioned FROM this base instance's AMI
        if "ec2" in resources:
            ec2_rname = uniq(_slug("ec2", base_slug))
            tags = {"Name": name or host, "Role": role, "Host": host,
                    "Environment": ins.get("environment", ""),
                    "ManagedBy": "infra-portal"}
            # merge user-defined AWS tags + custom metadata
            for k, v in (ins.get("tags") or {}).items():
                tags[k] = v
            for k, v in (ins.get("custom_metadata") or {}).items():
                tags[k] = v
            tags = {k: v for k, v in tags.items() if v not in (None, "")}
            attrs = {
                "ami": ins.get("ami_id") or default_ami,
                "instance_type": ins.get("ec2_instance_type") or default_instance_type,
            }
            if ins.get("subnet_id"):
                attrs["subnet_id"] = ins["subnet_id"]
            if ins.get("key_name"):
                attrs["key_name"] = ins["key_name"]
            if ins.get("availability_zone"):
                attrs["availability_zone"] = ins["availability_zone"]
            if ins.get("iam_instance_profile"):
                attrs["iam_instance_profile"] = ins["iam_instance_profile"]
            sgs = [s for s in (ins.get("security_groups") or []) if s]
            if sgs:
                attrs["vpc_security_group_ids"] = sgs
            ebs = [v for v in (ins.get("ebs_volumes") or []) if v.get("device_name")]
            blocks.append({"type": "aws_instance", "name": ec2_rname,
                           "attrs": attrs, "tags": tags, "ebs": ebs})

        # Security group from port
        if "sg" in resources and port:
            rname = uniq(_slug("sg", base_slug))
            blocks.append({
                "type": "aws_security_group", "name": rname,
                "attrs": {
                    "name": f"{base_slug}_sg",
                    "description": f"Security group for {name or host} port {port}",
                },
                "vpc_id": ins.get("vpc_id") or None,
                "ingress": [{"from_port": port, "to_port": port,
                             "protocol": "tcp", "cidr_blocks": ["10.0.0.0/8"]}],
                "tags": {"Name": f"{base_slug}_sg", "ManagedBy": "infra-portal"},
            })

        # Route53 DNS (A records) — map to the CREATED instance, not the host IP
        if "dns" in resources:
            if dns_target in ("instance_private", "instance_public") and ec2_rname:
                attr = "private_ip" if dns_target == "instance_private" else "public_ip"
                record_val = [Raw(f"aws_instance.{ec2_rname}.{attr}")]
            else:
                record_val = [host] if host else ["0.0.0.0"]
            for dns in ins.get("dns_records", []):
                dns = dns.strip()
                if not dns:
                    continue
                rname = uniq(_slug("dns", dns.replace(".", "_")))
                blocks.append({
                    "type": "aws_route53_record", "name": rname,
                    "attrs": {
                        "zone_id": zone_id,
                        "name": dns,
                        "type": "A",
                        "ttl": 300,
                        "records": list(record_val),
                    },
                })

        # Route53 SRV records
        if "srv" in resources:
            for srv in ins.get("srv_records", []):
                srv = srv.strip()
                if not srv:
                    continue
                rname = uniq(_slug("srv", srv.replace(".", "_")))
                target = srv if srv.endswith(".") else srv + "."
                srv_value = f"0 5 {port or 3306} {target}"
                blocks.append({
                    "type": "aws_route53_record", "name": rname,
                    "attrs": {
                        "zone_id": zone_id,
                        "name": f"_service._tcp.{srv}",
                        "type": "SRV",
                        "ttl": 300,
                        "records": [srv_value],
                    },
                })

    return blocks


def _to_hcl(blocks):
    out = []
    out.append('terraform {\n  required_providers {\n    aws = {\n      source  = "hashicorp/aws"\n      version = "~> 5.0"\n    }\n  }\n}\n')
    out.append('provider "aws" {\n  region = var.aws_region\n}\n')
    out.append('variable "aws_region" {\n  type    = string\n  default = "us-east-1"\n}\n')

    for b in blocks:
        lines = [f'resource "{b["type"]}" "{b["name"]}" {{']
        for k, v in b["attrs"].items():
            lines.append(f"  {_hcl_val(k, v)}")
        if b.get("vpc_id"):
            lines.append(f'  vpc_id = "{_esc(b["vpc_id"])}"')
        for ing in b.get("ingress", []):
            lines.append("  ingress {")
            lines.append(f'    from_port   = {ing["from_port"]}')
            lines.append(f'    to_port     = {ing["to_port"]}')
            lines.append(f'    protocol    = "{ing["protocol"]}"')
            cidrs = json.dumps(ing["cidr_blocks"])
            lines.append(f'    cidr_blocks = {cidrs}')
            lines.append("  }")
        for vol in b.get("ebs", []):
            lines.append("  ebs_block_device {")
            lines.append(f'    device_name = "{_esc(vol.get("device_name",""))}"')
            if vol.get("size_gb"):
                lines.append(f'    volume_size = {int(vol["size_gb"])}')
            lines.append(f'    volume_type = "{_esc(vol.get("volume_type") or "gp3")}"')
            lines.append("  }")
        if b.get("tags"):
            lines.append(_hcl_tags(b["tags"]))
        lines.append("}")
        out.append("\n".join(lines) + "\n")
    return "\n".join(out)


def _hcl_list(v):
    parts = []
    for x in v:
        if isinstance(x, Raw):
            parts.append(str(x))
        elif isinstance(x, (int, float)) and not isinstance(x, bool):
            parts.append(str(x))
        else:
            parts.append(f'"{_esc(x)}"')
    return "[" + ", ".join(parts) + "]"


def _hcl_val(key, v):
    if isinstance(v, Raw):
        return f"{key} = {v}"
    if isinstance(v, bool):
        return f"{key} = {str(v).lower()}"
    if isinstance(v, int):
        return f"{key} = {v}"
    if isinstance(v, list):
        return f"{key} = {_hcl_list(v)}"
    return f'{key} = "{_esc(v)}"'


def _jsonify(obj):
    """Convert Raw references to ${...} interpolation strings recursively."""
    if isinstance(obj, Raw):
        return "${" + str(obj) + "}"
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonify(x) for x in obj]
    return obj


def _to_tf_json(blocks):
    resource = {}
    for b in blocks:
        rtype = b["type"]
        body = dict(b["attrs"])
        if b.get("vpc_id"):
            body["vpc_id"] = b["vpc_id"]
        if b.get("ingress"):
            body["ingress"] = b["ingress"]
        if b.get("ebs"):
            body["ebs_block_device"] = [
                {"device_name": v.get("device_name", ""),
                 "volume_size": int(v["size_gb"]) if v.get("size_gb") else None,
                 "volume_type": v.get("volume_type") or "gp3"}
                for v in b["ebs"]
            ]
        if b.get("tags"):
            body["tags"] = b["tags"]
        resource.setdefault(rtype, {})[b["name"]] = _jsonify(body)
    doc = {
        "terraform": {
            "required_providers": {
                "aws": {"source": "hashicorp/aws", "version": "~> 5.0"}
            }
        },
        "provider": {"aws": {"region": "${var.aws_region}"}},
        "variable": {"aws_region": {"type": "string", "default": "us-east-1"}},
        "resource": resource,
    }
    return json.dumps(doc, indent=2)


def generate_terraform(instances, resources, output_format, zone_id,
                       default_ami, default_instance_type,
                       dns_target="instance_private"):
    blocks = _build_resources(instances, resources, zone_id,
                              default_ami, default_instance_type, dns_target)
    result = {"resource_count": len(blocks)}
    if output_format in ("hcl", "both"):
        result["hcl"] = _to_hcl(blocks)
    if output_format in ("json", "both"):
        result["json"] = _to_tf_json(blocks)
    return result

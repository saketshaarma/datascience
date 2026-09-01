"""Generate the K8s cluster config JSON and provisioning Terraform (HCL)."""
import json
import re


def _esc(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"')


def _ident(v):
    raw = re.sub(r"[^a-zA-Z0-9_]+", "_", str(v)).strip("_").lower() or "node"
    if raw[0].isdigit():
        raw = "n_" + raw
    return raw


def _tag_key(k):
    # HCL map keys with special chars must be quoted; keep simple keys bare
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", str(k)):
        return str(k)
    return f'"{_esc(k)}"'


def build_config_json(doc: dict) -> dict:
    """Return the exact cluster config JSON structure."""
    nodes = {}
    for i, n in enumerate(doc.get("nodes", []), start=1):
        nodes[f"node{i}"] = {
            "hostname": n.get("hostname", ""),
            "instance_type": n.get("instance_type", "t3.medium"),
            "root_volume_size": int(n.get("root_volume_size") or 0),
        }
    cfg = {
        "aws_region": doc.get("aws_region", ""),
        "vpc_tag": doc.get("vpc_tag", ""),
        "subnet_tag": doc.get("subnet_tag", ""),
        "key_name": doc.get("key_name", ""),
        "private_zone_name": doc.get("private_zone_name", ""),
        "security_group_tags": doc.get("security_group_tags", {}) or {},
        "instance_tags": doc.get("instance_tags", {}) or {},
        "volume_tags": doc.get("volume_tags", {}) or {},
        "nodes": nodes,
    }
    for k, v in (doc.get("extra") or {}).items():
        cfg[k] = v
    return cfg


def _hcl_map(d: dict, indent: str) -> str:
    if not d:
        return "{}"
    lines = ["{"]
    for k, v in d.items():
        lines.append(f'{indent}  {_tag_key(k)} = "{_esc(v)}"')
    lines.append(indent + "}")
    return "\n".join(lines)


def build_terraform_hcl(doc: dict) -> str:
    name = doc.get("name") or "k8s"
    slug = _ident(name)
    region = doc.get("aws_region") or "us-east-1"
    vpc_tag = doc.get("vpc_tag") or ""
    subnet_tag = doc.get("subnet_tag") or ""
    key_name = doc.get("key_name") or ""
    zone = doc.get("private_zone_name") or ""
    sg_tags = doc.get("security_group_tags") or {}
    inst_tags = doc.get("instance_tags") or {}
    vol_tags = doc.get("volume_tags") or {}
    ami = doc.get("ami_id") or ""
    nodes = doc.get("nodes") or []

    out = []
    out.append(
        'terraform {\n  required_providers {\n    aws = {\n'
        '      source  = "hashicorp/aws"\n      version = "~> 5.0"\n    }\n  }\n}\n'
    )
    out.append(f'provider "aws" {{\n  region = "{_esc(region)}"\n}}\n')
    out.append(f'variable "ami_id" {{\n  type    = string\n  default = "{_esc(ami)}"\n}}\n')

    out.append(
        "locals {\n"
        f"  instance_tags       = {_hcl_map(inst_tags, '  ')}\n"
        f"  volume_tags         = {_hcl_map(vol_tags, '  ')}\n"
        f"  security_group_tags = {_hcl_map(sg_tags, '  ')}\n"
        "}\n"
    )

    if vpc_tag:
        out.append(
            'data "aws_vpc" "selected" {\n'
            f'  tags = {{\n    Name = "{_esc(vpc_tag)}"\n  }}\n}}\n'
        )
    if subnet_tag:
        out.append(
            'data "aws_subnet" "selected" {\n'
            f'  tags = {{\n    Name = "{_esc(subnet_tag)}"\n  }}\n}}\n'
        )
    if zone:
        out.append(
            'data "aws_route53_zone" "private" {\n'
            f'  name         = "{_esc(zone)}"\n  private_zone = true\n}}\n'
        )

    vpc_ref = "data.aws_vpc.selected.id" if vpc_tag else '""'
    subnet_ref = "data.aws_subnet.selected.id" if subnet_tag else '""'

    # security group
    sg_lines = [f'resource "aws_security_group" "{slug}_sg" {{']
    sg_lines.append(f'  name = "{_esc(name)}-sg"')
    if vpc_tag:
        sg_lines.append(f"  vpc_id = {vpc_ref}")
    sg_lines.append("  ingress {")
    sg_lines.append("    description = \"intra-cluster\"")
    sg_lines.append("    from_port   = 0")
    sg_lines.append("    to_port     = 0")
    sg_lines.append('    protocol    = "-1"')
    sg_lines.append("    self        = true")
    sg_lines.append("  }")
    sg_lines.append("  egress {")
    sg_lines.append("    from_port   = 0")
    sg_lines.append("    to_port     = 0")
    sg_lines.append('    protocol    = "-1"')
    sg_lines.append('    cidr_blocks = ["0.0.0.0/0"]')
    sg_lines.append("  }")
    sg_lines.append(f'  tags = merge(local.security_group_tags, {{ Name = "{_esc(name)}-sg" }})')
    sg_lines.append("}\n")
    out.append("\n".join(sg_lines))

    # nodes
    for i, n in enumerate(nodes, start=1):
        rname = f"node{i}"
        hostname = n.get("hostname") or rname
        itype = n.get("instance_type") or "t3.medium"
        vsize = int(n.get("root_volume_size") or 50)
        lines = [f'resource "aws_instance" "{rname}" {{']
        lines.append("  ami           = var.ami_id")
        lines.append(f'  instance_type = "{_esc(itype)}"')
        if key_name:
            lines.append(f'  key_name      = "{_esc(key_name)}"')
        if subnet_tag:
            lines.append(f"  subnet_id     = {subnet_ref}")
        lines.append(f"  vpc_security_group_ids = [aws_security_group.{slug}_sg.id]")
        lines.append("  root_block_device {")
        lines.append(f"    volume_size = {vsize}")
        lines.append('    volume_type = "gp3"')
        lines.append(f'    tags        = merge(local.volume_tags, {{ Name = "{_esc(hostname)}-root" }})')
        lines.append("  }")
        lines.append(f'  tags = merge(local.instance_tags, {{ Name = "{_esc(hostname)}" }})')
        lines.append("}\n")
        out.append("\n".join(lines))

        if zone:
            r = [f'resource "aws_route53_record" "{rname}_dns" {{']
            r.append("  zone_id = data.aws_route53_zone.private.zone_id")
            r.append(f'  name    = "{_esc(hostname)}.{_esc(zone)}"')
            r.append('  type    = "A"')
            r.append("  ttl     = 300")
            r.append(f"  records = [aws_instance.{rname}.private_ip]")
            r.append("}\n")
            out.append("\n".join(r))

    return "\n".join(out)


def generate_k8s(doc: dict) -> dict:
    return {
        "config_json": json.dumps(build_config_json(doc), indent=2),
        "hcl": build_terraform_hcl(doc),
    }

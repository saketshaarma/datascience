"""Generate a non-Kubernetes workload spec JSON + a MODULAR Terraform project.

Mirrors the Kubernetes generator but targets standalone servers: each node is a
generic EC2 instance that can carry a role, a root volume and any number of extra
data (EBS) volumes, an optional private Route53 record, and a security group whose
ingress is driven by an explicit port list.

Output files:
  config.json            - the workload spec (nodes keyed node1..nodeN)
  provider.tf            - terraform + provider blocks
  variables.tf           - variable declarations
  main.tf                - data sources + resources (for_each over var.nodes)
  outputs.tf             - useful outputs
  terraform.tfvars.json  - variable values for this workload
  userdata.sh.tpl        - per-node bootstrap template
"""
import json


def _volumes(node: dict) -> list:
    out = []
    for v in node.get("data_volumes", []) or []:
        dev = (v.get("device_name") or "").strip()
        if not dev:
            continue
        out.append({
            "device_name": dev,
            "size_gb": int(v.get("size_gb") or 0),
            "volume_type": v.get("volume_type", "gp3") or "gp3",
        })
    return out


def build_config_json(doc: dict) -> dict:
    nodes = {}
    for i, n in enumerate(doc.get("nodes", []), start=1):
        nodes[f"node{i}"] = {
            "hostname": n.get("hostname", ""),
            "role": n.get("role", ""),
            "instance_type": n.get("instance_type", "t3.medium"),
            "root_volume_size": int(n.get("root_volume_size") or 0),
            "data_volumes": _volumes(n),
        }
    cfg = {
        "aws_region": doc.get("aws_region", ""),
        "vpc_tag": doc.get("vpc_tag", ""),
        "subnet_tag": doc.get("subnet_tag", ""),
        "key_name": doc.get("key_name", ""),
        "enable_dns": bool(doc.get("enable_dns", False)),
        "private_zone_name": doc.get("private_zone_name", ""),
        "ingress_ports": [int(p) for p in (doc.get("ingress_ports") or []) if str(p).strip()],
        "security_group_tags": doc.get("security_group_tags", {}) or {},
        "instance_tags": doc.get("instance_tags", {}) or {},
        "volume_tags": doc.get("volume_tags", {}) or {},
        "nodes": nodes,
    }
    for k, v in (doc.get("extra") or {}).items():
        cfg[k] = v
    return cfg


def build_tfvars(doc: dict) -> dict:
    cfg = build_config_json(doc)
    tfvars = {
        "workload_name": doc.get("name", "workload"),
        "aws_region": cfg["aws_region"],
        "ami_id": doc.get("ami_id", ""),
        "key_name": cfg["key_name"],
        "vpc_tag": cfg["vpc_tag"],
        "subnet_tag": cfg["subnet_tag"],
        "enable_dns": cfg["enable_dns"],
        "private_zone_name": cfg["private_zone_name"],
        "ingress_ports": cfg["ingress_ports"],
        "security_group_tags": cfg["security_group_tags"],
        "instance_tags": cfg["instance_tags"],
        "volume_tags": cfg["volume_tags"],
        "nodes": cfg["nodes"],
    }
    for k, v in (doc.get("extra") or {}).items():
        tfvars[k] = v
    return tfvars


PROVIDER_TF = '''terraform {
  required_version = ">= 1.3.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}
'''

VARIABLES_TF = '''variable "workload_name" {
  description = "Logical name of the workload (used for the security group)"
  type        = string
}

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
}

variable "ami_id" {
  description = "AMI used for every node"
  type        = string
}

variable "key_name" {
  description = "EC2 key pair name"
  type        = string
  default     = ""
}

variable "vpc_tag" {
  description = "Value of the Name tag used to look up the target VPC"
  type        = string
}

variable "subnet_tag" {
  description = "Value of the Name tag used to look up the target subnet"
  type        = string
}

variable "enable_dns" {
  description = "Whether to create private Route53 A records for each node"
  type        = bool
  default     = false
}

variable "private_zone_name" {
  description = "Route53 private hosted zone name (required when enable_dns = true)"
  type        = string
  default     = ""
}

variable "ingress_ports" {
  description = "TCP ports to open on the workload security group (0.0.0.0/0)"
  type        = list(number)
  default     = []
}

variable "security_group_tags" {
  description = "Tags applied to the workload security group"
  type        = map(string)
  default     = {}
}

variable "instance_tags" {
  description = "Tags applied to every node instance"
  type        = map(string)
  default     = {}
}

variable "volume_tags" {
  description = "Tags applied to every volume"
  type        = map(string)
  default     = {}
}

variable "nodes" {
  description = "Map of nodes to provision"
  type = map(object({
    hostname         = string
    role             = string
    instance_type    = string
    root_volume_size = number
    data_volumes = list(object({
      device_name = string
      size_gb     = number
      volume_type = string
    }))
  }))
}
'''

MAIN_TF = '''data "aws_vpc" "selected" {
  tags = {
    Name = var.vpc_tag
  }
}

data "aws_subnet" "selected" {
  tags = {
    Name = var.subnet_tag
  }
}

data "aws_route53_zone" "private" {
  count        = var.enable_dns ? 1 : 0
  name         = var.private_zone_name
  private_zone = true
}

locals {
  # Flatten every node's data volumes into a single map keyed "<node>-<device>".
  node_volumes = merge([
    for nk, n in var.nodes : {
      for v in n.data_volumes :
      "${nk}-${replace(v.device_name, "/", "_")}" => {
        node        = nk
        device_name = v.device_name
        size_gb     = v.size_gb
        volume_type = v.volume_type
      }
    }
  ]...)
}

resource "aws_security_group" "workload" {
  name        = "${var.workload_name}-sg"
  description = "Security group for ${var.workload_name} workload nodes"
  vpc_id      = data.aws_vpc.selected.id

  dynamic "ingress" {
    for_each = var.ingress_ports
    content {
      description = "Port ${ingress.value}"
      from_port   = ingress.value
      to_port     = ingress.value
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  ingress {
    description = "Intra-workload traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.security_group_tags, {
    Name = "${var.workload_name}-sg"
  })
}

resource "aws_instance" "node" {
  for_each = var.nodes

  ami                    = var.ami_id
  instance_type          = each.value.instance_type
  key_name               = var.key_name != "" ? var.key_name : null
  subnet_id              = data.aws_subnet.selected.id
  vpc_security_group_ids = [aws_security_group.workload.id]

  user_data = templatefile("${path.module}/userdata.sh.tpl", {
    hostname      = each.value.hostname
    role          = each.value.role
    workload_name = var.workload_name
  })

  root_block_device {
    volume_size = each.value.root_volume_size
    volume_type = "gp3"
    tags = merge(var.volume_tags, {
      Name = "${each.value.hostname}-root"
    })
  }

  tags = merge(var.instance_tags, {
    Name = each.value.hostname
    Role = each.value.role
  })
}

resource "aws_ebs_volume" "data" {
  for_each = local.node_volumes

  availability_zone = aws_instance.node[each.value.node].availability_zone
  size              = each.value.size_gb
  type              = each.value.volume_type

  tags = merge(var.volume_tags, {
    Name = each.key
  })
}

resource "aws_volume_attachment" "data" {
  for_each = local.node_volumes

  device_name = each.value.device_name
  volume_id   = aws_ebs_volume.data[each.key].id
  instance_id = aws_instance.node[each.value.node].id
}

resource "aws_route53_record" "node" {
  for_each = var.enable_dns ? var.nodes : {}

  zone_id = data.aws_route53_zone.private[0].zone_id
  name    = "${each.value.hostname}.${var.private_zone_name}"
  type    = "A"
  ttl     = 300
  records = [aws_instance.node[each.key].private_ip]
}
'''

OUTPUTS_TF = '''output "instance_ids" {
  description = "Map of node key => EC2 instance id"
  value       = { for k, n in aws_instance.node : k => n.id }
}

output "private_ips" {
  description = "Map of node key => private IP"
  value       = { for k, n in aws_instance.node : k => n.private_ip }
}

output "data_volume_ids" {
  description = "Map of volume key => EBS volume id"
  value       = { for k, v in aws_ebs_volume.data : k => v.id }
}

output "node_fqdns" {
  description = "Map of node key => private DNS FQDN (empty when DNS disabled)"
  value       = { for k, r in aws_route53_record.node : k => r.fqdn }
}

output "security_group_id" {
  description = "Workload security group id"
  value       = aws_security_group.workload.id
}
'''

USERDATA_TPL = '''#!/bin/bash
set -euo pipefail

# Bootstrap for node: ${hostname} (role: ${role}, workload: ${workload_name})
hostnamectl set-hostname "${hostname}"
echo "127.0.0.1 ${hostname}" >> /etc/hosts

if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y ca-certificates curl
else
  yum install -y ca-certificates curl || true
fi

# TODO: add role-specific provisioning for "${role}" here.
echo "userdata bootstrap complete for ${hostname}"
'''


def generate_workload(doc: dict) -> dict:
    files = {
        "provider.tf": PROVIDER_TF,
        "variables.tf": VARIABLES_TF,
        "main.tf": MAIN_TF,
        "outputs.tf": OUTPUTS_TF,
        "terraform.tfvars.json": json.dumps(build_tfvars(doc), indent=2),
        "userdata.sh.tpl": USERDATA_TPL,
    }
    return {
        "config_json": json.dumps(build_config_json(doc), indent=2),
        "files": files,
    }

"""Generate the K8s cluster spec JSON + a MODULAR Terraform project.

Output files:
  cluster.json           - the cluster spec (nodes keyed node1..nodeN)
  provider.tf            - terraform + provider blocks
  variables.tf           - variable declarations
  main.tf                - data sources + resources (for_each over var.nodes)
  outputs.tf             - useful outputs
  terraform.tfvars.json  - variable values for this cluster
  userdata.sh.tpl        - per-node bootstrap template
"""
import json


def build_config_json(doc: dict) -> dict:
    """The cluster spec JSON (nodes keyed node1, node2, ...)."""
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


def build_tfvars(doc: dict) -> dict:
    """Variable values consumed by variables.tf (terraform.tfvars.json)."""
    cfg = build_config_json(doc)
    tfvars = {
        "cluster_name": doc.get("name", "k8s-cluster"),
        "aws_region": cfg["aws_region"],
        "ami_id": doc.get("ami_id", ""),
        "key_name": cfg["key_name"],
        "vpc_tag": cfg["vpc_tag"],
        "subnet_tag": cfg["subnet_tag"],
        "private_zone_name": cfg["private_zone_name"],
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

VARIABLES_TF = '''variable "cluster_name" {
  description = "Logical name of the cluster (used for the security group)"
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

variable "private_zone_name" {
  description = "Route53 private hosted zone name"
  type        = string
}

variable "security_group_tags" {
  description = "Tags applied to the cluster security group"
  type        = map(string)
  default     = {}
}

variable "instance_tags" {
  description = "Tags applied to every node instance"
  type        = map(string)
  default     = {}
}

variable "volume_tags" {
  description = "Tags applied to every root volume"
  type        = map(string)
  default     = {}
}

variable "nodes" {
  description = "Map of nodes to provision"
  type = map(object({
    hostname         = string
    instance_type    = string
    root_volume_size = number
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
  name         = var.private_zone_name
  private_zone = true
}

resource "aws_security_group" "cluster" {
  name        = "${var.cluster_name}-sg"
  description = "Security group for ${var.cluster_name} cluster nodes"
  vpc_id      = data.aws_vpc.selected.id

  ingress {
    description = "Intra-cluster traffic"
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
    Name = "${var.cluster_name}-sg"
  })
}

resource "aws_instance" "node" {
  for_each = var.nodes

  ami                    = var.ami_id
  instance_type          = each.value.instance_type
  key_name               = var.key_name != "" ? var.key_name : null
  subnet_id              = data.aws_subnet.selected.id
  vpc_security_group_ids = [aws_security_group.cluster.id]

  user_data = templatefile("${path.module}/userdata.sh.tpl", {
    hostname     = each.value.hostname
    cluster_name = var.cluster_name
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
  })
}

resource "aws_route53_record" "node" {
  for_each = var.nodes

  zone_id = data.aws_route53_zone.private.zone_id
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

output "node_fqdns" {
  description = "Map of node key => private DNS FQDN"
  value       = { for k, r in aws_route53_record.node : k => r.fqdn }
}

output "security_group_id" {
  description = "Cluster security group id"
  value       = aws_security_group.cluster.id
}
'''

USERDATA_TPL = '''#!/bin/bash
set -euo pipefail

# Bootstrap for Kubernetes node: ${hostname} (cluster: ${cluster_name})
hostnamectl set-hostname "${hostname}"
echo "127.0.0.1 ${hostname}" >> /etc/hosts

# Base packages
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y apt-transport-https ca-certificates curl gnupg
else
  yum install -y ca-certificates curl
fi

# Kernel prerequisites for kubelet / containerd
cat <<EOF >/etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.ipv4.ip_forward                 = 1
EOF
sysctl --system || true

# TODO: install containerd, kubeadm, kubelet & kubectl and join/init the cluster.
echo "userdata bootstrap complete for ${hostname}"
'''


def generate_k8s(doc: dict) -> dict:
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

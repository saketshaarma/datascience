# InfraForge — AWS Infrastructure Inventory & Terraform Generator Portal

## Original Problem Statement
Internal web-based portal to maintain a centralized inventory of infrastructure metadata
(hosts, ports, instance roles, DNS records, SRV records, AWS EC2 details such as instance
type & AMI, networking info) and automatically generate Terraform configuration (HCL and
Terraform JSON) that can be reviewed and used to provision the corresponding AWS
infrastructure. Acts as the central source of truth for DevOps/Infrastructure teams.

## User Choices
- No authentication (open internal tool)
- CSV bulk upload + manual add/edit
- Generate all resource types: EC2, Route53 DNS (A), Route53 SRV, Security Groups
- Output in both HCL and Terraform JSON

## Architecture
- **Backend**: FastAPI + MongoDB (motor). Routes under `/api`.
  - Instances CRUD, grouped-CSV import, stats, terraform generation.
  - `terraform_generator.py` renders aws_instance, aws_security_group, aws_route53_record (A + SRV) in HCL and Terraform JSON.
- **Frontend**: React (CRA + craco), react-router, Tailwind, shadcn/ui, recharts, sonner.
  - Dark "command-center" theme (Signal Orange accent), IBM Plex Sans / Inter / JetBrains Mono.
  - Pages: Dashboard, Inventory, DNS & SRV, Terraform Generator.

## User Personas
- DevOps / Infrastructure engineers maintaining AWS infra metadata and provisioning via Terraform.

## Core Requirements (static)
- Centralized inventory of hosts/instances with full metadata.
- Import existing inventory from CSV (grouped format where continuation rows carry DNS/SRV).
- Manual add/edit/delete of instances.
- Auto-generate reviewable Terraform (HCL + JSON) for selected resources & instances.

## Implemented (2026-06)
- Instance data model: instance_name, host, port, instance_role, ec2_instance_type, ami_id, region, AZ, vpc_id, subnet_id, key_name, dns_records[], srv_records[], tags, notes.
- CRUD APIs + search; stats API (role & type breakdown).
- CSV import parser handling grouped format (verified: 5 hosts, 54 DNS, 4 SRV from sample).
- Terraform generator: EC2, Security Groups (from ports), Route53 A + SRV records; HCL string escaping; both HCL and Terraform JSON output; per-instance/resource selection; configurable zone id, default AMI, default instance type.
- Dashboard (stat cards + pie/bar charts), Inventory table (search, add/edit dialog, CSV upload dropzone, delete w/ confirm), DNS & SRV browser (tabs + filter), Generator (config panel + syntax-highlighted HCL/JSON with copy & download).
- Tested end-to-end: 100% backend (11/11 pytest) and frontend pass.

## Backlog / Remaining
- P1: File-size/content-type validation on CSV upload; safeguard on bulk delete-all.
- P2: Export inventory to CSV; VPC/subnet resource generation; multi-zone Route53 mapping; migrate `on_event` to lifespan handler.
- P2: Optional authentication if the tool moves outside the internal network.

## Next Tasks
- Awaiting user review of the initial portal and their own CSV import.

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

## Implemented (2026-06) — Iteration 2
- **Team login (JWT)**: email/password auth, admin-seeded account, Bearer + httpOnly cookies, brute-force lockout (keyed by email, 5 attempts / 15 min). All data routes protected. `/team` page for admins to add/remove members.
- **Extended instance fields**: environment, region, EC2 instance ID, instance type, AMI, VPC, subnet, availability zone, private IP, public IP, security groups[], IAM instance profile, EBS volumes[], AWS tags{}, custom metadata{}.
- **CSV export** (GET /api/instances/export) with all columns; **upload safeguards** (.csv only, 5 MB max); **delete-all safeguard** (requires confirm=DELETE_ALL).
- Terraform EC2 blocks now emit private_ip, availability_zone, iam_instance_profile, vpc_security_group_ids, ebs_block_device, and merged Environment + AWS tags + custom metadata.
- Tested: 100% backend (20/20 pytest) and frontend pass.

## Credentials
- Admin: `admin@infraforge.io` / `Admin@12345` (see /app/memory/test_credentials.md)

## Implemented (2026-06) — Iteration 3
- **Base-instance semantics**: each Host_Port row is a base instance whose **AMI drives creation** of a new EC2 instance (`aws_instance.ami = inventory ami_id`).
- **DNS maps to created instance**: Route53 A records now reference the created instance's IP (`aws_instance.<name>.private_ip` / `.public_ip`) instead of the static host IP. Configurable via a "DNS maps to" selector (private / public / host literal). Falls back to literal host IP when EC2 isn't in the selected resources.
- **Export all as JSON**: one-click button generates Terraform JSON for the entire inventory (all resources) and downloads `main.tf.json`.
- Added `Raw` reference type in the generator (unquoted in HCL, `${...}` in JSON). Tested: 28/28 backend, 100% frontend.

## Implemented (2026-06) — Iteration 4
- **Admin-only deletes**: single delete and delete-all require admin role (`require_admin`, 403 for members); frontend hides delete buttons for non-admins.
- **Host:Port uniqueness**: create/update reject duplicate host:port (409); CSV import skips duplicates (returns `{imported, skipped}`).
- **One EC2 per host**: Terraform generator groups instances by host — a host with multiple ports yields ONE `aws_instance`, ONE security group with an ingress rule per distinct port, aggregated DNS A records referencing that single instance, and SRV records each keyed to their own port.
- **Full Terraform JSON export** also available on the Inventory page ("Export JSON").
- Tested: 41/41 backend, 100% frontend.

## Implemented (2026-06) — Iteration 5
- **Kubernetes Provisioning panel** (`/kubernetes`): define a cluster spec — aws_region, vpc_tag, subnet_tag, key_name, private_zone_name, AMI, plus security_group_tags / instance_tags / volume_tags (key=value) and a list of nodes (hostname / instance_type / root_volume_size).
- Generates the **exact cluster config JSON** (nodes keyed `node1`, `node2`, …) plus provisioning **Terraform HCL**: `aws_vpc`/`aws_subnet`/`aws_route53_zone` data sources, `locals` for tags, one `aws_security_group`, per-node `aws_instance` with `root_block_device` + merged tags, and per-node private `aws_route53_record` (`<hostname>.<zone>` → instance private_ip).
- Save/load/delete cluster configs (delete admin-only) in a separate `k8s_clusters` collection.
- Backend: `k8s_generator.py`, endpoints `/api/k8s/clusters` CRUD + `/generate` + `/preview`. Tested: 12/12 backend, 100% frontend.

## Implemented (2026-06) — Iteration 6
- **DB Config panel** (`/db-config`): relational model — `db_services` (unique name), `db_instances` (service FK, host, port, instance_type, unique aws_instance_id, all_dns, srv_record, aws_region, environment enum DEV/QA/UAT/DR/PROD, status enum Running/Stopped/Terminated, timestamps), and `db_instance_metadata` (key/value per instance, embedded, unique per key).
- Manage services (add/rename/delete) and instances with a metadata attribute editor; edit rights via dialog; delete admin-only; service delete blocked while it has instances.
- **Excel (.xlsx) import**: auto-creates missing services, maps known columns, turns any extra columns into metadata attributes, skips duplicate aws_instance_id; returns `{imported, skipped}`.
- **JSON export** in the exact relational shape (`db_services` / `db_instances` / `db_instance_metadata`) with integer ids and FK references.
- Backend: `db_config.py` (`/api/db/*`), openpyxl added. Tested: 17/17 backend, 100% frontend.

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

## Implemented (2026-06) — Iteration 7 & 8
- **Kubernetes page redesigned as a 4-step wizard** (Cluster → Tags → Nodes → Review) with a progress stepper, framer-motion transitions, key-value tag editors, node cards with controller/etcd/worker presets, and a review summary. Tested 100% frontend.
- **Modular Terraform output**: the K8s generator now emits a full project instead of a flat file — `provider.tf`, `variables.tf`, `main.tf` (data sources + `for_each` over `var.nodes` + `templatefile` userdata), `outputs.tf`, `terraform.tfvars.json` (all values incl. cluster_name/ami/tags/nodes), and `userdata.sh.tpl` — plus the `cluster.json` spec. Wizard shows each file in its own tab with copy/download and a "Download all" action.

## Implemented (2026-06) — Iteration 9
- **Discovery Dashboard**: aggregates every resource across Inventory + DB Config + Kubernetes into a unified AWS discovery view (EC2, EBS, security groups, Route53, RDS/DB), filterable by a selectable tag key + value; summary cards, by-source pie, resource table, DEMO/LIVE mode badge.
- **AWS connection settings** (admin, Team page): access key / secret / region + live-mode toggle (off = demo/mock, on = boto3 Resource Groups Tagging API). Secret write-only, returned masked.
- Backend: `aws_discovery.py` (`/api/aws/tag-options|discover|settings`), boto3 added. Tested: 14/14 backend, 100% frontend. Runs in DEMO/MOCK mode until real creds + live mode enabled.

## Implemented (2026-06) — Iteration 10
- **Type-driven Discovery Dashboard**: five selectable type cards (EC2 Instances, Security Groups, Volumes, Route53 Zones, A Records) with live counts; selecting a type shows a table with type-specific columns (EC2: instance id, private IP, type; A record: value, ttl, zone; volume: device/size; zone: record count).
- **Hover popups**: hovering a resource opens a rich detail card (full `details` grid + all tags + source/region).
- Backend now emits richer resources with a `details` object and adds `route53_zone` (derived from A-record domains + k8s private zones) and `a_record` kinds. Tag filter (key/value) narrows all types. Tested: 100% backend + frontend.

## Implemented (2026-06) — Iteration 11: Self-Hosting Artifacts
- **Docker Compose** (`docker-compose.yml` + `.env.example`): one-command stack — Nginx frontend + FastAPI backend + MongoDB 7 (named volume `mongo_data`). Frontend proxies `/api` to backend (same-origin, no CORS).
- **Backend image** (`backend/Dockerfile`): python:3.11-slim, installs requirements incl. emergentintegrations via extra index, runs uvicorn on 8001, `/api/health` healthcheck.
- **Frontend image** (`frontend/Dockerfile` + `nginx.conf.template`): multi-stage node:20 build → nginx:1.27-alpine. Built with empty `REACT_APP_BACKEND_URL` so app calls `/api` same-origin; Nginx envsubst injects `BACKEND_HOST` into the `/api` proxy (NGINX_ENVSUBST_FILTER=BACKEND_HOST).
- **Kubernetes manifests** (`k8s/00..40`): namespace, Secret (JWT/admin), ConfigMap, Mongo (PVC+Deployment+Service), backend Deployment+Service, frontend Deployment+Service, optional Ingress (nginx). All 8 YAMLs validated.
- **DEPLOYMENT.md**: full self-hosting guide (Compose + K8s), config reference table, external/managed Mongo notes.
- NOTE: could not run `docker build` in preview (no Docker daemon); YAML + build inputs validated, build steps mirror the working craco/pip flow.

## Implemented (2026-06) — Iteration 12: Non-K8s Workloads + Live Discovery fixes
- **NEW: Non-Kubernetes Workloads** (`/workloads`, sidebar): 4-step wizard (Workload → Tags → Nodes → Review) mirroring the K8s wizard for standalone servers. Per-node: hostname, role, instance_type, root volume, and multiple data EBS volumes (device/size/type). Plus ingress ports and optional private Route53 DNS toggle. Generates `config.json` + modular Terraform (`provider/variables/main/outputs/terraform.tfvars.json/userdata.sh.tpl`) with flattened `local.node_volumes` for aws_ebs_volume+aws_volume_attachment, dynamic SG ingress, conditional route53. Save/load/delete named configs (`workloads` collection). Backend: `workloads_generator.py`, `/api/workloads*` CRUD + preview + generate. Tested 11/11 backend + full frontend.
- **FIX: Live AWS discovery not showing all tagged resources** — removed the hardcoded `ResourceTypeFilters` (was only ec2:instance/volume/security-group + rds:db), so ALL tagged resource types in the region now return (VPC, subnet, route-table, gateways, ELB, IAM, etc.). Added `_parse_arn`/`_kind_from_arn`, EC2 instance & volume enrichment (private IP, type, size, attachment), and region/details on every live resource.
- **Live tag options**: `/api/aws/tag-options` now pulls real tag keys/values from AWS (get_tag_keys/get_tag_values) when live mode is on, so the dashboard dropdowns reflect the actual account. Returns a `mode` field.
- **AWS Test Connection**: new `POST /api/aws/test-connection` (admin) does sts:GetCallerIdentity + a sample get_resources and reports account/region/sample-count or the REAL AWS error. Team page shows LIVE/DEMO badge, a "keys saved but live is OFF" warning, and a Test Connection button with a result strip.
- **Dashboard**: renders every discovered resource kind dynamically (unknown kinds get a generic table), added an "RDS Databases" type card, and surfaces the real 502 error message from failed live discovery.
- NOTE: The user's "not showing" issue was on their DEPLOYED instance where the badge read DEMO MODE (live toggle off) AND it runs pre-fix code — they must enable Live discovery and redeploy the images to pick up the resource-type fix.

## Update (2026-06) — Live discovery UX
- Root cause of user's "still demo mode": credentials were valid (Test Connection returned account + 100 resources) but `use_live` was OFF, so /api/aws/discover served demo data. Backend persistence of use_live verified correct via curl + UI.
- UX fix (Team.jsx): a successful **Test Connection now auto-enables live discovery** (saves use_live=true, refreshes badge to LIVE) so users don't have to separately toggle+save. Failure path unchanged (shows real AWS ClientError inline + toast). Self-tested via screenshot (invalid-cred path); success/auto-enable path requires valid AWS creds (not available in preview).
- Immediate workaround for user: flip Live discovery switch ON + Save → badge LIVE → Dashboard Discover shows real resources.

## Fix (2026-06) — Invisible Live-discovery toggle + AWS field autofill
- BUG: shadcn `Switch` uses `data-[state=unchecked]:bg-input` which on the dark theme is ~invisible, so users couldn't see/find the Live discovery toggle on Team page.
- FIX (Team.jsx): replaced the Switch with an explicit always-visible pill button (orange=ON / zinc-700=OFF) + ON/OFF badge. data-testid still `aws-use-live` (role=switch, aria-checked). Verified via screenshot desktop+mobile: toggle visible, flips OFF->ON.
- FIX: browser was autofilling admin@infraforge.io into the AWS Access Key field (and password into Secret) — added autoComplete off / new-password + name attrs on access-key/secret/region inputs to stop autofill (autofilled email could overwrite the saved key on Save -> "invalid token").
- User must redeploy images to get these on their self-hosted instance, and re-enter real AWS keys.

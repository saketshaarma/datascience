"""Backend API tests for AWS Infra Inventory & Terraform Portal (Iteration 2 - Auth)."""
import io
import json
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://aws-inventory-hub.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"
CSV_PATH = "/tmp/datatest.csv"

ADMIN_EMAIL = "admin@infraforge.io"
ADMIN_PASSWORD = "Admin@12345"


# ----------------- Fixtures -----------------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    data = r.json()
    assert "access_token" in data and "user" in data
    return data["access_token"]


@pytest.fixture(scope="session")
def admin_client(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}"})
    return s


@pytest.fixture(scope="session", autouse=True)
def clean_db(admin_client):
    admin_client.delete(f"{API}/instances", params={"confirm": "DELETE_ALL"})
    yield
    admin_client.delete(f"{API}/instances", params={"confirm": "DELETE_ALL"})


# ----------------- Auth -----------------
class TestAuth:
    def test_unauth_instances(self):
        assert requests.get(f"{API}/instances").status_code == 401

    def test_unauth_stats(self):
        assert requests.get(f"{API}/stats").status_code == 401

    def test_unauth_terraform(self):
        assert requests.post(f"{API}/terraform/generate", json={"resources": ["ec2"]}).status_code == 401

    def test_health_open(self):
        assert requests.get(f"{API}/health").status_code == 200

    def test_login_success(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        data = r.json()
        assert data["user"]["email"] == ADMIN_EMAIL
        assert data["user"]["role"] == "admin"
        assert isinstance(data["access_token"], str) and len(data["access_token"]) > 10

    def test_login_bad_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrongpass"})
        assert r.status_code == 401

    def test_me(self, admin_client):
        r = admin_client.get(f"{API}/auth/me")
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_register_member_and_delete(self, admin_client):
        # cleanup if exists
        r = admin_client.get(f"{API}/auth/users")
        for u in r.json():
            if u["email"] == "test_member@infraforge.io":
                admin_client.delete(f"{API}/auth/users/{u['id']}")
        r = admin_client.post(f"{API}/auth/register", json={
            "email": "test_member@infraforge.io", "password": "Member@123", "name": "Test Member"})
        assert r.status_code == 200, r.text
        uid = r.json()["id"]
        assert r.json()["role"] == "member"
        # member cannot register another user
        m = requests.post(f"{API}/auth/login", json={"email": "test_member@infraforge.io", "password": "Member@123"})
        assert m.status_code == 200
        m_token = m.json()["access_token"]
        r2 = requests.post(f"{API}/auth/register",
                           headers={"Authorization": f"Bearer {m_token}"},
                           json={"email": "x@x.com", "password": "abc12345", "name": "X"})
        assert r2.status_code == 403
        # admin cannot delete self
        me = admin_client.get(f"{API}/auth/me").json()
        r3 = admin_client.delete(f"{API}/auth/users/{me['id']}")
        assert r3.status_code == 400
        # admin can delete member
        r4 = admin_client.delete(f"{API}/auth/users/{uid}")
        assert r4.status_code == 200

    def test_brute_force_lockout(self):
        # throwaway email so admin isn't locked. Ingress may load-balance to multiple
        # backend replicas so counts per (ip,email) can differ - verify that at least
        # one 429 is returned within a reasonable number of attempts.
        codes = []
        for _ in range(15):
            r = requests.post(f"{API}/auth/login",
                              json={"email": "throwaway_bruteforce@nope.io", "password": "wrong"})
            codes.append(r.status_code)
        assert 429 in codes, f"Expected at least one 429 lockout response, got {codes}"


# ----------------- Instances CRUD with new fields -----------------
class TestInstancesExtended:
    created_id = None

    def test_create_with_all_new_fields(self, admin_client):
        payload = {
            "instance_name": "TEST_full",
            "environment": "prod",
            "host": "10.0.0.5",
            "port": 3306,
            "instance_role": "master",
            "region": "us-west-2",
            "ec2_instance_id": "i-0abc123",
            "ec2_instance_type": "t3.large",
            "ami_id": "ami-abcd",
            "vpc_id": "vpc-1",
            "subnet_id": "subnet-1",
            "availability_zone": "us-west-2a",
            "private_ip": "10.0.0.5",
            "public_ip": "54.1.2.3",
            "security_groups": ["sg-1", "sg-2"],
            "iam_instance_profile": "ec2-role",
            "ebs_volumes": [
                {"device_name": "/dev/sda1", "size_gb": 30, "volume_type": "gp3"},
                {"device_name": "/dev/sdb", "size_gb": 100, "volume_type": "gp3"},
            ],
            "dns_records": ["db.example.com"],
            "srv_records": ["_mysql._tcp.example.com"],
            "tags": {"Owner": "team-a", "Project": "alpha"},
            "custom_metadata": {"ticket": "JIRA-1"},
        }
        r = admin_client.post(f"{API}/instances", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        TestInstancesExtended.created_id = d["id"]
        # verify persist
        g = admin_client.get(f"{API}/instances/{d['id']}").json()
        assert g["environment"] == "prod"
        assert g["region"] == "us-west-2"
        assert g["ec2_instance_id"] == "i-0abc123"
        assert g["vpc_id"] == "vpc-1"
        assert g["availability_zone"] == "us-west-2a"
        assert g["private_ip"] == "10.0.0.5"
        assert g["public_ip"] == "54.1.2.3"
        assert g["security_groups"] == ["sg-1", "sg-2"]
        assert g["iam_instance_profile"] == "ec2-role"
        assert len(g["ebs_volumes"]) == 2
        assert g["ebs_volumes"][0]["device_name"] == "/dev/sda1"
        assert g["tags"]["Owner"] == "team-a"
        assert g["custom_metadata"]["ticket"] == "JIRA-1"

    def test_update(self, admin_client):
        r = admin_client.put(f"{API}/instances/{TestInstancesExtended.created_id}", json={
            "instance_name": "TEST_full", "environment": "staging", "host": "10.0.0.6",
            "region": "us-east-1",
        })
        assert r.status_code == 200
        assert r.json()["environment"] == "staging"

    def test_delete_single(self, admin_client):
        r = admin_client.delete(f"{API}/instances/{TestInstancesExtended.created_id}")
        assert r.status_code == 200


# ----------------- CSV Import Safeguards -----------------
class TestCSV:
    def test_import_success(self, admin_client):
        admin_client.delete(f"{API}/instances", params={"confirm": "DELETE_ALL"})
        assert os.path.exists(CSV_PATH), f"missing {CSV_PATH}"
        with open(CSV_PATH, "rb") as f:
            r = admin_client.post(f"{API}/instances/import-csv",
                                  files={"file": ("datatest.csv", f, "text/csv")})
        assert r.status_code == 200, r.text
        assert r.json()["imported"] == 5

    def test_stats(self, admin_client):
        r = admin_client.get(f"{API}/stats").json()
        assert r["total_hosts"] == 5
        assert r["total_dns"] == 54
        assert r["total_srv"] == 4

    def test_non_csv_rejected(self, admin_client):
        r = admin_client.post(f"{API}/instances/import-csv",
                              files={"file": ("bad.txt", b"x", "text/plain")})
        assert r.status_code == 400

    def test_oversized_rejected(self, admin_client):
        big = b"a" * (5 * 1024 * 1024 + 100)
        r = admin_client.post(f"{API}/instances/import-csv",
                              files={"file": ("big.csv", big, "text/csv")})
        assert r.status_code == 413

    def test_export_csv(self, admin_client):
        r = admin_client.get(f"{API}/instances/export")
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        text = r.text
        header = text.splitlines()[0]
        for col in ["instance_name", "environment", "security_groups", "ebs_volumes",
                    "dns_records", "srv_records", "tags", "custom_metadata"]:
            assert col in header


# ----------------- Delete-all safeguard -----------------
class TestDeleteAll:
    def test_no_confirm(self, admin_client):
        r = admin_client.delete(f"{API}/instances")
        assert r.status_code == 400

    def test_with_confirm(self, admin_client):
        r = admin_client.delete(f"{API}/instances", params={"confirm": "DELETE_ALL"})
        assert r.status_code == 200
        n = admin_client.get(f"{API}/instances").json()
        assert n == []


# ----------------- Terraform -----------------
class TestTerraform:
    def test_generate_full(self, admin_client):
        # seed one instance with all fields
        admin_client.post(f"{API}/instances", json={
            "instance_name": "TEST_tf", "environment": "prod", "host": "10.0.0.5",
            "region": "us-west-2", "private_ip": "10.0.0.5", "availability_zone": "us-west-2a",
            "iam_instance_profile": "ec2-role", "security_groups": ["sg-abc"],
            "ebs_volumes": [{"device_name": "/dev/sda1", "size_gb": 30, "volume_type": "gp3"}],
            "tags": {"Owner": "team-a"}, "custom_metadata": {"ticket": "JIRA-1"},
            "dns_records": ["db.example.com"], "srv_records": ["_mysql._tcp.example.com"],
            "ec2_instance_type": "t3.medium", "ami_id": "ami-1",
        })
        r = admin_client.post(f"{API}/terraform/generate",
                              json={"resources": ["ec2", "dns", "srv", "sg"], "output_format": "both"})
        assert r.status_code == 200, r.text
        d = r.json()
        hcl = d["hcl"]
        assert 'resource "aws_instance"' in hcl
        assert "private_ip" in hcl
        assert "availability_zone" in hcl
        assert "iam_instance_profile" in hcl
        assert "vpc_security_group_ids" in hcl
        assert "ebs_block_device" in hcl
        assert "Owner" in hcl  # tag merged
        assert "Environment" in hcl
        # valid JSON
        parsed = json.loads(d["json"])
        assert "resource" in parsed
        admin_client.delete(f"{API}/instances", params={"confirm": "DELETE_ALL"})


# ----------------- Terraform DNS target (Iteration 3) -----------------
class TestTerraformDnsTarget:
    """Iteration 3: DNS A records must reference the CREATED aws_instance IP,
    not the static host IP, unless dns_target=host or ec2 not in resources."""

    @pytest.fixture(scope="class", autouse=True)
    def seed(self, admin_client):
        admin_client.delete(f"{API}/instances", params={"confirm": "DELETE_ALL"})
        r = admin_client.post(f"{API}/instances", json={
            "instance_name": "jalsi", "host": "172.10.112.169", "port": 3306,
            "instance_role": "master", "ec2_instance_type": "t3.medium",
            "ami_id": "ami-baseXYZ", "dns_records": ["db.example.com"],
            "srv_records": ["_mysql._tcp.example.com"],
        })
        assert r.status_code == 200, r.text
        yield
        admin_client.delete(f"{API}/instances", params={"confirm": "DELETE_ALL"})

    def _gen(self, admin_client, **overrides):
        payload = {
            "resources": ["ec2", "dns", "srv", "sg"],
            "output_format": "both",
            "dns_target": "instance_private",
        }
        payload.update(overrides)
        r = admin_client.post(f"{API}/terraform/generate", json=payload)
        assert r.status_code == 200, r.text
        return r.json()

    def test_ami_from_inventory(self, admin_client):
        d = self._gen(admin_client)
        # base instance's AMI is propagated
        assert 'ami = "ami-baseXYZ"' in d["hcl"]

    def test_dns_target_instance_private(self, admin_client):
        d = self._gen(admin_client, dns_target="instance_private")
        hcl = d["hcl"]
        # Unquoted reference in HCL
        assert "records = [aws_instance.ec2_jalsi_172_10_112_169.private_ip]" in hcl
        assert '"172.10.112.169"' not in hcl.split("aws_route53_record")[1].split("}")[0] if "aws_route53_record" in hcl else True
        # ${...} in JSON
        parsed = json.loads(d["json"])
        rec = list(parsed["resource"]["aws_route53_record"].values())[0]
        assert rec["records"] == ["${aws_instance.ec2_jalsi_172_10_112_169.private_ip}"]
        assert rec["type"] == "A"

    def test_dns_target_instance_public(self, admin_client):
        d = self._gen(admin_client, dns_target="instance_public")
        assert "records = [aws_instance.ec2_jalsi_172_10_112_169.public_ip]" in d["hcl"]
        parsed = json.loads(d["json"])
        rec = list(parsed["resource"]["aws_route53_record"].values())[0]
        assert rec["records"] == ["${aws_instance.ec2_jalsi_172_10_112_169.public_ip}"]

    def test_dns_target_host(self, admin_client):
        d = self._gen(admin_client, dns_target="host")
        assert 'records = ["172.10.112.169"]' in d["hcl"]
        parsed = json.loads(d["json"])
        rec = list(parsed["resource"]["aws_route53_record"].values())[0]
        assert rec["records"] == ["172.10.112.169"]

    def test_dns_fallback_when_no_ec2(self, admin_client):
        # dns_target=instance_private BUT ec2 not requested -> must fall back to literal host
        d = self._gen(admin_client, resources=["dns", "srv"], dns_target="instance_private")
        assert 'records = ["172.10.112.169"]' in d["hcl"]
        parsed = json.loads(d["json"])
        rec = list(parsed["resource"]["aws_route53_record"].values())[0]
        assert rec["records"] == ["172.10.112.169"]
        # no ec2 was generated
        assert "aws_instance" not in parsed["resource"]

    def test_srv_still_literal(self, admin_client):
        d = self._gen(admin_client)
        parsed = json.loads(d["json"])
        srv = [v for k, v in parsed["resource"]["aws_route53_record"].items() if v["type"] == "SRV"]
        assert len(srv) == 1
        # SRV value is a literal string (no interpolation)
        assert srv[0]["records"][0].startswith("0 5 3306 ")
        assert "aws_instance" not in srv[0]["records"][0]

    def test_sg_still_from_port(self, admin_client):
        d = self._gen(admin_client)
        parsed = json.loads(d["json"])
        sg = list(parsed["resource"]["aws_security_group"].values())[0]
        assert sg["ingress"][0]["from_port"] == 3306
        assert sg["ingress"][0]["to_port"] == 3306

    def test_json_only_all_instances(self, admin_client):
        # instance_ids null -> all instances; output_format=json -> valid TF JSON doc
        d = self._gen(admin_client, instance_ids=None, output_format="json")
        assert "hcl" not in d or d.get("hcl") is None
        assert d["json"]
        parsed = json.loads(d["json"])
        assert "terraform" in parsed
        assert "provider" in parsed
        assert "resource" in parsed
        assert "aws_instance" in parsed["resource"]
        assert "aws_route53_record" in parsed["resource"]
        assert "aws_security_group" in parsed["resource"]



# ----------------- Iteration 4: Admin-only delete + host:port uniqueness + grouping -----------------
@pytest.fixture(scope="module")
def member_token(admin_client):
    """Create (or refresh) a throwaway member and return an access token."""
    # cleanup
    r = admin_client.get(f"{API}/auth/users")
    for u in r.json():
        if u["email"] == "iter4_member@infraforge.io":
            admin_client.delete(f"{API}/auth/users/{u['id']}")
    r = admin_client.post(f"{API}/auth/register", json={
        "email": "iter4_member@infraforge.io", "password": "Member@123", "name": "Iter4 Member"})
    assert r.status_code == 200, r.text
    login = requests.post(f"{API}/auth/login",
                          json={"email": "iter4_member@infraforge.io", "password": "Member@123"})
    assert login.status_code == 200
    return login.json()["access_token"]


class TestIter4AdminDelete:
    """Only admin can delete single/all; members get 403."""

    @pytest.fixture(scope="class", autouse=True)
    def _clean(self, admin_client):
        admin_client.delete(f"{API}/instances", params={"confirm": "DELETE_ALL"})
        yield
        admin_client.delete(f"{API}/instances", params={"confirm": "DELETE_ALL"})

    def _seed(self, admin_client, host="10.0.9.1", port=3306):
        r = admin_client.post(f"{API}/instances", json={
            "instance_name": "TEST_del", "host": host, "port": port, "ec2_instance_type": "t3.medium",
            "ami_id": "ami-x",
        })
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def test_member_delete_single_forbidden(self, admin_client, member_token):
        iid = self._seed(admin_client, "10.0.9.10", 3306)
        r = requests.delete(f"{API}/instances/{iid}",
                            headers={"Authorization": f"Bearer {member_token}"})
        assert r.status_code == 403
        # still exists
        assert admin_client.get(f"{API}/instances/{iid}").status_code == 200

    def test_member_delete_all_forbidden(self, member_token):
        r = requests.delete(f"{API}/instances", params={"confirm": "DELETE_ALL"},
                            headers={"Authorization": f"Bearer {member_token}"})
        assert r.status_code == 403

    def test_admin_delete_single_ok(self, admin_client):
        iid = self._seed(admin_client, "10.0.9.11", 3306)
        r = admin_client.delete(f"{API}/instances/{iid}")
        assert r.status_code == 200
        assert admin_client.get(f"{API}/instances/{iid}").status_code == 404

    def test_admin_delete_all_ok(self, admin_client):
        self._seed(admin_client, "10.0.9.12", 3306)
        self._seed(admin_client, "10.0.9.13", 3306)
        r = admin_client.delete(f"{API}/instances", params={"confirm": "DELETE_ALL"})
        assert r.status_code == 200
        assert admin_client.get(f"{API}/instances").json() == []


class TestIter4HostPortUnique:
    """Host:port must be unique on create/update; same host different port OK."""

    @pytest.fixture(scope="class", autouse=True)
    def _clean(self, admin_client):
        admin_client.delete(f"{API}/instances", params={"confirm": "DELETE_ALL"})
        yield
        admin_client.delete(f"{API}/instances", params={"confirm": "DELETE_ALL"})

    def test_create_duplicate_409(self, admin_client):
        p = {"instance_name": "A", "host": "10.0.7.7", "port": 3306,
             "ec2_instance_type": "t3.medium", "ami_id": "ami-x"}
        r1 = admin_client.post(f"{API}/instances", json=p)
        assert r1.status_code == 200
        r2 = admin_client.post(f"{API}/instances", json={**p, "instance_name": "B"})
        assert r2.status_code == 409
        assert "already exists" in r2.json()["detail"].lower()

    def test_same_host_different_port_ok(self, admin_client):
        r = admin_client.post(f"{API}/instances", json={
            "instance_name": "C", "host": "10.0.7.7", "port": 6379,
            "ec2_instance_type": "t3.medium", "ami_id": "ami-x"})
        assert r.status_code == 200

    def test_update_conflict_409(self, admin_client):
        # add third distinct host/port
        r = admin_client.post(f"{API}/instances", json={
            "instance_name": "D", "host": "10.0.7.8", "port": 3306,
            "ec2_instance_type": "t3.medium", "ami_id": "ami-x"})
        assert r.status_code == 200
        did = r.json()["id"]
        # try to update D to (10.0.7.7, 3306) - which A owns -> 409
        u = admin_client.put(f"{API}/instances/{did}", json={
            "instance_name": "D", "host": "10.0.7.7", "port": 3306,
            "ec2_instance_type": "t3.medium", "ami_id": "ami-x"})
        assert u.status_code == 409

    def test_update_self_same_hostport_ok(self, admin_client):
        # find A and update it with same host:port -> should not conflict
        lst = admin_client.get(f"{API}/instances").json()
        a = next(i for i in lst if i["host"] == "10.0.7.7" and i["port"] == 3306)
        u = admin_client.put(f"{API}/instances/{a['id']}", json={
            "instance_name": "A2", "host": "10.0.7.7", "port": 3306,
            "ec2_instance_type": "t3.medium", "ami_id": "ami-x"})
        assert u.status_code == 200


class TestIter4CsvDedup:
    """Re-importing same CSV should skip duplicates and report count."""

    @pytest.fixture(scope="class", autouse=True)
    def _clean(self, admin_client):
        admin_client.delete(f"{API}/instances", params={"confirm": "DELETE_ALL"})
        yield
        admin_client.delete(f"{API}/instances", params={"confirm": "DELETE_ALL"})

    def test_first_import_then_reimport_skips(self, admin_client):
        with open(CSV_PATH, "rb") as f:
            r1 = admin_client.post(f"{API}/instances/import-csv",
                                   files={"file": ("datatest.csv", f, "text/csv")})
        assert r1.status_code == 200, r1.text
        body1 = r1.json()
        assert body1["imported"] == 5
        assert body1.get("skipped", 0) == 0
        # reimport - all should skip
        with open(CSV_PATH, "rb") as f:
            r2 = admin_client.post(f"{API}/instances/import-csv",
                                   files={"file": ("datatest.csv", f, "text/csv")})
        assert r2.status_code == 200, r2.text
        body2 = r2.json()
        assert body2["imported"] == 0
        assert body2["skipped"] == 5

    def test_within_file_dedup(self, admin_client):
        admin_client.delete(f"{API}/instances", params={"confirm": "DELETE_ALL"})
        csv_body = (
            "Id,InstanceName,Host_Port,Instance Type,ALL_DNS,SRV\n"
            "1,alpha,10.0.8.1:3306,t3.medium,a.example.com,\n"
            "2,alpha_dup,10.0.8.1:3306,t3.medium,b.example.com,\n"
            "3,beta,10.0.8.2:3306,t3.medium,c.example.com,\n"
        )
        r = admin_client.post(f"{API}/instances/import-csv",
                              files={"file": ("dup.csv", csv_body.encode(), "text/csv")})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["imported"] == 2
        assert b["skipped"] == 1


class TestIter4TerraformGrouping:
    """One host with multiple ports -> one aws_instance, one SG w/ multi ingress,
    DNS aggregated referencing the single instance, SRV keyed to own port."""

    @pytest.fixture(scope="class", autouse=True)
    def _seed(self, admin_client):
        admin_client.delete(f"{API}/instances", params={"confirm": "DELETE_ALL"})
        # mysql
        r1 = admin_client.post(f"{API}/instances", json={
            "instance_name": "db-mysql", "host": "10.0.0.5", "port": 3306,
            "ec2_instance_type": "t3.medium", "ami_id": "ami-shared",
            "dns_records": ["db.example.com"],
            "srv_records": ["_mysql._tcp.example.com"],
        })
        assert r1.status_code == 200, r1.text
        # redis (same host, different port)
        r2 = admin_client.post(f"{API}/instances", json={
            "instance_name": "db-redis", "host": "10.0.0.5", "port": 6379,
            "ec2_instance_type": "t3.medium", "ami_id": "ami-shared",
            "dns_records": ["cache.example.com"],
            "srv_records": ["_redis._tcp.example.com"],
        })
        assert r2.status_code == 200, r2.text
        yield
        admin_client.delete(f"{API}/instances", params={"confirm": "DELETE_ALL"})

    def test_grouping_produces_single_ec2_and_sg(self, admin_client):
        r = admin_client.post(f"{API}/terraform/generate", json={
            "resources": ["ec2", "dns", "srv", "sg"], "output_format": "both",
            "dns_target": "instance_private",
        })
        assert r.status_code == 200, r.text
        parsed = json.loads(r.json()["json"])
        insts = parsed["resource"]["aws_instance"]
        sgs = parsed["resource"]["aws_security_group"]
        assert len(insts) == 1, f"expected 1 aws_instance, got {list(insts.keys())}"
        assert len(sgs) == 1, f"expected 1 aws_security_group, got {list(sgs.keys())}"
        # SG must contain ingress rules for BOTH ports
        sg = list(sgs.values())[0]
        ports = sorted({(ing["from_port"], ing["to_port"]) for ing in sg["ingress"]})
        assert (3306, 3306) in ports and (6379, 6379) in ports, f"ports={ports}"

    def test_dns_aggregated_and_ref_single_instance(self, admin_client):
        r = admin_client.post(f"{API}/terraform/generate", json={
            "resources": ["ec2", "dns", "srv", "sg"], "output_format": "both",
            "dns_target": "instance_private",
        })
        parsed = json.loads(r.json()["json"])
        recs = parsed["resource"]["aws_route53_record"]
        a_records = [v for v in recs.values() if v["type"] == "A"]
        srv_records = [v for v in recs.values() if v["type"] == "SRV"]
        # Both A records reference the SAME single aws_instance
        assert len(a_records) == 2
        for a in a_records:
            assert a["records"] == ["${aws_instance.ec2_db_mysql_10_0_0_5.private_ip}"] \
                or a["records"] == ["${aws_instance.ec2_db_redis_10_0_0_5.private_ip}"]
        # They should reference the SAME instance name
        refs = {a["records"][0] for a in a_records}
        assert len(refs) == 1, f"A records reference more than one instance: {refs}"
        # SRV: each keyed to its own port
        srv_ports = sorted(int(s["records"][0].split()[2]) for s in srv_records)
        assert srv_ports == [3306, 6379], f"SRV ports={srv_ports}"

    def test_ec2_ami_from_inventory(self, admin_client):
        r = admin_client.post(f"{API}/terraform/generate", json={
            "resources": ["ec2"], "output_format": "hcl", "dns_target": "instance_private",
        })
        assert 'ami = "ami-shared"' in r.json()["hcl"]

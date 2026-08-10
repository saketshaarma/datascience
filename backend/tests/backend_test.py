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

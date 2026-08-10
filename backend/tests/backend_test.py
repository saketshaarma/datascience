"""Backend API tests for AWS Infra Inventory & Terraform Portal."""
import json
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://aws-inventory-hub.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"
CSV_PATH = "/tmp/datatest.csv"


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    return s


@pytest.fixture(scope="session", autouse=True)
def clean_db(client):
    # Wipe before test session for deterministic counts
    client.delete(f"{API}/instances")
    yield
    # Final cleanup
    client.delete(f"{API}/instances")


# ----------------- Health -----------------
def test_root(client):
    r = client.get(f"{API}/")
    assert r.status_code == 200
    assert "message" in r.json()


# ----------------- CRUD -----------------
class TestInstanceCRUD:
    created_id = None

    def test_create_instance(self, client):
        payload = {
            "instance_name": "TEST_db01",
            "host": "10.0.0.5",
            "port": 3306,
            "instance_role": "master",
            "ec2_instance_type": "t3.medium",
            "ami_id": "ami-1234",
            "dns_records": ["db01.example.com"],
            "srv_records": ["_mysql._tcp.example.com"],
        }
        r = client.post(f"{API}/instances", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["instance_name"] == "TEST_db01"
        assert data["port"] == 3306
        assert data["dns_records"] == ["db01.example.com"]
        assert "id" in data
        TestInstanceCRUD.created_id = data["id"]

    def test_get_instance(self, client):
        assert TestInstanceCRUD.created_id
        r = client.get(f"{API}/instances/{TestInstanceCRUD.created_id}")
        assert r.status_code == 200
        assert r.json()["host"] == "10.0.0.5"

    def test_list_instances(self, client):
        r = client.get(f"{API}/instances")
        assert r.status_code == 200
        arr = r.json()
        assert isinstance(arr, list)
        assert any(i["id"] == TestInstanceCRUD.created_id for i in arr)

    def test_update_instance(self, client):
        r = client.put(f"{API}/instances/{TestInstanceCRUD.created_id}", json={
            "instance_name": "TEST_db01",
            "host": "10.0.0.6",
            "port": 3307,
            "instance_role": "slave",
            "ec2_instance_type": "t3.large",
            "ami_id": "ami-1234",
            "dns_records": ["db01.example.com"],
            "srv_records": [],
        })
        assert r.status_code == 200
        assert r.json()["host"] == "10.0.0.6"
        assert r.json()["instance_role"] == "slave"
        # verify persistence
        g = client.get(f"{API}/instances/{TestInstanceCRUD.created_id}").json()
        assert g["port"] == 3307

    def test_delete_instance(self, client):
        r = client.delete(f"{API}/instances/{TestInstanceCRUD.created_id}")
        assert r.status_code == 200
        assert r.json().get("deleted") is True
        g = client.get(f"{API}/instances/{TestInstanceCRUD.created_id}")
        assert g.status_code == 404


# ----------------- CSV Import -----------------
class TestCSVImport:
    def test_import_csv(self, client):
        # ensure clean
        client.delete(f"{API}/instances")
        assert os.path.exists(CSV_PATH), f"CSV file missing at {CSV_PATH}"
        with open(CSV_PATH, "rb") as f:
            r = client.post(f"{API}/instances/import-csv",
                            files={"file": ("datatest.csv", f, "text/csv")})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["imported"] == 5, f"expected 5 hosts, got {data}"

    def test_stats_after_import(self, client):
        r = client.get(f"{API}/stats")
        assert r.status_code == 200
        s = r.json()
        assert s["total_hosts"] == 5
        assert s["total_dns"] == 54, f"expected 54 dns got {s['total_dns']}"
        assert s["total_srv"] == 4, f"expected 4 srv got {s['total_srv']}"
        assert isinstance(s["role_breakdown"], list)
        assert isinstance(s["type_breakdown"], list)


# ----------------- Terraform -----------------
class TestTerraform:
    def test_generate_all(self, client):
        r = client.post(f"{API}/terraform/generate", json={
            "resources": ["ec2", "dns", "srv", "sg"],
            "output_format": "both",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert "hcl" in data and "json" in data
        assert data["resource_count"] > 0
        # HCL should include a resource block
        assert 'resource "aws_instance"' in data["hcl"]
        # JSON must be valid
        parsed = json.loads(data["json"])
        assert "resource" in parsed
        assert "aws_instance" in parsed["resource"]

    def test_generate_dns_only(self, client):
        r = client.post(f"{API}/terraform/generate", json={
            "resources": ["dns"],
            "output_format": "hcl",
        })
        assert r.status_code == 200
        data = r.json()
        assert "aws_route53_record" in data["hcl"]
        assert "aws_instance" not in data["hcl"]

    def test_generate_empty_selection(self, client):
        # Empty when no instances - clean and try
        client.delete(f"{API}/instances")
        r = client.post(f"{API}/terraform/generate", json={"resources": ["ec2"]})
        assert r.status_code == 400

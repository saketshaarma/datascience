"""Backend tests for the new Non-K8s Workloads feature + AWS test-connection + tag-options."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to reading frontend/.env
    from pathlib import Path
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL"):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN_EMAIL = "admin@infraforge.io"
ADMIN_PASSWORD = "Admin@12345"


@pytest.fixture(scope="module")
def admin_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    token = r.json()["access_token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


SAMPLE_WORKLOAD = {
    "name": "TEST_workload_1",
    "aws_region": "ap-south-1",
    "vpc_tag": "prod-vpc",
    "subnet_tag": "prod-subnet-a",
    "key_name": "my-key",
    "enable_dns": True,
    "private_zone_name": "internal.local",
    "ami_id": "ami-abc123",
    "ingress_ports": [22, 80, 443],
    "security_group_tags": {"Name": "test-sg"},
    "instance_tags": {"Env": "test"},
    "volume_tags": {"Env": "test"},
    "nodes": [
        {
            "hostname": "web01",
            "role": "web",
            "instance_type": "t3.small",
            "root_volume_size": 30,
            "data_volumes": [
                {"device_name": "/dev/sdf", "size_gb": 100, "volume_type": "gp3"},
                {"device_name": "/dev/sdg", "size_gb": 200, "volume_type": "io2"},
            ],
        },
        {
            "hostname": "db01",
            "role": "db",
            "instance_type": "r5.large",
            "root_volume_size": 40,
            "data_volumes": [
                {"device_name": "/dev/sdh", "size_gb": 500, "volume_type": "gp3"},
            ],
        },
    ],
}


# ---------- CRUD ----------
class TestWorkloadsCRUD:
    _created_id = None

    def test_create(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/workloads", json=SAMPLE_WORKLOAD, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == "TEST_workload_1"
        assert data["enable_dns"] is True
        assert data["ingress_ports"] == [22, 80, 443]
        assert len(data["nodes"]) == 2
        assert data["nodes"][0]["data_volumes"][0]["size_gb"] == 100
        assert "id" in data
        TestWorkloadsCRUD._created_id = data["id"]

    def test_list(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/workloads", timeout=30)
        assert r.status_code == 200
        ids = [w["id"] for w in r.json()]
        assert TestWorkloadsCRUD._created_id in ids

    def test_get_by_id(self, admin_client):
        wid = TestWorkloadsCRUD._created_id
        r = admin_client.get(f"{BASE_URL}/api/workloads/{wid}", timeout=30)
        assert r.status_code == 200
        assert r.json()["id"] == wid

    def test_get_404(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/workloads/does-not-exist", timeout=30)
        assert r.status_code == 404

    def test_update(self, admin_client):
        wid = TestWorkloadsCRUD._created_id
        payload = dict(SAMPLE_WORKLOAD)
        payload["name"] = "TEST_workload_1_updated"
        payload["ingress_ports"] = [22, 8080]
        r = admin_client.put(f"{BASE_URL}/api/workloads/{wid}", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "TEST_workload_1_updated"
        # verify persisted
        g = admin_client.get(f"{BASE_URL}/api/workloads/{wid}", timeout=30)
        assert g.json()["ingress_ports"] == [22, 8080]

    def test_preview(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/workloads/preview", json=SAMPLE_WORKLOAD, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "config_json" in data and "files" in data
        files = data["files"]
        for fn in ["provider.tf", "variables.tf", "main.tf", "outputs.tf",
                   "terraform.tfvars.json", "userdata.sh.tpl"]:
            assert fn in files, f"missing {fn}"
        import json as _json
        tfvars = _json.loads(files["terraform.tfvars.json"])
        assert tfvars["ingress_ports"] == [22, 80, 443]
        assert "node1" in tfvars["nodes"]
        assert tfvars["nodes"]["node1"]["data_volumes"][0]["size_gb"] == 100
        cfg = _json.loads(data["config_json"])
        assert cfg["enable_dns"] is True
        assert cfg["nodes"]["node1"]["role"] == "web"

    def test_generate_saved(self, admin_client):
        wid = TestWorkloadsCRUD._created_id
        r = admin_client.post(f"{BASE_URL}/api/workloads/{wid}/generate", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "config_json" in data
        assert "main.tf" in data["files"]

    def test_delete_admin(self, admin_client):
        wid = TestWorkloadsCRUD._created_id
        r = admin_client.delete(f"{BASE_URL}/api/workloads/{wid}", timeout=30)
        assert r.status_code == 200
        assert r.json().get("deleted") is True
        g = admin_client.get(f"{BASE_URL}/api/workloads/{wid}", timeout=30)
        assert g.status_code == 404


# ---------- AWS test-connection + tag-options ----------
class TestAws:
    def test_test_connection_with_invalid_creds(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/aws/test-connection", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        # should return ok:false (no creds saved or invalid creds)
        assert body.get("ok") is False
        assert "error" in body and body["error"]

    def test_tag_options_has_mode(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/aws/tag-options", timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "mode" in body
        assert body["mode"] in ("demo", "live")
        assert "keys" in body and "values" in body

    def test_discover_demo(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/aws/discover", json={}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["mode"] in ("demo", "live")
        assert "resources" in body
        assert "by_kind" in body

"""Backend pytest for /api/db (DB Config) endpoints - iteration 6."""
import io
import os
import uuid
import pytest
import requests
import openpyxl

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@infraforge.io", "password": "Admin@12345"}


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def member_ctx(admin_headers):
    """Create a throwaway member and return (headers, user_id) for permission tests."""
    email = f"TEST_member_{uuid.uuid4().hex[:6]}@test.io"
    password = "Member@12345"
    r = requests.post(
        f"{API}/auth/register",
        headers=admin_headers,
        json={"email": email, "password": password, "name": "TEST Member"},
        timeout=15,
    )
    assert r.status_code in (200, 201), f"register member failed: {r.status_code} {r.text}"
    uid = r.json().get("id") or r.json().get("user", {}).get("id")
    lr = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert lr.status_code == 200
    token = lr.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    yield headers, uid
    # cleanup
    if uid:
        try:
            requests.delete(f"{API}/auth/users/{uid}", headers=admin_headers, timeout=10)
        except Exception:
            pass


created_services = []
created_instances = []


@pytest.fixture(scope="session", autouse=True)
def cleanup_after(admin_headers):
    yield
    # delete instances first, then services
    for iid in created_instances:
        try:
            requests.delete(f"{API}/db/instances/{iid}", headers=admin_headers, timeout=10)
        except Exception:
            pass
    for sid in created_services:
        try:
            requests.delete(f"{API}/db/services/{sid}", headers=admin_headers, timeout=10)
        except Exception:
            pass
    # also try to delete any TEST_ services that may have been auto-created via excel
    try:
        r = requests.get(f"{API}/db/services", headers=admin_headers, timeout=10)
        for s in r.json():
            if s["service_name"].startswith("TEST_"):
                # remove instances first
                ins = requests.get(f"{API}/db/instances", headers=admin_headers,
                                   params={"service_id": s["id"]}, timeout=10).json()
                for it in ins:
                    requests.delete(f"{API}/db/instances/{it['id']}", headers=admin_headers, timeout=10)
                requests.delete(f"{API}/db/services/{s['id']}", headers=admin_headers, timeout=10)
    except Exception:
        pass


# ---------- All services + instances + delete (one class for xdist loadscope) ----------
class TestDbConfig:
    def test_create_service(self, admin_headers):
        name = f"TEST_svc_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/db/services", headers=admin_headers,
                          json={"service_name": name}, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["service_name"] == name
        assert "id" in d
        created_services.append(d["id"])
        pytest.svc_id = d["id"]
        pytest.svc_name = name

    def test_create_duplicate_service(self, admin_headers):
        r = requests.post(f"{API}/db/services", headers=admin_headers,
                          json={"service_name": pytest.svc_name}, timeout=10)
        assert r.status_code == 409, r.text

    def test_list_services_has_instance_count(self, admin_headers):
        r = requests.get(f"{API}/db/services", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        arr = r.json()
        match = [s for s in arr if s["id"] == pytest.svc_id]
        assert match and "instance_count" in match[0]
        assert match[0]["instance_count"] == 0

    def test_update_service_rename(self, admin_headers):
        new_name = f"TEST_svc_renamed_{uuid.uuid4().hex[:6]}"
        r = requests.put(f"{API}/db/services/{pytest.svc_id}", headers=admin_headers,
                         json={"service_name": new_name}, timeout=10)
        assert r.status_code == 200, r.text
        assert r.json()["service_name"] == new_name
        pytest.svc_name = new_name

    def test_delete_service_admin_only(self, member_ctx):
        headers, _ = member_ctx
        r = requests.delete(f"{API}/db/services/{pytest.svc_id}", headers=headers, timeout=10)
        assert r.status_code == 403, r.text

    # ---------- Instances ----------
    def test_create_instance_invalid_service_id(self, admin_headers):
        r = requests.post(f"{API}/db/instances", headers=admin_headers, json={
            "service_id": "bogus-id-xxx", "instance_name": "x"
        }, timeout=10)
        assert r.status_code == 400, r.text

    def test_create_instance_ok(self, admin_headers):
        aws_id = f"i-{uuid.uuid4().hex[:12]}"
        payload = {
            "service_id": pytest.svc_id,
            "instance_name": "TEST_ins1",
            "host": "10.0.0.5", "port": 3306,
            "instance_type": "db.r5.large",
            "aws_instance_id": aws_id,
            "all_dns": "db.test.example.com",
            "aws_region": "ap-south-1",
            "environment": "PROD", "status": "Running",
            "metadata": [
                {"attribute_key": "owner", "attribute_value": "alice"},
                {"attribute_key": "team", "attribute_value": "data"},
                {"attribute_key": "owner", "attribute_value": "dup-should-drop"},
            ],
        }
        r = requests.post(f"{API}/db/instances", headers=admin_headers, json=payload, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["instance_name"] == "TEST_ins1"
        assert d["environment"] == "PROD"
        assert d["status"] == "Running"
        # metadata dedup
        keys = [m["attribute_key"] for m in d["metadata"]]
        assert keys.count("owner") == 1
        assert set(keys) == {"owner", "team"}
        created_instances.append(d["id"])
        pytest.ins_id = d["id"]
        pytest.aws_id = aws_id

    def test_create_instance_duplicate_awsid(self, admin_headers):
        r = requests.post(f"{API}/db/instances", headers=admin_headers, json={
            "service_id": pytest.svc_id, "instance_name": "TEST_ins2",
            "aws_instance_id": pytest.aws_id,
        }, timeout=10)
        assert r.status_code == 409, r.text

    def test_create_instance_invalid_env(self, admin_headers):
        r = requests.post(f"{API}/db/instances", headers=admin_headers, json={
            "service_id": pytest.svc_id, "instance_name": "bad",
            "environment": "BOGUS"
        }, timeout=10)
        assert r.status_code == 422, r.text

    def test_list_instances_filter_and_service_name(self, admin_headers):
        r = requests.get(f"{API}/db/instances", headers=admin_headers,
                         params={"service_id": pytest.svc_id}, timeout=10)
        assert r.status_code == 200
        arr = r.json()
        assert len(arr) >= 1
        assert all(i["service_id"] == pytest.svc_id for i in arr)
        assert arr[0].get("service_name")  # joined name present

    def test_list_instances_search(self, admin_headers):
        r = requests.get(f"{API}/db/instances", headers=admin_headers,
                         params={"search": "TEST_ins1"}, timeout=10)
        assert r.status_code == 200
        assert any(i["instance_name"] == "TEST_ins1" for i in r.json())

    def test_update_instance(self, admin_headers):
        r = requests.put(f"{API}/db/instances/{pytest.ins_id}", headers=admin_headers, json={
            "service_id": pytest.svc_id, "instance_name": "TEST_ins1",
            "host": "10.0.0.9", "port": 3306, "aws_instance_id": pytest.aws_id,
            "environment": "QA", "status": "Stopped", "metadata": [],
        }, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["environment"] == "QA"
        assert d["status"] == "Stopped"
        assert d["host"] == "10.0.0.9"

    def test_service_delete_blocked_with_instances(self, admin_headers):
        r = requests.delete(f"{API}/db/services/{pytest.svc_id}", headers=admin_headers, timeout=10)
        assert r.status_code == 409, r.text

    def test_delete_instance_member_forbidden(self, member_ctx):
        headers, _ = member_ctx
        r = requests.delete(f"{API}/db/instances/{pytest.ins_id}", headers=headers, timeout=10)
        assert r.status_code == 403, r.text

    # ---------- Excel import ----------
    def _make_xlsx(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        headers = ["service_name", "instance_name", "host", "port", "instance_type",
                   "aws_instance_id", "all_dns", "srv_record", "aws_region",
                   "environment", "status", "owner", "team"]
        ws.append(headers)
        prefix = f"TEST_xl_{uuid.uuid4().hex[:6]}"
        aws_a = f"i-{uuid.uuid4().hex[:12]}"
        aws_b = f"i-{uuid.uuid4().hex[:12]}"
        ws.append([f"{prefix}_svcA", "insA", "10.1.1.1", 3306, "db.t3.medium",
                   aws_a, "a.example.com", "", "ap-south-1", "prod", "running", "alice", "core"])
        ws.append([f"{prefix}_svcA", "insA2", "10.1.1.2", 3306, "db.t3.medium",
                   aws_b, "a2.example.com", "", "ap-south-1", "dev", "stopped", "bob", "core"])
        # duplicate aws_id -> should be skipped
        ws.append([f"{prefix}_svcA", "dup", "10.1.1.3", 3306, "", aws_a,
                   "", "", "", "DEV", "Running", "carol", "core"])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf.read(), prefix

    def test_reject_non_xlsx(self, admin_headers):
        files = {"file": ("bad.csv", b"a,b,c\n1,2,3\n", "text/csv")}
        r = requests.post(f"{API}/db/import-excel", headers=admin_headers, files=files, timeout=15)
        assert r.status_code == 400, r.text

    def test_import_xlsx_creates_services_and_metadata(self, admin_headers):
        data, prefix = self._make_xlsx()
        files = {"file": ("test.xlsx", data,
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r = requests.post(f"{API}/db/import-excel", headers=admin_headers, files=files, timeout=30)
        assert r.status_code == 200, r.text
        res = r.json()
        assert res["imported"] == 2
        assert res["skipped"] == 1
        # verify service auto-created
        svcs = requests.get(f"{API}/db/services", headers=admin_headers, timeout=10).json()
        target = [s for s in svcs if s["service_name"] == f"{prefix}_svcA"]
        assert target, f"auto-created service not found among {[s['service_name'] for s in svcs]}"
        created_services.append(target[0]["id"])
        sid = target[0]["id"]
        # verify metadata columns became attributes
        ins = requests.get(f"{API}/db/instances", headers=admin_headers,
                          params={"service_id": sid}, timeout=10).json()
        assert len(ins) == 2
        for i in ins:
            created_instances.append(i["id"])
            keys = {m["attribute_key"] for m in i.get("metadata", [])}
            assert "owner" in keys and "team" in keys

    # ---------- JSON export ----------
    def test_export_json_shape(self, admin_headers):
        r = requests.get(f"{API}/db/export-json", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert set(data.keys()) == {"db_services", "db_instances", "db_instance_metadata"}
        assert isinstance(data["db_services"], list)
        assert isinstance(data["db_instances"], list)
        assert isinstance(data["db_instance_metadata"], list)
        # int ids
        for s in data["db_services"]:
            assert isinstance(s["id"], int)
            assert "service_name" in s
        svc_ids = {s["id"] for s in data["db_services"]}
        ins_ids = {i["id"] for i in data["db_instances"]}
        for i in data["db_instances"]:
            assert isinstance(i["id"], int)
            assert i["service_id"] in svc_ids, "FK service_id must reference db_services.id"
            assert "instance_name" in i
            assert i["environment"] in ["DEV", "QA", "UAT", "DR", "PROD"]
            assert i["status"] in ["Running", "Stopped", "Terminated"]
        for m in data["db_instance_metadata"]:
            assert isinstance(m["id"], int)
            assert m["instance_id"] in ins_ids, "FK instance_id must reference db_instances.id"
            assert "attribute_key" in m

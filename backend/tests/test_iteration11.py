"""Iteration 11 backend tests:
- DB Config CSV import (host-grouped, default service from filename)
- Combined JSON export
- AWS instance-action guard (live mode off)
"""
import io
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@infraforge.io"
ADMIN_PASSWORD = "Admin@12345"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- DB Config CSV import (host-grouped) ----------

CSV_CONTENT = (
    "Id,InstanceName,Host_Port,Instance Type,ALL_DNS,SRV\n"
    "1,JaLsi,172.10.112.169:3306,slave,dns1.example.com,srv1.example.com\n"
    ",,,,dns2.example.com,srv2.example.com\n"
    ",,,,dns3.example.com,\n"
    ",,,,dns4.example.com,\n"
    "2,SecondHost,172.10.113.50:3306,master,mainpri.example.com,\n"
)


def test_db_import_host_grouped_csv(auth_headers):
    files = {"file": ("datatest_iter11.csv", CSV_CONTENT, "text/csv")}
    r = requests.post(f"{API}/db/import-excel", headers=auth_headers, files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] >= 2, body
    # verify created service auto from filename
    svc_r = requests.get(f"{API}/db/services", headers=auth_headers)
    assert svc_r.status_code == 200
    svc_names = [s["service_name"] for s in svc_r.json()]
    assert "datatest_iter11" in svc_names, svc_names
    svc_id = next(s["id"] for s in svc_r.json() if s["service_name"] == "datatest_iter11")

    # verify instance details
    ir = requests.get(f"{API}/db/instances", headers=auth_headers,
                      params={"service_id": svc_id})
    assert ir.status_code == 200
    ins_list = ir.json()
    jalsi = next((i for i in ins_list if i["instance_name"] == "JaLsi"), None)
    assert jalsi is not None, ins_list
    assert jalsi["host"] == "172.10.112.169"
    assert jalsi["port"] == 3306
    assert jalsi["instance_type"] == "slave"
    # dns1..dns4 all merged in all_dns
    for d in ("dns1.example.com", "dns2.example.com", "dns3.example.com", "dns4.example.com"):
        assert d in jalsi["all_dns"], jalsi["all_dns"]
    # cleanup
    for ins in ins_list:
        requests.delete(f"{API}/db/instances/{ins['id']}", headers=auth_headers)
    requests.delete(f"{API}/db/services/{svc_id}", headers=auth_headers)


# ---------- Combined JSON export ----------

def test_combined_export(auth_headers):
    r = requests.get(f"{API}/export/combined", headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ("generated_at", "db_config", "kubernetes_clusters", "workloads"):
        assert k in data, f"missing key {k}: {list(data.keys())}"
    assert isinstance(data["kubernetes_clusters"], list)
    assert isinstance(data["workloads"], list)
    dbc = data["db_config"]
    for k in ("db_services", "db_instances", "db_instance_metadata"):
        assert k in dbc, f"missing db_config.{k}"


# ---------- AWS instance-action guard ----------

def test_instance_action_guard_live_off(auth_headers):
    # Ensure live mode is OFF (default)
    settings = requests.get(f"{API}/aws/settings", headers=auth_headers).json()
    assert settings.get("use_live") in (False, None), settings
    r = requests.post(f"{API}/aws/instance-action", headers=auth_headers,
                      json={"instance_id": "i-abc", "action": "start"})
    assert r.status_code == 400, r.text
    assert "live" in r.text.lower()


def test_instance_action_requires_auth():
    r = requests.post(f"{API}/aws/instance-action",
                      json={"instance_id": "i-abc", "action": "start"})
    assert r.status_code in (401, 403), r.text


# ---------- Regression: services + instance manual CRUD ----------

def test_manual_service_and_instance_flow(auth_headers):
    # create service
    r = requests.post(f"{API}/db/services", headers=auth_headers,
                      json={"service_name": "TEST_iter11_svc"})
    assert r.status_code == 200, r.text
    svc = r.json()
    sid = svc["id"]
    # create instance
    r = requests.post(f"{API}/db/instances", headers=auth_headers, json={
        "service_id": sid, "instance_name": "TEST_iter11_ins",
        "host": "10.0.0.1", "port": 3306, "instance_type": "master",
    })
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    # search
    lr = requests.get(f"{API}/db/instances", headers=auth_headers,
                     params={"search": "TEST_iter11"})
    assert lr.status_code == 200
    assert any(i["id"] == iid for i in lr.json())
    # cleanup
    requests.delete(f"{API}/db/instances/{iid}", headers=auth_headers)
    requests.delete(f"{API}/db/services/{sid}", headers=auth_headers)


def test_db_export_json(auth_headers):
    r = requests.get(f"{API}/db/export-json", headers=auth_headers)
    assert r.status_code == 200, r.text
    j = r.json()
    for k in ("db_services", "db_instances", "db_instance_metadata"):
        assert k in j

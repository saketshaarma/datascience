"""Tests for AWS Discovery Dashboard (type-driven + hover details)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback: read frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break

ADMIN_EMAIL = "admin@infraforge.io"
ADMIN_PASSWORD = "Admin@12345"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"] if "access_token" in r.json() else r.json().get("token")


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---- discover all ----
def test_discover_all(headers):
    r = requests.post(f"{BASE_URL}/api/aws/discover", json={}, headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "demo"
    kinds = {k["name"]: k["value"] for k in body["by_kind"]}
    # Required kinds per statement (ebs_volume presence depends on inventory data)
    for expected in ["ec2_instance", "security_group", "route53_zone", "a_record"]:
        assert expected in kinds, f"Missing kind {expected}; got {kinds}"
    # Rough counts
    assert kinds["ec2_instance"] >= 5
    assert kinds["security_group"] >= 5
    assert kinds["a_record"] >= 20
    assert kinds["route53_zone"] >= 1


def test_resource_details_shape(headers):
    r = requests.post(f"{BASE_URL}/api/aws/discover", json={}, headers=headers, timeout=30)
    body = r.json()
    resources = body["resources"]
    by_kind = {}
    for res in resources:
        by_kind.setdefault(res["kind"], []).append(res)
        assert "details" in res and isinstance(res["details"], dict)
        assert "tags" in res and isinstance(res["tags"], dict)

    ec2 = by_kind["ec2_instance"][0]
    for k in ["private_ip", "port", "instance_type"]:
        assert k in ec2["details"], f"ec2 missing {k}: {ec2['details']}"

    ar = by_kind["a_record"][0]
    for k in ["record", "type", "value", "ttl", "zone"]:
        assert k in ar["details"], f"a_record missing {k}"
    assert ar["details"]["type"] == "A"

    rz = by_kind["route53_zone"][0]
    for k in ["zone_name", "record_count", "private"]:
        assert k in rz["details"], f"route53_zone missing {k}"

    if "ebs_volume" in by_kind:
        ebs = by_kind["ebs_volume"][0]
        for k in ["device_name", "size_gb", "volume_type", "attached_to"]:
            assert k in ebs["details"], f"ebs missing {k}"

    sg = by_kind["security_group"][0]
    assert "ports" in sg["details"]


def test_tag_options(headers):
    r = requests.get(f"{BASE_URL}/api/aws/tag-options", headers=headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "keys" in body and isinstance(body["keys"], list)
    assert "values" in body and isinstance(body["values"], dict)
    assert len(body["keys"]) > 0
    # each key present in values map
    for k in body["keys"]:
        assert k in body["values"]


def test_tag_filter_key_and_value(headers):
    # find a key/value combo from tag-options
    opts = requests.get(f"{BASE_URL}/api/aws/tag-options", headers=headers, timeout=15).json()
    picked_k, picked_v = None, None
    for k, vs in opts["values"].items():
        if vs:
            picked_k, picked_v = k, vs[0]
            break
    assert picked_k, "No tag options available"
    r = requests.post(f"{BASE_URL}/api/aws/discover",
                      json={"tag_key": picked_k, "tag_value": picked_v},
                      headers=headers, timeout=30)
    assert r.status_code == 200
    body = r.json()
    for res in body["resources"]:
        assert res["tags"].get(picked_k) == picked_v, \
            f"Resource {res['name']} does not match tag filter"


def test_tag_filter_key_only(headers):
    opts = requests.get(f"{BASE_URL}/api/aws/tag-options", headers=headers, timeout=15).json()
    picked_k = next((k for k, vs in opts["values"].items() if vs), None)
    assert picked_k
    r = requests.post(f"{BASE_URL}/api/aws/discover",
                      json={"tag_key": picked_k}, headers=headers, timeout=30)
    assert r.status_code == 200
    for res in r.json()["resources"]:
        assert picked_k in res["tags"]


def test_unauth_denied():
    r = requests.post(f"{BASE_URL}/api/aws/discover", json={}, timeout=10)
    assert r.status_code in (401, 403)

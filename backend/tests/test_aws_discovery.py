"""AWS discovery + settings endpoints tests."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:3000").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@infraforge.io"
ADMIN_PASS = "Admin@12345"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def member(admin_headers):
    email = f"TEST_member_{int(time.time())}@infraforge.io"
    payload = {"name": "TEST Member", "email": email, "password": "Member@12345"}
    r = requests.post(f"{API}/auth/register", json=payload, headers=admin_headers)
    assert r.status_code in (200, 201), r.text
    user = r.json()
    # login as member
    login = requests.post(f"{API}/auth/login", json={"email": email, "password": "Member@12345"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    yield {"id": user.get("id"), "email": email, "token": token}
    # cleanup
    try:
        requests.delete(f"{API}/auth/users/{user['id']}", headers=admin_headers)
    except Exception:
        pass


# --- tag-options ---
class TestTagOptions:
    def test_requires_auth(self):
        r = requests.get(f"{API}/aws/tag-options")
        assert r.status_code in (401, 403)

    def test_returns_keys_and_values(self, admin_headers):
        r = requests.get(f"{API}/aws/tag-options", headers=admin_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "keys" in data and "values" in data
        assert isinstance(data["keys"], list)
        assert isinstance(data["values"], dict)
        # Should include at least Role from inventory
        # (data may vary but keys should be non-empty per seed)
        assert len(data["keys"]) >= 1


# --- discover ---
class TestDiscover:
    def test_discover_all_demo(self, admin_headers):
        r = requests.post(f"{API}/aws/discover", json={}, headers=admin_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["mode"] == "demo"
        assert "total" in d and isinstance(d["total"], int)
        assert "by_kind" in d and isinstance(d["by_kind"], list)
        assert "by_source" in d and isinstance(d["by_source"], list)
        assert "resources" in d and isinstance(d["resources"], list)
        assert "region" in d
        assert "account_id" in d
        assert d["total"] == len(d["resources"])
        # Expect inventory-derived kinds
        kinds = {x["name"] for x in d["by_kind"]}
        # not asserting exact kinds since data may vary, but total>0 expected
        assert d["total"] > 0
        assert "inventory" in {x["name"] for x in d["by_source"]}

    def test_filter_by_tag_key_only(self, admin_headers):
        # get a key
        t = requests.get(f"{API}/aws/tag-options", headers=admin_headers).json()
        assert t["keys"], "no tag keys to test with"
        key = t["keys"][0]
        r = requests.post(f"{API}/aws/discover", json={"tag_key": key}, headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["filter"]["tag_key"] == key
        for res in d["resources"]:
            assert key in (res.get("tags") or {})

    def test_filter_by_tag_key_value(self, admin_headers):
        t = requests.get(f"{API}/aws/tag-options", headers=admin_headers).json()
        key = t["keys"][0]
        vals = t["values"].get(key) or []
        assert vals, "no values for key"
        val = vals[0]
        r = requests.post(f"{API}/aws/discover", json={"tag_key": key, "tag_value": val}, headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["filter"]["tag_value"] == val
        for res in d["resources"]:
            assert (res.get("tags") or {}).get(key) == val


# --- settings ---
class TestAwsSettings:
    def test_member_forbidden_get(self, member):
        r = requests.get(f"{API}/aws/settings",
                         headers={"Authorization": f"Bearer {member['token']}"})
        assert r.status_code == 403

    def test_member_forbidden_put(self, member):
        r = requests.put(f"{API}/aws/settings",
                         headers={"Authorization": f"Bearer {member['token']}",
                                  "Content-Type": "application/json"},
                         json={"access_key_id": "AKIA", "secret_access_key": "x",
                               "region": "us-east-1", "use_live": False})
        assert r.status_code == 403

    def test_admin_put_and_get_masked(self, admin_headers):
        payload = {
            "access_key_id": "AKIATESTKEY123456ABCD",
            "secret_access_key": "supersecret-value-xyz",
            "region": "ap-south-2",
            "use_live": False,
        }
        r = requests.put(f"{API}/aws/settings", json=payload, headers=admin_headers)
        assert r.status_code == 200, r.text
        assert r.json()["configured"] is True

        g = requests.get(f"{API}/aws/settings", headers=admin_headers)
        assert g.status_code == 200
        s = g.json()
        assert s["configured"] is True
        assert s["region"] == "ap-south-2"
        assert s["use_live"] is False
        assert s["access_key_id_masked"].endswith("ABCD")
        assert "AKIATESTKEY" not in s["access_key_id_masked"]
        # secret must never leak
        assert "secret_access_key" not in s
        assert "supersecret" not in str(s)

    def test_blank_keeps_previous(self, admin_headers):
        # send blank access/secret; region change
        r = requests.put(f"{API}/aws/settings",
                         json={"access_key_id": "", "secret_access_key": "",
                               "region": "eu-west-1", "use_live": False},
                         headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["configured"] is True  # should stay configured

        g = requests.get(f"{API}/aws/settings", headers=admin_headers).json()
        assert g["configured"] is True
        assert g["region"] == "eu-west-1"
        assert g["access_key_id_masked"].endswith("ABCD")

    def test_live_mode_graceful_502(self, admin_headers):
        # Enable live with fake creds; discover should fail gracefully (502)
        requests.put(f"{API}/aws/settings",
                     json={"access_key_id": "", "secret_access_key": "",
                           "region": "us-east-1", "use_live": True},
                     headers=admin_headers)
        r = requests.post(f"{API}/aws/discover", json={}, headers=admin_headers)
        # With fake creds boto3 will fail -> expect 502
        assert r.status_code == 502, f"expected 502 got {r.status_code}: {r.text}"

        # Turn live off again so dashboard stays in demo mode
        requests.put(f"{API}/aws/settings",
                     json={"access_key_id": "", "secret_access_key": "",
                           "region": "us-east-1", "use_live": False},
                     headers=admin_headers)


# --- regression endpoints ---
class TestRegression:
    def test_login(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
        assert r.status_code == 200

    def test_instances_list(self, admin_headers):
        r = requests.get(f"{API}/instances", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_db_services(self, admin_headers):
        r = requests.get(f"{API}/db/services", headers=admin_headers)
        assert r.status_code == 200

    def test_k8s_clusters(self, admin_headers):
        r = requests.get(f"{API}/k8s/clusters", headers=admin_headers)
        assert r.status_code == 200

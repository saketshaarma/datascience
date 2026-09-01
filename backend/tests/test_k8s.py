"""Iteration 5: Kubernetes Provisioning Panel backend tests.

Does NOT touch /api/instances collection; only exercises /api/k8s/* endpoints
against the k8s_clusters collection.
"""
import json
import os
import re
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://aws-inventory-hub.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@infraforge.io"
ADMIN_PASSWORD = "Admin@12345"


# ---------- fixtures (no cross-collection cleanup) ----------
@pytest.fixture(scope="module")
def admin_client():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def member_client(admin_client):
    email = "test_k8s_member@infraforge.io"
    # attempt to create; ignore if already exists
    admin_client.post(f"{API}/auth/register", json={
        "email": email, "password": "Member@12345", "name": "K8s Member"
    })
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": "Member@12345"})
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    user_id = r.json()["user"]["id"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}"})
    yield s
    # cleanup member
    admin_client.delete(f"{API}/auth/users/{user_id}")


@pytest.fixture
def sample_spec():
    return {
        "name": "TEST_k8s_cluster",
        "aws_region": "ap-south-2",
        "vpc_tag": "Pakri-analytics-db-vpc",
        "subnet_tag": "Pakri-analytics-db-subnet",
        "key_name": "pakri-key",
        "private_zone_name": "pakri.internal",
        "ami_id": "ami-0abc",
        "security_group_tags": {"Env": "prod", "Team": "data"},
        "instance_tags": {"Env": "prod", "Project": "analytics"},
        "volume_tags": {"Env": "prod"},
        "nodes": [
            {"hostname": "controller0", "instance_type": "t3.large", "root_volume_size": 80},
            {"hostname": "controller1", "instance_type": "t3.large", "root_volume_size": 80},
            {"hostname": "controller2", "instance_type": "t3.large", "root_volume_size": 80},
            {"hostname": "etcd3",       "instance_type": "t3.medium", "root_volume_size": 50},
            {"hostname": "etcd4",       "instance_type": "t3.medium", "root_volume_size": 50},
        ],
    }


# ---------- /api/k8s/preview ----------
class TestPreview:
    def test_preview_returns_json_and_hcl(self, admin_client, sample_spec):
        r = admin_client.post(f"{API}/k8s/preview", json=sample_spec)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "config_json" in body and "hcl" in body

    def test_config_json_structure(self, admin_client, sample_spec):
        r = admin_client.post(f"{API}/k8s/preview", json=sample_spec)
        cfg = json.loads(r.json()["config_json"])
        # top-level keys, exact
        for k in ["aws_region", "vpc_tag", "subnet_tag", "key_name",
                  "private_zone_name", "security_group_tags",
                  "instance_tags", "volume_tags", "nodes"]:
            assert k in cfg, f"missing top-level key {k}"
        assert cfg["aws_region"] == "ap-south-2"
        assert cfg["vpc_tag"] == "Pakri-analytics-db-vpc"
        # nodes as dict keyed nodeN
        assert isinstance(cfg["nodes"], dict)
        assert list(cfg["nodes"].keys()) == ["node1", "node2", "node3", "node4", "node5"]
        n1 = cfg["nodes"]["node1"]
        assert n1["hostname"] == "controller0"
        assert n1["instance_type"] == "t3.large"
        assert n1["root_volume_size"] == 80

    def test_hcl_contents(self, admin_client, sample_spec):
        r = admin_client.post(f"{API}/k8s/preview", json=sample_spec)
        hcl = r.json()["hcl"]
        # provider region
        assert 'provider "aws"' in hcl and 'region = "ap-south-2"' in hcl
        # locals
        assert "locals {" in hcl
        assert "instance_tags" in hcl and "volume_tags" in hcl and "security_group_tags" in hcl
        # data sources
        assert 'data "aws_vpc" "selected"' in hcl
        assert 'data "aws_subnet" "selected"' in hcl
        assert 'data "aws_route53_zone" "private"' in hcl
        assert 'Name = "Pakri-analytics-db-vpc"' in hcl
        # SG
        assert 'resource "aws_security_group"' in hcl
        # per-node aws_instance
        for i in range(1, 6):
            assert f'resource "aws_instance" "node{i}"' in hcl
            assert f'resource "aws_route53_record" "node{i}_dns"' in hcl
        # root_block_device with volume_size and merge with instance name
        assert re.search(r'root_block_device\s*\{[^}]*volume_size\s*=\s*80', hcl, re.S)
        assert 'merge(local.instance_tags, { Name = "controller0" })' in hcl
        # route53 record uses <hostname>.<zone> and instance private_ip
        assert 'name    = "controller0.pakri.internal"' in hcl
        assert "records = [aws_instance.node1.private_ip]" in hcl


# ---------- CRUD ----------
class TestClusterCRUD:
    _created_id = None

    def test_create(self, admin_client, sample_spec):
        r = admin_client.post(f"{API}/k8s/clusters", json=sample_spec)
        assert r.status_code == 200, r.text
        obj = r.json()
        assert obj["name"] == sample_spec["name"]
        assert "id" in obj and isinstance(obj["id"], str)
        assert len(obj["nodes"]) == 5
        TestClusterCRUD._created_id = obj["id"]

    def test_list_contains_created(self, admin_client):
        r = admin_client.get(f"{API}/k8s/clusters")
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()]
        assert TestClusterCRUD._created_id in ids

    def test_get_by_id(self, admin_client):
        cid = TestClusterCRUD._created_id
        r = admin_client.get(f"{API}/k8s/clusters/{cid}")
        assert r.status_code == 200
        assert r.json()["id"] == cid

    def test_update(self, admin_client, sample_spec):
        cid = TestClusterCRUD._created_id
        updated = dict(sample_spec)
        updated["aws_region"] = "us-east-1"
        r = admin_client.put(f"{API}/k8s/clusters/{cid}", json=updated)
        assert r.status_code == 200, r.text
        # verify persisted
        g = admin_client.get(f"{API}/k8s/clusters/{cid}").json()
        assert g["aws_region"] == "us-east-1"

    def test_generate_endpoint(self, admin_client):
        cid = TestClusterCRUD._created_id
        r = admin_client.post(f"{API}/k8s/clusters/{cid}/generate")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "config_json" in body and "hcl" in body
        cfg = json.loads(body["config_json"])
        assert cfg["aws_region"] == "us-east-1"
        assert "node1" in cfg["nodes"]

    def test_delete_admin_only_member_forbidden(self, member_client):
        cid = TestClusterCRUD._created_id
        r = member_client.delete(f"{API}/k8s/clusters/{cid}")
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text}"

    def test_delete_admin_ok_and_gone(self, admin_client):
        cid = TestClusterCRUD._created_id
        r = admin_client.delete(f"{API}/k8s/clusters/{cid}")
        assert r.status_code == 200, r.text
        g = admin_client.get(f"{API}/k8s/clusters/{cid}")
        assert g.status_code == 404


# ---------- Auth guard ----------
class TestAuthGuard:
    def test_preview_requires_auth(self):
        r = requests.post(f"{API}/k8s/preview", json={"name": "x", "nodes": []})
        assert r.status_code == 401

    def test_list_requires_auth(self):
        r = requests.get(f"{API}/k8s/clusters")
        assert r.status_code == 401

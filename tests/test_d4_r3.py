"""D4-R3：`/trace/serial/<sn>/` 只读追溯链（DB 版）验收测试。

演示链先枚举后固化（fixtures 实况）：SN-DEMO-001 → found=True、complete=True、
missing=[]、nodes=31、edges=42（含 REQ/BOM/PART/PO/TR/TC/ECN/git_commit 等）。
"""

import pytest
from django.core.management import call_command

from agents.models import AgentRun
from core.models import InventoryLot, Part, Project, User
from traceability.chain import build_trace_chain
from traceability.models import TraceLink


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


@pytest.fixture
def project(seeded):
    return Project.objects.get(code="DEMO-GW")


# --- 1) 演示链完整 ---------------------------------------------------------
def test_demo_chain_complete(seeded, client, project):
    client.force_login(seeded)
    response = client.get("/trace/serial/SN-DEMO-001/?format=json")
    assert response.status_code == 200
    data = response.json()
    assert data["found"] is True
    assert data["complete"] is True
    assert data["missing"] == []
    assert data["root"] == "SN-DEMO-001"
    assert len(data["nodes"]) == 31
    assert len(data["edges"]) == 37

    types = {node["node_type"] for node in data["nodes"]}
    assert {
        "inventory_lot",
        "requirement",
        "bom",
        "part",
        "purchase_order",
        "test_run",
        "test_case",
        "ecn",
        "git_commit",
    } <= types
    ids = {node["node_id"] for node in data["nodes"]}
    assert {
        "SN-DEMO-001",
        "REQ-001",
        "BOM-001",
        "PART-001",
        "PO-001",
        "TR-001",
        "TC-001",
        "ECN-001",
        "e4738a67bbe0fec85fe2e5b9258c533270b5e00f",
    } <= ids
    assert data["nodes"][0]["node_id"] == "SN-DEMO-001"  # 根在首位


# --- 2) 根未命中 -----------------------------------------------------------
def test_serial_not_found(seeded, client):
    client.force_login(seeded)
    response = client.get("/trace/serial/NO-SUCH-SN/?format=json")
    assert response.status_code == 200
    data = response.json()
    assert data["found"] is False
    assert data["complete"] is False
    assert data["nodes"] == []
    assert data["missing"] == ["serial_not_found"]


# --- 3) 根命中零链 ---------------------------------------------------------
def test_root_without_links(seeded, client, project):
    InventoryLot.objects.create(
        project=project,
        part=Part.objects.get(part_number="PART-001"),
        serial_type="serial",
        serial_number="SN-NO-LINK",
        quantity=1,
        qty_available=1,
    )
    client.force_login(seeded)
    data = client.get("/trace/serial/SN-NO-LINK/?format=json").json()
    assert data["found"] is True
    assert data["complete"] is False
    assert data["missing"] == ["no_trace_links"]
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["node_id"] == "SN-NO-LINK"


# --- 4) 悬空引用 fail-soft -------------------------------------------------
def test_dangling_reference(seeded, client, project):
    TraceLink.objects.create(
        project=project,
        from_type="inventory_lot",
        from_id="SN-DEMO-001",
        to_type="part",
        to_id="PART-999",
        relation_type="references",
    )
    client.force_login(seeded)
    data = client.get("/trace/serial/SN-DEMO-001/?format=json").json()
    assert "unresolved_reference:part:PART-999" in data["missing"]
    assert data["complete"] is False
    assert len(data["nodes"]) > 1  # 其余节点仍返回（不中断）
    assert all(node["node_id"] != "PART-999" for node in data["nodes"])


# --- 5) 边界 ---------------------------------------------------------------
def test_read_only_no_agentrun(seeded, client):
    client.force_login(seeded)
    before = (AgentRun.objects.count(), TraceLink.objects.count())
    client.get("/trace/serial/SN-DEMO-001/")
    after = (AgentRun.objects.count(), TraceLink.objects.count())
    assert before == after


def test_anonymous_redirects_to_login(seeded, client):
    response = client.get("/trace/serial/SN-DEMO-001/")
    assert response.status_code == 302


def test_json_matches_builder(seeded, client, project):
    client.force_login(seeded)
    data = client.get("/trace/serial/SN-DEMO-001/?format=json").json()
    assert data == build_trace_chain(project.pk, "inventory_lot", "SN-DEMO-001")


def test_json_is_deterministic(seeded, client):
    client.force_login(seeded)
    first = client.get("/trace/serial/SN-DEMO-001/?format=json").content
    second = client.get("/trace/serial/SN-DEMO-001/?format=json").content
    assert first == second


# --- 6) 计数回归 -----------------------------------------------------------
def test_counts_regression(seeded):
    assert TraceLink.objects.count() == 39
    assert InventoryLot.objects.count() == 3
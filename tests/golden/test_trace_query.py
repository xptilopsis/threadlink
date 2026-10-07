"""D12-R2（commit 3）：GT-TRACE-002/005/006/007 + 001/003 断言补强。

分层：全部 **T3 craft**（DB / 只读视图），无 LLM；零 LLM 断言用 monkeypatch spy。
"""

import pytest
from django.core.management import call_command

from agents.models import AgentRun
from core.models import InventoryLot, Part, Project, User
from traceability.chain import build_trace_chain
from traceability.models import TraceLink

SERIAL = "SN-DEMO-001"
ASOF = None


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


@pytest.fixture
def project(seeded):
    return Project.objects.get(code="DEMO-GW")


def _get(client, url):
    return client.get(url).json()


# --- GT-TRACE-001 断言补强：edge 关系集合 + 每节点/边 source_refs 非空 -------
def test_trace_001_edge_relations_and_refs(seeded, client):
    client.force_login(seeded)
    data = _get(client, f"/trace/serial/{SERIAL}/?format=json")
    assert data["found"] is True and data["complete"] is True and data["missing"] == []
    rels = {edge["relation_type"] for edge in data["edges"]}
    assert {"implemented_by", "sourced_from", "tested_by", "evidences", "replaces"} <= rels
    assert all(node["source_refs"] for node in data["nodes"])
    assert all(edge["source_refs"] for edge in data["edges"])


# --- GT-TRACE-002 未确认链过滤 ---------------------------------------------
def test_trace_002_unconfirmed_excluded_confirmed_included(seeded, project):
    TraceLink.objects.create(  # 未确认边
        project=project,
        from_type="inventory_lot",
        from_id=SERIAL,
        to_type="part",
        to_id="PART-001",
        relation_type="references",
    )
    payload = build_trace_chain(project.pk, "inventory_lot", SERIAL)
    assert not any(edge["relation_type"] == "references" for edge in payload["edges"])

    TraceLink.objects.filter(project=project, relation_type="references").update(
        confirmed_by_id=seeded.pk
    )
    payload2 = build_trace_chain(project.pk, "inventory_lot", SERIAL)
    assert any(edge["relation_type"] == "references" for edge in payload2["edges"])


# --- GT-TRACE-003 断言补强：零 LLM + warnings -------------------------------
def test_trace_003_zero_llm_and_warnings(seeded, client, monkeypatch):
    import agents.llm as llm_module

    def _boom(*_args, **_kwargs):
        raise AssertionError("未命中短路：LLM 不得被调用")

    monkeypatch.setattr(llm_module, "call_json", _boom)
    before = AgentRun.objects.count()
    client.force_login(seeded)
    data = _get(client, "/trace/serial/NO-SUCH-SN/?format=json")
    assert data["found"] is False and data["nodes"] == [] and data["edges"] == []
    assert data["missing"] == ["serial_not_found"]
    assert "serial_not_found" in data["warnings"]
    assert AgentRun.objects.count() == before


# 注：D12-R2 曾以 `test_trace_003_whitespace_not_fabricated` 记录「未做规范化」；
# D12-R3 已实现规范化（strip + 大小写不敏感），该缺口收口 → 用例由下方
# `test_trace_003_normalization_*` 取代（命中变体 → 31/37；未命中变体 → found=false）。


# --- GT-TRACE-005 断点 token（关系缺失） ------------------------------------
def test_trace_005_no_purchase_order_and_no_test_run(seeded, project):
    part = Part.objects.get(part_number="PART-001")
    InventoryLot.objects.create(
        project=project, part=part, serial_type="serial",
        serial_number="SN-NO-PO", quantity=1, qty_available=1,
    )
    TraceLink.objects.create(  # 唯一一条边（references），使链非零
        project=project, from_type="inventory_lot", from_id="SN-NO-PO",
        to_type="part", to_id="PART-001", relation_type="references",
        confirmed_by_id=seeded.pk,
    )
    payload = build_trace_chain(project.pk, "inventory_lot", "SN-NO-PO")
    assert "no_purchase_order" in payload["missing"]  # 无 sourced_from
    assert "no_test_run" in payload["missing"]  # 无 tested_by
    assert payload["complete"] is False


# --- GT-TRACE-006 depth / direction ----------------------------------------
def test_trace_006_depth_truncation(seeded, project):
    full = build_trace_chain(project.pk, "inventory_lot", SERIAL)
    assert full["missing"] == [] and full["complete"] is True  # depth=0（缺省）

    d1 = build_trace_chain(project.pk, "inventory_lot", SERIAL, depth=1)
    assert all(node["depth"] <= 1 for node in d1["nodes"])
    assert "depth_truncated" in d1["missing"] and d1["complete"] is False

    dmax = build_trace_chain(project.pk, "inventory_lot", SERIAL, depth=99)  # 裁无可裁
    assert dmax["missing"] == [] and dmax["complete"] is True


def test_trace_006_directed_variants(seeded, project):
    fwd = build_trace_chain(project.pk, "inventory_lot", SERIAL, direction="forward")
    bwd = build_trace_chain(project.pk, "inventory_lot", SERIAL, direction="backward")
    assert fwd["found"] and bwd["found"]
    # 有向 ≠ 无向全链（规模更小）
    full = build_trace_chain(project.pk, "inventory_lot", SERIAL)
    assert len(fwd["nodes"]) < len(full["nodes"])
    assert len(bwd["nodes"]) < len(full["nodes"])


def test_trace_006_view_param_validation(seeded, client):
    client.force_login(seeded)
    assert client.get(f"/trace/serial/{SERIAL}/?format=json&depth=1").status_code == 200
    assert client.get(f"/trace/serial/{SERIAL}/?depth=0").status_code == 200
    assert client.get(f"/trace/serial/{SERIAL}/?depth=-1").status_code == 400
    assert client.get(f"/trace/serial/{SERIAL}/?depth=abc").status_code == 400
    assert client.get(f"/trace/serial/{SERIAL}/?direction=forward").status_code == 200
    assert client.get(f"/trace/serial/{SERIAL}/?direction=backward").status_code == 200
    assert client.get(f"/trace/serial/{SERIAL}/?direction=sideways").status_code == 400


# --- GT-TRACE-006 补充：forward + depth 组合（遍历层方向过滤 → 返回层深度截断）--
def test_trace_006_forward_with_depth(seeded, project):
    fwd1 = build_trace_chain(project.pk, "inventory_lot", SERIAL, depth=1, direction="forward")
    # 方向过滤（遍历层）先于深度截断（返回层）：节点深度 ≤1 且为 forward 可达子集
    assert fwd1["found"] is True
    assert all(node["depth"] <= 1 for node in fwd1["nodes"])
    # forward 有向子图（≤1 跳）= 根 + 其 from→to 邻居
    fwd_all = build_trace_chain(project.pk, "inventory_lot", SERIAL, direction="forward")
    assert set(fwd1["nodes"][i]["node_id"] for i in range(len(fwd1["nodes"]))) <= set(
        node["node_id"] for node in fwd_all["nodes"]
    )


# --- GT-TRACE-003 边界2 输入规范化（strip + 大小写不敏感） -------------------
def test_trace_003_normalization_variants_hit_same_chain(seeded, client):
    """小写 / 前后空格 / 混合 三种变体 → 命中同一链（31/37）。"""

    client.force_login(seeded)
    variants = ["sn-demo-001", "%20SN-DEMO-001%20", "%20Sn-Demo-001%20"]
    for variant in variants:
        data = _get(client, f"/trace/serial/{variant}/?format=json")
        assert data["found"] is True, variant
        assert data["complete"] is True, variant
        assert len(data["nodes"]) == 31 and len(data["edges"]) == 37, variant


def test_trace_003_normalization_not_found_unchanged(seeded, client):
    """规范化后仍不存在 → found=false（不编造）。"""

    client.force_login(seeded)
    data = _get(client, "/trace/serial/%20sn-does-not-exist%20/?format=json")
    assert data["found"] is False
    assert data["nodes"] == []
    assert data["missing"] == ["serial_not_found"]


# --- GT-TRACE-007 批次（lot）反查 -------------------------------------------
def test_trace_007_lot_query(seeded, client):
    client.force_login(seeded)
    data = _get(client, "/trace/serial/LOT-DCDC-001/?format=json")
    assert data["found"] is True
    assert data["nodes"][0]["node_id"] == "LOT-DCDC-001"
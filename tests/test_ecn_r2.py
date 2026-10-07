"""D11-R2：ECN 影响投影（零写）+ 正式应用（写回 + 确认）。

GT-ECN-001…006 逐条 + 写边界（分析零写）/ 回滚 / 前置门；口径见 ADR-0015。
"""

import json
from datetime import date

import pytest
from django.core.management import call_command
from django.db.utils import IntegrityError

from agents.models import AgentRun
from core.ecn import EcnApplyError, apply_ecn, project_ecn_impact
from core.models import BomItem, ECN, ECNImpact, Part, Project, User
from traceability.models import TraceLink

ASOF = date(2026, 3, 5)


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


@pytest.fixture
def project(seeded):
    return Project.objects.get(code="DEMO-GW")


def _ecn(project, number="ECN-001"):
    return ECN.objects.get(project=project, ecn_number=number)


def _counts():
    return (
        ECNImpact.objects.count(),
        TraceLink.objects.count(),
        AgentRun.objects.count(),
        BomItem.objects.count(),
        Part.objects.count(),
    )


def _affects(project, number="ECN-001"):
    return TraceLink.objects.filter(
        project=project, from_type="ecn", from_id=number, relation_type="affects"
    )


# --- GT-ECN-001 ------------------------------------------------------------
def test_gt_ecn_001_impact_scope(seeded, project):
    result = project_ecn_impact(_ecn(project), as_of_date=ASOF)
    assert result["effective"] is True
    assert [x["affected_id"] for x in result["impacts"]["bom_nodes"]] == ["BI-001"]
    assert [x["affected_id"] for x in result["impacts"]["inventory_lots"]] == ["LOT-DCDC-001"]
    assert [x["affected_id"] for x in result["impacts"]["purchase_orders"]] == ["PO-001"]
    assert sorted(x["affected_id"] for x in result["impacts"]["test_cases"]) == ["TC-001", "TC-009"]
    # consistency：TC-009 缺 affects 边（fixtures TL-029..032 无 TC-009）
    assert "missing_affects_edge:test_case:TC-009" in result["consistency"]


# --- GT-ECN-002(a)：分析全零写 ---------------------------------------------
def test_gt_ecn_002a_analysis_zero_write(seeded, project):
    ecn = _ecn(project)
    item = BomItem.objects.get(bom__project=project, item_no="BI-001")
    before_counts = _counts()
    edges_before = list(TraceLink.objects.values_list("id", "confirmed_by_id", "created_by_id"))
    ei_before = list(
        ECNImpact.objects.values_list("id", "affected_type", "affected_id", "impact_type")
    )

    project_ecn_impact(ecn, as_of_date=ASOF)

    assert _counts() == before_counts
    item.refresh_from_db()
    assert item.part.part_number == "PART-001"  # 未写回
    assert list(TraceLink.objects.values_list("id", "confirmed_by_id", "created_by_id")) == edges_before
    assert (
        list(ECNImpact.objects.values_list("id", "affected_type", "affected_id", "impact_type"))
        == ei_before
    )


# --- GT-ECN-002(b)：应用写回 + 边确认 --------------------------------------
def test_gt_ecn_002b_apply(seeded, project):
    ecn = _ecn(project)
    result = apply_ecn(ecn, seeded, as_of_date=ASOF)

    item = BomItem.objects.get(bom__project=project, item_no="BI-001")
    assert item.part.part_number == "PART-002"
    assert result["created_edges"] == 1  # TC-009 边补建（确认态）
    assert result["rewritten"] == [{"bom_item": "BI-001", "from": "PART-001", "to": "PART-002"}]

    edge = TraceLink.objects.get(
        project=project, from_type="ecn", from_id="ECN-001",
        relation_type="affects", to_type="test_case", to_id="TC-009",
    )
    assert edge.confirmed_by_id == seeded.pk
    assert edge.created_by_id == seeded.pk
    assert edge.confirmed_at is not None

    # 已确认边不动（created_by 保持 NULL）
    existing = TraceLink.objects.get(
        project=project, from_type="ecn", from_id="ECN-001",
        relation_type="affects", to_type="bom_item", to_id="BI-001",
    )
    assert existing.created_by_id is None


# --- GT-ECN-003：状态门 -----------------------------------------------------
def test_gt_ecn_003_status_gate(seeded, project):
    ecn2 = _ecn(project, "ECN-002")  # reviewing
    result = project_ecn_impact(ecn2, as_of_date=ASOF)
    assert result["effective"] is False
    assert "status_not_effective" in result["warnings"]
    with pytest.raises(EcnApplyError):
        apply_ecn(ecn2, seeded, as_of_date=ASOF)


# --- GT-ECN-004：日期门 -----------------------------------------------------
def test_gt_ecn_004_missing_effective_date(seeded, project):
    ecn = _ecn(project)
    ecn.effective_date = None
    ecn.save(update_fields=["effective_date"])
    result = project_ecn_impact(ecn)
    assert result["effective"] is False
    assert "missing_effective_date" in result["warnings"]
    with pytest.raises(EcnApplyError):
        apply_ecn(ecn, seeded)


def test_gt_ecn_date_boundary(seeded, project):
    ecn = _ecn(project)
    assert project_ecn_impact(ecn, as_of_date=date(2026, 3, 4))["effective"] is False
    assert project_ecn_impact(ecn, as_of_date=date(2026, 3, 5))["effective"] is True


# --- GT-ECN-005：唯一 + 确认 + NULL 语义 -----------------------------------
def test_gt_ecn_005_unique_and_confirmed(seeded, project):
    ecn = _ecn(project)
    apply_ecn(ecn, seeded, as_of_date=ASOF)
    edges = _affects(project)
    assert edges.count() == 5  # ECN-001 有 5 个 EI
    assert all(edge.confirmed_by_id is not None for edge in edges)
    with pytest.raises(IntegrityError):
        TraceLink.objects.create(
            project=project, from_type="ecn", from_id="ECN-001",
            to_type="bom_item", to_id="BI-001", relation_type="affects",
        )


# --- GT-ECN-006：幂等重跑 ---------------------------------------------------
def test_gt_ecn_006_idempotent(seeded, project):
    ecn = _ecn(project)
    apply_ecn(ecn, seeded, as_of_date=ASOF)
    ei_after = ECNImpact.objects.count()
    edges_after = _affects(project).count()

    project_ecn_impact(ecn, as_of_date=ASOF)  # 重算（零写）
    second = apply_ecn(ecn, seeded, as_of_date=ASOF)

    assert ECNImpact.objects.count() == ei_after
    assert _affects(project).count() == edges_after
    assert second["created_edges"] == 0
    assert second["confirmed_edges"] == 0
    assert second["rewritten"] == []  # 已替换 → 不再写回


# --- 回滚 -------------------------------------------------------------------
def test_apply_rollback_on_failure(seeded, project, monkeypatch):
    ecn = _ecn(project)
    import core.ecn as ecn_module

    def boom(_project, _part):  # noqa: ANN001
        raise RuntimeError("boom")

    monkeypatch.setattr(ecn_module, "_replacement_part", boom)
    edges_before = TraceLink.objects.count()

    with pytest.raises(RuntimeError):
        apply_ecn(ecn, seeded, as_of_date=ASOF)

    assert TraceLink.objects.count() == edges_before  # 新建边回滚
    item = BomItem.objects.get(bom__project=project, item_no="BI-001")
    assert item.part.part_number == "PART-001"  # 零残留


# --- 投影 fail-soft + 确定性 + 命令冒烟 ------------------------------------
def test_unresolved_fail_soft(seeded, project):
    ecn = _ecn(project)
    ECNImpact.objects.create(
        ecn=ecn, affected_type="bom_item", affected_id="BI-999", impact_type="affected"
    )
    result = project_ecn_impact(ecn, as_of_date=ASOF)
    assert {"affected_type": "bom_item", "affected_id": "BI-999"} in result["unresolved"]


def test_projection_deterministic(seeded, project):
    ecn = _ecn(project)
    dump = lambda r: json.dumps(r, sort_keys=True, ensure_ascii=False, default=str)  # noqa: E731
    assert dump(project_ecn_impact(ecn, as_of_date=ASOF)) == dump(
        project_ecn_impact(ecn, as_of_date=ASOF)
    )


def test_commands_smoke(seeded, project, capsys):
    call_command("ecn_impact", "ECN-001")
    out = capsys.readouterr().out
    assert "ECN-001" in out and "BI-001" in out

    call_command("ecn_apply", "ECN-001")
    out2 = capsys.readouterr().out
    assert "ECN-001" in out2 and "PART-002" in out2
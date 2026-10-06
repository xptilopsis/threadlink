"""D7-R2：traceability 纯审计确认 + human-rejected 落档 + chain source_refs 回填。

- §2：``approve_traceability`` 纯审计确认（零实体写入 / 幂等 / 前置校验）；
- §4：``reject`` best-effort 落 ``<FAILURES_ROOT>/<agent_dir>/v1/failures/<date>-human-rejected-<id>.md``
  （三 agent 各 1 例；写失败不阻塞 reject）；
- §5：``build_trace_chain`` 节点/边 ``source_refs`` 自 ``TraceLink.evidence`` 聚合去重（根节点 = []，
  无 evidence → []，两次 build 逐字节一致）。
"""

import json
from datetime import date

import pytest
from django.core.management import call_command

from agents.confirmation import ConfirmationError, reject
from agents.models import AgentRun
from agents.traceability import approve_traceability
from core.models import Bom, BomItem, InventoryLot, Project, Requirement, User
from traceability.chain import build_trace_chain
from traceability.models import TraceLink

SERIAL = "SN-DEMO-001"


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


@pytest.fixture
def project(seeded):
    return Project.objects.get(code="DEMO-GW")


def _make_run(
    project,
    *,
    agent_name="traceability",
    status="needs_review",
    ref_ok=True,
    output_json=None,
):
    return AgentRun.objects.create(
        project=project,
        agent_name=agent_name,
        status=status,
        prompt_id="prompt.traceability.chain",
        prompt_version="v1",
        model="test-model",
        temperature=0,
        input_json={},
        input_hash="d" * 64,
        output_json=output_json if output_json is not None else {"summary": "示例摘要"},
        output_schema_valid=True,
        reference_check_passed=ref_ok,
        invalid_references=[],
    )


def _counts():
    return (
        Requirement.objects.count(),
        Bom.objects.count(),
        BomItem.objects.count(),
        TraceLink.objects.count(),
        AgentRun.objects.count(),
    )


# --- §2 approve_traceability（纯审计确认） ---------------------------------
def test_approve_traceability_audit_only(seeded, project):
    run = _make_run(project)
    before = _counts()
    result = approve_traceability(run, seeded)
    after = _counts()

    run.refresh_from_db()
    assert run.status == "success"
    assert run.confirmed_by_id == seeded.pk
    assert run.confirmed_at is not None
    assert result["audit_only"] is True
    assert before == after  # 零实体写入 + AgentRun 计数不变


def test_approve_traceability_idempotent(seeded, project):
    run = _make_run(project)
    approve_traceability(run, seeded)
    with pytest.raises(ConfirmationError):
        approve_traceability(run, seeded)


def test_approve_traceability_requires_reference_check(seeded, project):
    run = _make_run(project, ref_ok=False)
    with pytest.raises(ConfirmationError):
        approve_traceability(run, seeded)


def test_approve_traceability_rejects_non_needs_review(seeded, project):
    run = _make_run(project, status="failed")
    with pytest.raises(ConfirmationError):
        approve_traceability(run, seeded)


# --- §4 human-rejected 落档 -------------------------------------------------
@pytest.mark.parametrize(
    "agent_name,agent_dir",
    [
        ("requirement", "requirement_agent"),
        ("bom_selection", "bom_selection_agent"),
        ("traceability", "traceability_agent"),
    ],
)
def test_reject_writes_human_rejected_sample(
    settings, tmp_path, seeded, project, agent_name, agent_dir
):
    settings.FAILURES_ROOT = tmp_path
    run = _make_run(project, agent_name=agent_name, output_json={"summary": f"{agent_name} 摘要"})
    reject(run, seeded)

    run.refresh_from_db()
    assert run.status == "rejected"
    path = (
        tmp_path
        / agent_dir
        / "v1"
        / "failures"
        / f"{date.today().isoformat()}-human-rejected-{run.pk}.md"
    )
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "human-rejected" in text
    assert str(run.pk) in text
    assert f"{agent_name} 摘要" in text


def test_reject_survives_sample_write_failure(settings, tmp_path, seeded, project):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    settings.FAILURES_ROOT = blocker  # 作为目录用 → mkdir 失败，被 best-effort 吞掉
    run = _make_run(project)

    reject(run, seeded)  # 不抛

    run.refresh_from_db()
    assert run.status == "rejected"


# --- §5 source_refs 回填 ----------------------------------------------------
def test_source_refs_backfill_from_evidence(seeded, project):
    link = (
        TraceLink.objects.filter(
            project=project, from_type="inventory_lot", from_id=SERIAL
        )
        .order_by("pk")
        .first()
    )
    assert link is not None
    evidence = [{"type": "document", "id": "DOC-001", "locator": None, "snippet": None}]
    link.evidence = evidence
    link.save(update_fields=["evidence"])

    payload = build_trace_chain(project.pk, "inventory_lot", SERIAL)

    root = next(n for n in payload["nodes"] if n["node_id"] == SERIAL)
    assert root["source_refs"] == []  # 根节点恒为 []

    other_id = link.to_id if link.from_id == SERIAL else link.from_id
    other_node = next(n for n in payload["nodes"] if n["node_id"] == other_id)
    assert other_node["source_refs"] == evidence

    edge = next(
        e for e in payload["edges"] if {e["from_node_id"], e["to_node_id"]} == {link.from_id, link.to_id}
    )
    assert edge["source_refs"] == evidence


def test_source_refs_empty_without_evidence(seeded, project):
    payload = build_trace_chain(project.pk, "inventory_lot", SERIAL)
    assert payload["nodes"] and payload["edges"]
    assert all(n["source_refs"] == [] for n in payload["nodes"])
    assert all(e["source_refs"] == [] for e in payload["edges"])


def test_source_refs_deterministic_with_evidence(seeded, project):
    link = (
        TraceLink.objects.filter(project=project, from_type="inventory_lot", from_id=SERIAL)
        .order_by("pk")
        .first()
    )
    link.evidence = [
        {"type": "document", "id": "DOC-001"},
        {"type": "document", "id": "DOC-001"},  # 重复 → 去重
        {"type": "part", "id": "PART-002"},
    ]
    link.save(update_fields=["evidence"])

    first = build_trace_chain(project.pk, "inventory_lot", SERIAL)
    second = build_trace_chain(project.pk, "inventory_lot", SERIAL)
    dump = lambda p: json.dumps(p, sort_keys=True, ensure_ascii=False, default=str)
    assert dump(first) == dump(second)  # 逐字节一致

    # 去重：{DOC-001} 只出现一次
    other_id = link.to_id if link.from_id == SERIAL else link.from_id
    other_node = next(n for n in first["nodes"] if n["node_id"] == other_id)
    assert len(other_node["source_refs"]) == 2
"""D6-R3：approve → 初版 BOM（craft）+ bom_selection live 端到端。

- craft：approve 建 draft `Bom` + 逐候选 `BomItem`（共享 `substitute_group`）+ `replaces` `TraceLink` + 同行 `success`；
  幂等、回滚、AgentRun 计数不变；requirement 派发不回归（见 `tests/test_bom_selection_r2.py`）。
- live（`@pytest.mark.live`，本机）：真实一次调用，断言引擎权威输出 + `source_refs` 非空核验通过。
"""

import pytest
from django.core.management import call_command

from agents.bom_selection import approve_bom_selection, run_bom_selection_agent
from agents.confirmation import ConfirmationError
from agents.models import AgentRun
from core.models import Bom, BomItem, Project, User
from core.selection import Criteria
from traceability.models import TraceLink


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


@pytest.fixture
def project(seeded):
    return Project.objects.get(code="DEMO-GW")


def _output_json():
    return {
        "agent_name": "bom_selection",
        "summary": "s",
        "request_params": [],
        "candidates": [
            {
                "part_number": "PART-002",
                "name": "P2",
                "lifecycle_status": "active",
                "score": 0.9479,
                "rationale": "r2",
                "replaces_part_id": "PART-017",
                "source_refs": [{"type": "part", "id": "PART-002"}],
            },
            {
                "part_number": "PART-001",
                "name": "P1",
                "lifecycle_status": "active",
                "score": 0.8724,
                "rationale": "r1",
                "source_refs": [{"type": "part", "id": "PART-001"}],
            },
            {
                "part_number": "PART-018",
                "name": "P18",
                "lifecycle_status": "active",
                "score": 0.0,
                "rationale": "r18",
                "source_refs": [{"type": "part", "id": "PART-018"}],
            },
        ],
        "recommended_part_id": "PART-002",
        "trace_refs": [],
        "warnings": [],
    }


def _make_run(project, output_json=None, status="needs_review", ref_ok=True):
    return AgentRun.objects.create(
        project=project,
        agent_name="bom_selection",
        status=status,
        prompt_id="prompt.bom.selection",
        prompt_version="v1",
        model="test-model",
        temperature=0,
        input_json={},
        input_hash="c" * 64,
        output_json=output_json or _output_json(),
        output_schema_valid=True,
        reference_check_passed=ref_ok,
        invalid_references=[],
    )


# --- craft: approve --------------------------------------------------------
def test_approve_creates_draft_bom(seeded, project):
    run = _make_run(project)
    before_runs = AgentRun.objects.count()
    before_links = TraceLink.objects.count()

    result = approve_bom_selection(run, seeded)

    assert result["items"] == 3 and result["links"] == 1
    bom = Bom.objects.get(bom_no=result["bom_no"])
    assert bom.status == "draft"
    assert bom.version == f"v0.1-sel-{run.pk}"
    assert bom.created_by_id == seeded.pk

    items = BomItem.objects.filter(bom=bom)
    assert items.count() == 3
    assert {item.substitute_group for item in items} == {f"SG-SEL-{run.pk}"}
    assert {item.quantity for item in items} == {1}

    link = TraceLink.objects.get(
        from_type="part",
        from_id="PART-002",
        to_type="part",
        to_id="PART-017",
        relation_type="replaces",
    )
    assert link.source == "agent" and link.agent_run_id == run.pk
    assert TraceLink.objects.count() == before_links + 1

    run.refresh_from_db()
    assert run.status == "success"
    assert run.confirmed_by_id == seeded.pk and run.confirmed_at is not None
    assert AgentRun.objects.count() == before_runs  # 不新增 AgentRun


def test_approve_twice_is_idempotent(seeded, project):
    run = _make_run(project)
    approve_bom_selection(run, seeded)
    before_bom = Bom.objects.count()
    with pytest.raises(ConfirmationError):
        approve_bom_selection(run, seeded)
    assert Bom.objects.count() == before_bom


def test_approve_rejects_unverified_run(seeded, project):
    run = _make_run(project, ref_ok=False)
    before_bom = Bom.objects.count()
    with pytest.raises(ConfirmationError):
        approve_bom_selection(run, seeded)
    assert Bom.objects.count() == before_bom  # 未新增（fixture 已有 BOM-001）


def test_approve_rolls_back_on_error(monkeypatch, seeded, project):
    run = _make_run(project)
    before_bom = Bom.objects.count()
    before_item = BomItem.objects.count()

    def boom(*args, **kwargs):
        raise RuntimeError("item boom")

    monkeypatch.setattr(BomItem.objects, "create", boom)
    with pytest.raises(RuntimeError):
        approve_bom_selection(run, seeded)

    run.refresh_from_db()
    assert run.status == "needs_review"  # 整体回滚
    assert Bom.objects.count() == before_bom
    assert BomItem.objects.count() == before_item


# --- live（本机；沙箱 -m "not live" 跳过）----------------------------------
@pytest.mark.live
def test_live_bom_selection_end_to_end(seeded, project):
    before = AgentRun.objects.count()
    summary = run_bom_selection_agent(project, Criteria(), seeded)
    assert summary["ok"] is True
    assert summary["candidates"] == 3
    assert AgentRun.objects.count() == before + 1

    output = summary["output"]
    assert [c["part_number"] for c in output["candidates"]] == [
        "PART-002",
        "PART-001",
        "PART-018",
    ]
    assert [str(c["score"]) for c in output["candidates"]] == ["0.9479", "0.8724", "0.0"]
    assert output["recommended_part_id"] == "PART-002"
    for candidate in output["candidates"]:
        assert candidate["rationale"]
        assert any("\u4e00" <= ch <= "\u9fff" for ch in candidate["rationale"])  # 含中文
        assert candidate["source_refs"]  # AC-004：非空

    run = AgentRun.objects.get(pk=summary["agent_run_id"])
    assert run.status == "needs_review"
    assert run.reference_check_passed is True
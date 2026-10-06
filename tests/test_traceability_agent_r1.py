"""D7-R1：Traceability Agent 管道 + FailureReason 扩展 + 入口 craft 测试（沙箱）。

- §1：``FailureReason += ambiguous`` round-trip + 消费方（``verify_references``）回归；
- §2：未命中短路（零 LLM / 零 AgentRun / 零 TraceLink）；命中 → DB 权威链 + LLM 文案合并 +
  ``output_json`` 可再解析为 ``TraceabilityAgentOutput``；核验失败（幻觉 trace_ref）→ failed；
- §4：端点匿名 302 / 未命中 200 / command fake 冒烟；
- §5.2：审计一致性回归（requirement / bom_selection 落库 ``output_json`` 可按冻结 schema 反序列化）。
"""

import json
import re

import pytest
from django.core.management import call_command

from agents import llm
from agents.models import AgentRun
from agents.requirement import run_requirement_agent
from agents.traceability import (
    TraceRefSuggestion,
    TraceabilityExplanation,
    run_traceability_agent,
)
from agents.verification import verify_references
from core.models import Bom, BomItem, BomStatus, Document, Part, Project, User
from core.numbering import numbering_suspended
from core.selection import Criteria
from schemas.agent_outputs import (
    OUTPUT_MODELS,
    AgentName,
    AgentRunRead,
    BomSelectionAgentOutput,
    FailureReason,
    InvalidReference,
    RequirementAgentOutput,
    TraceabilityAgentOutput,
)
from traceability.models import TraceLink

TRACE_PROMPT_ID = "prompt.traceability.chain"


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
    prompt_id=TRACE_PROMPT_ID,
    output_json=None,
):
    return AgentRun.objects.create(
        project=project,
        agent_name=agent_name,
        status=status,
        prompt_id=prompt_id,
        prompt_version="v1",
        model="test-model",
        temperature=0,
        input_json={},
        input_hash="c" * 64,
        output_json=output_json or {},
        output_schema_valid=True,
        reference_check_passed=ref_ok,
        invalid_references=[],
    )


# --- §1 FailureReason += ambiguous -----------------------------------------
def test_failure_reason_ambiguous_roundtrip():
    ref = InvalidReference(entity_type="part", entity_id="PART-999", reason="ambiguous")
    assert ref.reason is FailureReason.AMBIGUOUS

    payload = {
        "id": "1",
        "agent_name": "traceability",
        "prompt_id": TRACE_PROMPT_ID,
        "prompt_version": "v1",
        "model": "m",
        "temperature": 0.0,
        "input_json": {},
        "input_hash": "a" * 64,
        "output_schema_valid": True,
        "status": "failed",
        "invalid_references": [
            {"entity_type": "bom_item", "entity_id": "ITEM-DUP", "reason": "ambiguous"}
        ],
        "created_at": "2026-10-06T00:00:00Z",
    }
    read = AgentRunRead.model_validate(payload)
    assert read.invalid_references[0].reason is FailureReason.AMBIGUOUS


def test_verify_references_ambiguous_reason(seeded, project):
    """消费方回归：多命中 → ``reason="ambiguous"``（D4-R1 登记项② 对账）。"""

    part = Part.objects.filter(project=project).first()
    b1 = Bom.objects.create(
        project=project, name="t1", version="v-t1", status=BomStatus.DRAFT, created_by=seeded
    )
    b2 = Bom.objects.create(
        project=project, name="t2", version="v-t2", status=BomStatus.DRAFT, created_by=seeded
    )
    with numbering_suspended():  # 绕过应用层「项目内编号唯一」预检，构造同 project 多命中
        BomItem.objects.create(bom=b1, part=part, quantity=1, item_no="ITEM-DUP")
        BomItem.objects.create(bom=b2, part=part, quantity=1, item_no="ITEM-DUP")

    invalid = verify_references(project.pk, [{"type": "bom_item", "id": "ITEM-DUP"}])
    assert [item.reason for item in invalid] == ["ambiguous"]


# --- §2 未命中短路 ----------------------------------------------------------
def test_pipeline_not_found_short_circuits(monkeypatch, seeded, project):
    from agents import traceability as module

    def spy(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("未命中短路：LLM 不得被调用")

    monkeypatch.setattr(module.llm, "call_json", spy)
    before_runs = AgentRun.objects.count()
    before_links = TraceLink.objects.count()

    summary = run_traceability_agent(project, "SN-DOES-NOT-EXIST", seeded)

    assert summary["found"] is False
    assert summary["agent_run_id"] is None
    assert AgentRun.objects.count() == before_runs
    assert TraceLink.objects.count() == before_links
    output = summary["output"]
    assert output["found"] is False and output["complete"] is False
    assert output["nodes"] == [] and output["edges"] == []
    assert output["missing"] == ["serial_not_found"]
    assert output["warnings"] == ["serial_not_found"]


def test_endpoint_not_found_returns_200(monkeypatch, seeded, project, client):
    from agents import traceability as module

    def spy(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("未命中短路：LLM 不得被调用")

    monkeypatch.setattr(module.llm, "call_json", spy)
    client.force_login(seeded)
    resp = client.post(
        "/agents/traceability/run/",
        data=json.dumps({"project_id": "DEMO-GW", "serial_number": "SN-DOES-NOT-EXIST"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["found"] is False
    assert "agent_run" not in body


# --- §2 命中（DB 权威 + LLM 文案合并） -------------------------------------
def test_pipeline_hit_merges_db_authoritative(monkeypatch, seeded, project):
    from agents import traceability as module

    parsed = TraceabilityExplanation(summary="演示链中文摘要", trace_refs=[])
    run = _make_run(project)
    monkeypatch.setattr(
        module.llm,
        "call_json",
        lambda *a, **k: llm.CallResult(parsed, "", None, 0.0, "json_object", agent_run=run),
    )

    before = AgentRun.objects.count()
    summary = run_traceability_agent(project, "SN-DEMO-001", seeded)

    assert summary["ok"] is True
    assert AgentRun.objects.count() == before  # 同一行更新（mock：真实路径 call_json 恰好 +1）
    run.refresh_from_db()
    assert run.status == "needs_review" and run.reference_check_passed is True
    # D6 教训回归：落库 output_json 必须可按冻结 schema 反序列化
    output = TraceabilityAgentOutput.model_validate(run.output_json)
    assert output.found is True and output.complete is True
    assert len(output.nodes) == 31 and len(output.edges) == 37
    assert output.summary == "演示链中文摘要"  # LLM 文案
    assert output.nodes[0].node_id == "SN-DEMO-001"  # DB 权威根


# --- §2 核验失败（幻觉 trace_ref） -----------------------------------------
def test_pipeline_hallucinated_trace_ref_fails(monkeypatch, seeded, project):
    from agents import traceability as module

    parsed = TraceabilityExplanation(
        summary="摘要",
        trace_refs=[
            TraceRefSuggestion(
                from_type="ecn",
                from_id="ECN-999",
                to_type="part",
                to_id="PART-001",
                relation_type="affects",
            )
        ],
    )
    run = _make_run(project)
    monkeypatch.setattr(
        module.llm,
        "call_json",
        lambda *a, **k: llm.CallResult(parsed, "", None, 0.0, "json_object", agent_run=run),
    )

    before = AgentRun.objects.count()
    summary = run_traceability_agent(project, "SN-DEMO-001", seeded)

    assert summary["ok"] is False
    assert summary["invalid_references"]
    assert AgentRun.objects.count() == before  # 同一行更新
    run.refresh_from_db()
    assert run.status == "failed" and run.reference_check_passed is False
    assert any(item["entity_id"] == "ECN-999" for item in run.invalid_references)
    # 核验失败不进人工确认队列
    assert not AgentRun.objects.filter(agent_name="traceability", status="needs_review").exists()


# --- §5.2 审计一致性回归（防 D6 同类缺陷） ----------------------------------
def test_audit_requirement_output_json_reparses(monkeypatch, seeded, project):
    from agents import requirement as req_module

    document = Document.objects.filter(project=project, doc_no="DOC-001").first()
    parsed = RequirementAgentOutput(
        agent_name="requirement",
        cards=[
            {
                "title": "审计回归卡",
                "content": "内容",
                "source_type": "email",
                "confidence": 0.5,
                "source_refs": [{"type": "document", "id": "DOC-001"}],
            }
        ],
    )
    run = _make_run(
        project,
        agent_name="requirement",
        prompt_id="prompt.requirement.extract",
        output_json=parsed.model_dump(mode="json"),
    )
    monkeypatch.setattr(
        req_module.llm,
        "call_json",
        lambda *a, **k: llm.CallResult(parsed, "", None, 0.0, "json_object", agent_run=run),
    )
    run_requirement_agent(project, document, seeded)
    run.refresh_from_db()

    reparsed = OUTPUT_MODELS[AgentName.REQUIREMENT].model_validate(run.output_json)
    assert reparsed.cards


def test_audit_bom_output_json_reparses(monkeypatch, seeded, project):
    from agents import bom_selection as bom_module

    parsed = bom_module.BomExplanationOutput(
        summary="审计回归",
        candidates=[
            bom_module.CandidateExplanation(part_number="PART-002", rationale="r"),
            bom_module.CandidateExplanation(part_number="PART-001", rationale="r"),
            bom_module.CandidateExplanation(part_number="PART-018", rationale="r"),
        ],
    )
    run = _make_run(
        project,
        agent_name="bom_selection",
        prompt_id="prompt.bom.selection",
        output_json={"stale": True},
    )
    monkeypatch.setattr(
        bom_module.llm,
        "call_json",
        lambda *a, **k: llm.CallResult(parsed, "", None, 0.0, "json_object", agent_run=run),
    )
    bom_module.run_bom_selection_agent(project, Criteria(), seeded)
    run.refresh_from_db()

    reparsed = OUTPUT_MODELS[AgentName.BOM_SELECTION].model_validate(run.output_json)
    assert reparsed.candidates


# --- §4 入口 ----------------------------------------------------------------
def test_traceability_endpoint_anonymous_redirects(seeded, client):
    resp = client.post(
        "/agents/traceability/run/", data="{}", content_type="application/json"
    )
    assert resp.status_code == 302


def test_command_fake_smoke(monkeypatch, settings, seeded, project):
    monkeypatch.setattr(settings, "LLM_BACKEND", "fake")
    before = AgentRun.objects.count()
    call_command("run_traceability", "SN-DEMO-001", "--project", "DEMO-GW")
    assert AgentRun.objects.count() == before  # fake 不落库


def test_command_not_found_message(seeded, project, capsys):
    call_command("run_traceability", "SN-DOES-NOT-EXIST", "--project", "DEMO-GW")
    out = capsys.readouterr().out
    assert "未命中，无 run 产生" in out


# --- live（本机执行：pytest -q -m live） -----------------------------------
@pytest.mark.live
def test_live_traceability_sn_demo_001(seeded, project):
    before = AgentRun.objects.count()
    summary = run_traceability_agent(project, "SN-DEMO-001", seeded, temperature=0.0)

    assert summary["ok"] is True
    assert AgentRun.objects.count() == before + 1
    run = AgentRun.objects.get(pk=summary["agent_run_id"])
    assert run.status == "needs_review"
    assert run.reference_check_passed is True

    output = TraceabilityAgentOutput.model_validate(run.output_json)
    assert output.found is True and output.complete is True
    assert len(output.nodes) == 31 and len(output.edges) == 37
    assert output.summary and re.search(r"[\u4e00-\u9fff]", output.summary)
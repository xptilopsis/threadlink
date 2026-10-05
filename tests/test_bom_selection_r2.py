"""D6-R2：BOM Selection Agent 管道 + 派发 + 入口 craft 测试（沙箱）。

- 引擎权威：LLM **不能**改写 score / 价格 / 交期 / 排序；只提供 rationale / summary / replaces 建议；
- 核验：幻觉 `replaces_part_id` → failed + `invalid_references` 非空；
- 派发：`requirement` approve 不回归、`bom_selection` reject 生效、`bom_selection` approve → 未实现消息且无写入、未知 agent 跳过；
- 入口：端点匿名 302、command fake 冒烟（不落库）。
"""

import pytest
from django.conf import settings
from django.core.management import call_command

from agents import llm
from agents.bom_selection import (
    BomExplanationOutput,
    CandidateExplanation,
    run_bom_selection_agent,
)
from agents.models import AgentRun
from core.models import Project, Requirement, User
from core.selection import Criteria


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


@pytest.fixture
def project(seeded):
    return Project.objects.get(code="DEMO-GW")


def _make_run(project, *, agent_name="bom_selection", status="needs_review", ref_ok=True, output_json=None):
    return AgentRun.objects.create(
        project=project,
        agent_name=agent_name,
        status=status,
        prompt_id="prompt.bom.selection" if agent_name == "bom_selection" else "prompt.requirement.extract",
        prompt_version="v1",
        model="test-model",
        temperature=0,
        input_json={},
        input_hash="b" * 64,
        output_json=output_json or {"candidates": []},
        output_schema_valid=True,
        reference_check_passed=ref_ok,
        invalid_references=[],
    )


def _explanation(entries):
    return BomExplanationOutput(
        summary="测试摘要",
        candidates=[CandidateExplanation(**entry) for entry in entries],
    )


# --- 引擎权威 ---------------------------------------------------------------
def test_pipeline_engine_authoritative(monkeypatch, seeded, project):
    from agents import bom_selection as module

    parsed = _explanation(
        [
            {"part_number": "PART-002", "rationale": "PART-002 中文理由"},
            {"part_number": "PART-001", "rationale": "PART-001 中文理由"},
            {"part_number": "PART-018", "rationale": "PART-018 中文理由"},
        ]
    )
    run = _make_run(project)
    monkeypatch.setattr(
        module.llm,
        "call_json",
        lambda *a, **k: llm.CallResult(parsed, "", None, 0.0, "json_object", agent_run=run),
    )

    summary = run_bom_selection_agent(project, Criteria(), seeded)
    assert summary["ok"] is True
    output = summary["output"]
    assert [c["part_number"] for c in output["candidates"]] == ["PART-002", "PART-001", "PART-018"]
    # 引擎权威：score 由引擎 total_score/100 提供，LLM 未参与
    assert output["candidates"][0]["score"] == pytest.approx(0.9479, abs=1e-6)
    assert output["candidates"][1]["score"] == pytest.approx(0.8724, abs=1e-6)
    assert output["candidates"][0]["unit_price"] == "45.0000"
    assert output["candidates"][0]["lead_time_days"] == 14
    assert output["recommended_part_id"] == "PART-002"
    # LLM 只提供文案
    assert output["candidates"][0]["rationale"] == "PART-002 中文理由"
    assert output["summary"] == "测试摘要"
    run.refresh_from_db()
    assert run.status == "needs_review" and run.reference_check_passed is True


def test_pipeline_hallucinated_replaces_fails(monkeypatch, seeded, project):
    from agents import bom_selection as module

    parsed = _explanation(
        [
            {"part_number": "PART-002", "rationale": "理由", "replaces_part_id": "PART-999"},
            {"part_number": "PART-001", "rationale": "理由"},
            {"part_number": "PART-018", "rationale": "理由"},
        ]
    )
    run = _make_run(project)
    monkeypatch.setattr(
        module.llm,
        "call_json",
        lambda *a, **k: llm.CallResult(parsed, "", None, 0.0, "json_object", agent_run=run),
    )

    before = AgentRun.objects.count()
    summary = run_bom_selection_agent(project, Criteria(), seeded)
    assert summary["ok"] is False
    assert summary["invalid_references"]
    assert AgentRun.objects.count() == before  # 恰好 +0（同行更新）
    run.refresh_from_db()
    assert run.status == "failed" and run.reference_check_passed is False
    assert any(item["entity_id"] == "PART-999" for item in run.invalid_references)


# --- 派发 -------------------------------------------------------------------
def _post_action(client, user, run, action):
    client.force_login(user)
    return client.post(
        "/admin/agents/agentrun/",
        {"action": action, "_selected_action": [str(run.pk)]},
        follow=True,
    )


def test_dispatch_bom_approve_not_implemented(seeded, client, project):
    run = _make_run(project)
    response = _post_action(client, seeded, run, "approve_selected")
    assert response.status_code == 200
    assert "未实现" in response.content.decode()
    run.refresh_from_db()
    assert run.status == "needs_review"  # 无写入


def test_dispatch_bom_reject_works(seeded, client, project):
    run = _make_run(project)
    _post_action(client, seeded, run, "reject_selected")
    run.refresh_from_db()
    assert run.status == "rejected"
    assert run.confirmed_by_id == seeded.pk


def test_dispatch_unknown_agent_skipped(seeded, client, project):
    run = _make_run(project, agent_name="traceability")
    _post_action(client, seeded, run, "approve_selected")
    run.refresh_from_db()
    assert run.status == "needs_review"


def test_dispatch_requirement_approve_not_regressed(seeded, client, project):
    run = _make_run(
        project,
        agent_name="requirement",
        output_json={
            "agent_name": "requirement",
            "cards": [
                {
                    "title": "回归卡",
                    "content": "内容",
                    "source_type": "email",
                    "confidence": 0.5,
                    "source_refs": [{"type": "document", "id": "DOC-001"}],
                }
            ],
        },
    )
    _post_action(client, seeded, run, "approve_selected")
    run.refresh_from_db()
    assert run.status == "success"
    assert Requirement.objects.filter(agent_run=run).count() == 1


# --- 入口 -------------------------------------------------------------------
def test_bom_endpoint_anonymous_redirects(seeded, client):
    response = client.post(
        "/agents/bom-selection/run/", data="{}", content_type="application/json"
    )
    assert response.status_code == 302


def test_command_fake_smoke(monkeypatch, settings, seeded):
    monkeypatch.setattr(settings, "LLM_BACKEND", "fake")
    before = AgentRun.objects.count()
    call_command("run_bom_selection", "--project", "DEMO-GW")
    assert AgentRun.objects.count() == before  # fake 不落库
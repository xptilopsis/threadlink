"""D5-R3：人工确认（approve / reject）craft 测试。

沙箱无 LLM 出网、且 pytest 用独立测试库（生产库 run 13/14/15 不在此），故：
- craft：构造 `needs_review` 行覆盖 approve/reject/幂等/前置/计数/回滚；
- live 端到端（生产库 run 13/14/15 的 approve×2 + reject×1）由**本机人工**执行（见汇报）。
"""

import pytest
from django.core.management import call_command

from agents.confirmation import ConfirmationError, approve, reject
from agents.models import AgentRun
from core.models import Project, Requirement, RequirementParam, User
from traceability.models import TraceLink
from traceability.services import resolve_entity


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


@pytest.fixture
def project(seeded):
    return Project.objects.get(code="DEMO-GW")


def _payload(cards=2):
    return {
        "agent_name": "requirement",
        "summary": "测试用",
        "cards": [
            {
                "title": f"需求{i}",
                "content": f"内容{i}",
                "source_type": "email",
                "priority": "high",
                "confidence": 0.9,
                "params": [
                    {
                        "name": "input_voltage",
                        "operator": "gte",
                        "value_num": 5,
                        "unit": "V",
                        "is_mandatory": True,
                    }
                ],
                "source_refs": [{"type": "document", "id": "DOC-001"}],
            }
            for i in range(1, cards + 1)
        ],
    }


def _make_run(project, output_json, status="needs_review", ref_ok=True):
    return AgentRun.objects.create(
        project=project,
        agent_name="requirement",
        status=status,
        prompt_id="prompt.requirement.extract",
        prompt_version="v1",
        model="test-model",
        temperature=0,
        input_json={"document_id": "DOC-001"},
        input_hash="a" * 64,
        output_json=output_json,
        output_schema_valid=True,
        reference_check_passed=ref_ok,
        invalid_references=[],
    )


# --- approve ---------------------------------------------------------------
def test_approve_creates_requirements_params_links(seeded, project):
    run = _make_run(project, _payload(2))
    before_req = Requirement.objects.count()
    before_link = TraceLink.objects.count()
    before_run = AgentRun.objects.count()

    codes = approve(run, seeded)

    assert len(codes) == 2
    assert codes == ["REQ-006", "REQ-007"]  # 现有 5 → 连续编号
    assert Requirement.objects.count() == before_req + 2
    assert TraceLink.objects.count() == before_link + 2
    assert AgentRun.objects.count() == before_run  # **不新增 AgentRun 行**

    run.refresh_from_db()
    assert run.status == "success"
    assert run.confirmed_by_id == seeded.pk
    assert run.confirmed_at is not None

    for requirement in Requirement.objects.filter(code__in=codes):
        assert requirement.status == "confirmed"
        assert requirement.priority == "high"
        assert requirement.source_type == "email"
        assert requirement.agent_run_id == run.pk
        assert RequirementParam.objects.filter(requirement=requirement).count() == 1

    # TraceLink 端点可回查（复用 R1 解析服务）
    for link in TraceLink.objects.filter(from_id__in=codes):
        assert link.from_type == "requirement" and link.to_type == "document"
        assert link.relation_type == "derived_from"
        resolve_entity(project.pk, "requirement", link.from_id)
        resolve_entity(project.pk, "document", link.to_id)


def test_approve_twice_is_idempotent(seeded, project):
    run = _make_run(project, _payload(1))
    approve(run, seeded)
    before_req = Requirement.objects.count()
    with pytest.raises(ConfirmationError):
        approve(run, seeded)
    assert Requirement.objects.count() == before_req


# --- reject ----------------------------------------------------------------
def test_reject_writes_nothing(seeded, project):
    run = _make_run(project, _payload(1))
    before_req = Requirement.objects.count()
    before_run = AgentRun.objects.count()
    reject(run, seeded)
    run.refresh_from_db()
    assert run.status == "rejected"
    assert run.confirmed_by_id == seeded.pk
    assert run.confirmed_at is not None
    assert Requirement.objects.count() == before_req
    assert AgentRun.objects.count() == before_run


# --- 前置校验 ---------------------------------------------------------------
def test_failed_run_cannot_be_approved(seeded, project):
    run = _make_run(project, _payload(1), status="failed", ref_ok=False)
    with pytest.raises(ConfirmationError):
        approve(run, seeded)


def test_unverified_run_cannot_be_approved(seeded, project):
    run = _make_run(project, _payload(1), status="needs_review", ref_ok=False)
    with pytest.raises(ConfirmationError):
        approve(run, seeded)


def test_already_rejected_cannot_be_rejected_again(seeded, project):
    run = _make_run(project, _payload(1))
    reject(run, seeded)
    with pytest.raises(ConfirmationError):
        reject(run, seeded)


# --- 回滚 -------------------------------------------------------------------
def test_approve_rolls_back_on_error(seeded, project, monkeypatch):
    run = _make_run(project, _payload(2))
    before_req = Requirement.objects.count()

    def boom(*args, **kwargs):
        raise RuntimeError("link boom")

    monkeypatch.setattr(TraceLink.objects, "create", boom)
    with pytest.raises(RuntimeError):
        approve(run, seeded)

    run.refresh_from_db()
    assert run.status == "needs_review"  # 整体回滚
    assert Requirement.objects.count() == before_req
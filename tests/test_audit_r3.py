"""D11-R3 §2：AgentRun 审计不变量 + 队列可用性 + 落档对应性。

不变量依据 `docs/interface_contract.md` §6 写入规则 0–7 与绑定规则（L258）。
"""

from datetime import date

import pytest
from django.core.management import call_command

from agents.confirmation import reject
from agents.models import AgentRun
from agents.traceability import approve_traceability
from core.models import Project, User


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)


@pytest.fixture
def admin(seeded):
    return User.objects.get(username="admin")


@pytest.fixture
def project(seeded):
    return Project.objects.get(code="DEMO-GW")


def _assert_invariants(run):
    if run.status == "failed":
        assert run.error, f"#{run.pk} failed 须 error 非空"
        assert run.confirmed_by_id is None and run.confirmed_at is None
    elif run.status == "needs_review":
        assert run.confirmed_by_id is None and run.confirmed_at is None
        assert run.output_schema_valid is True
        assert run.reference_check_passed is True
    elif run.status == "success":
        assert run.confirmed_by_id is not None and run.confirmed_at is not None
        assert run.output_schema_valid is True
        assert run.reference_check_passed is True
    elif run.status == "rejected":
        assert run.confirmed_by_id is not None and run.confirmed_at is not None
    else:
        raise AssertionError(f"非法 status: {run.status}")


def _make_run(project, *, status="needs_review", agent_name="traceability"):
    return AgentRun.objects.create(
        project=project,
        agent_name=agent_name,
        status=status,
        prompt_id="prompt.traceability.chain",
        prompt_version="v1",
        model="test-model",
        temperature=0,
        input_json={},
        input_hash="e" * 64,
        output_json={"summary": "示例"},
        output_schema_valid=True,
        reference_check_passed=True,
        invalid_references=[],
    )


# --- 全库不变量（fixtures 重导后） ------------------------------------------
def test_agentrun_invariants_all_rows(seeded):
    rows = list(AgentRun.objects.all())
    assert rows, "fixtures 应含 AgentRun 样例"
    for run in rows:
        _assert_invariants(run)


def test_fixtures_have_failed_sample(seeded):
    failed = AgentRun.objects.filter(status="failed")
    assert failed.exists()
    for run in failed:
        assert run.error and run.invalid_references


# --- 路径构造断言（各状态各 1 例） ------------------------------------------
def test_approve_path_invariants(admin, project):
    run = _make_run(project)  # traceability → 纯审计确认
    approve_traceability(run, admin)
    run.refresh_from_db()
    assert run.status == "success"
    _assert_invariants(run)


def test_reject_path_invariants(admin, project, settings, tmp_path):
    settings.FAILURES_ROOT = tmp_path
    run = _make_run(project)
    reject(run, admin)
    run.refresh_from_db()
    assert run.status == "rejected"
    _assert_invariants(run)


def test_failed_path_invariants(admin, project):
    run = _make_run(project, status="failed")
    run.error = "boom"
    run.save(update_fields=["error"])
    _assert_invariants(run)


# --- 队列可用性（过滤 × 搜索 × 详情读） -------------------------------------
def test_agentrun_queue_filters_search_detail(seeded, admin, client):
    client.force_login(admin)
    run = AgentRun.objects.first()
    assert client.get("/admin/agents/agentrun/").status_code == 200
    assert (
        client.get("/admin/agents/agentrun/?agent_name=requirement&status=success").status_code
        == 200
    )
    assert client.get("/admin/agents/agentrun/?q=prompt").status_code == 200
    assert client.get(f"/admin/agents/agentrun/{run.pk}/change/").status_code == 200


# --- 落档 ↔ rejected 行对应性（抽查 1 例） ---------------------------------
def test_rejected_run_has_human_rejected_sample(admin, project, settings, tmp_path):
    settings.FAILURES_ROOT = tmp_path
    run = _make_run(project, agent_name="traceability")
    reject(run, admin)
    run.refresh_from_db()

    sample = (
        tmp_path
        / "traceability_agent"
        / "v1"
        / "failures"
        / f"{date.today().isoformat()}-human-rejected-{run.pk}.md"
    )
    assert sample.exists(), "rejected 行须有对应 human-rejected 落档"
    text = sample.read_text(encoding="utf-8")
    assert f"run id: {run.pk}" in text
    assert "human-rejected" in text
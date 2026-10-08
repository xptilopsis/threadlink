"""D13-R1：演示场景 2 的 criteria 单页表单 + ``run_bom_selection --full``。

- 表单：GET/POST、登录必填、成功重定向 AgentRun 详情、错误路径不 500；
- 命令：``--full`` 输出完整 rationale，默认截断 80 字符并以 … 标注。
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.urls import reverse

from core.models import Project, User

FORM_URL = "/agents/bom-selection/form/"

VALID_POST = {
    "project": "DEMO-GW",
    "voltage_min": "9",
    "voltage_max": "36",
    "current_min": "5",
    "temp_min": "-40",
    "temp_max": "85",
    "ip_min": "65",
    "cost_max": "",
}


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


def test_anonymous_is_redirected(db, client):
    response = client.get(FORM_URL)
    assert response.status_code == 302
    assert "/login" in response["Location"]


def test_get_renders_form(seeded, client):
    client.force_login(seeded)
    response = client.get(FORM_URL)
    assert response.status_code == 200
    html = response.content.decode()
    assert "运行选型" in html
    assert 'name="voltage_min"' in html


def test_post_runs_agent_and_redirects(seeded, client, monkeypatch):
    client.force_login(seeded)
    captured = {}

    def fake(project, criteria, user, **kwargs):
        captured["criteria"] = criteria
        captured["project"] = project
        return {"ok": True, "agent_run_id": 42, "candidates": 3}

    monkeypatch.setattr("agents.bom_selection.run_bom_selection_agent", fake)
    response = client.post(FORM_URL, VALID_POST)

    assert response.status_code == 302
    assert response["Location"] == reverse("admin:agents_agentrun_change", args=[42])
    assert captured["project"].code == "DEMO-GW"
    assert str(captured["criteria"].voltage_min) == "9"
    assert captured["criteria"].cost_max is None


def test_post_agent_error_is_not_500(seeded, client, monkeypatch):
    client.force_login(seeded)

    def boom(*args, **kwargs):
        raise RuntimeError("llm boom")

    monkeypatch.setattr("agents.bom_selection.run_bom_selection_agent", boom)
    response = client.post(FORM_URL, VALID_POST)

    assert response.status_code == 200
    assert "llm boom" in response.content.decode()


def test_post_no_candidates_is_not_500(seeded, client, monkeypatch):
    client.force_login(seeded)

    def empty(*args, **kwargs):
        return {"ok": False, "reason": "no_candidates", "candidates": 0}

    monkeypatch.setattr("agents.bom_selection.run_bom_selection_agent", empty)
    response = client.post(FORM_URL, VALID_POST)

    assert response.status_code == 200
    assert "no_candidates" in response.content.decode()


def test_post_unknown_project(seeded, client):
    client.force_login(seeded)
    response = client.post(FORM_URL, {**VALID_POST, "project": "NOPE"})
    assert response.status_code == 200
    assert "project 不存在" in response.content.decode()


def test_command_full_flag(seeded, monkeypatch):
    long_rationale = "x" * 120
    output = {
        "agent_name": "bom_selection",
        "summary": None,
        "request_params": [],
        "candidates": [
            {
                "part_number": "PART-001",
                "name": "P1",
                "lifecycle_status": "active",
                "unit_price": "1.00",
                "lead_time_days": 3,
                "score": 0.9,
                "rationale": long_rationale,
                "source_refs": [{"type": "part", "id": "PART-001"}],
            }
        ],
        "recommended_part_id": "PART-001",
        "trace_refs": [],
        "warnings": [],
    }

    def fake(*args, **kwargs):
        return {"ok": True, "agent_run_id": 1, "candidates": 1, "output": output}

    monkeypatch.setattr(
        "core.management.commands.run_bom_selection.run_bom_selection_agent", fake
    )

    truncated = StringIO()
    call_command("run_bom_selection", stdout=truncated)
    assert "…" in truncated.getvalue()
    assert long_rationale not in truncated.getvalue()

    full = StringIO()
    call_command("run_bom_selection", "--full", stdout=full)
    assert long_rationale in full.getvalue()


def test_project_loaded(seeded):
    assert Project.objects.filter(code="DEMO-GW").exists()
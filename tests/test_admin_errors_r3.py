"""D11-R3 §3：自定义 Admin 面板 / action 的异常注入（不 500，消息含失败/异常字样）。

- WorkOrderAdmin 齐套面板：`tests/test_planning_r1.py::test_workorder_admin_panel_error_not_500`（已覆盖，引用不重造）；
- 非 staff / 未登录 → 302/403：`tests/test_permissions_r3.py`（已覆盖）。
"""

import pytest
from django.core.management import call_command

from agents.models import AgentRun
from core.models import ECN, Project, User


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)


@pytest.fixture
def admin(seeded):
    return User.objects.get(username="admin")


@pytest.fixture
def project(seeded):
    return Project.objects.get(code="DEMO-GW")


def _post_action(client, app, model, action, pks):
    return client.post(
        f"/admin/{app}/{model}/",
        {"action": action, "_selected_action": [str(pk) for pk in pks]},
        follow=True,
    )


# --- ECN 面板异常 -----------------------------------------------------------
def test_ecn_impact_panel_error_not_500(admin, project, client, monkeypatch):
    import core.ecn as ecn_module

    monkeypatch.setattr(ecn_module, "project_ecn_impact", lambda _ecn: (_ for _ in ()).throw(RuntimeError("boom")))
    ecn = ECN.objects.get(project=project, ecn_number="ECN-001")
    client.force_login(admin)
    resp = client.get(f"/admin/core/ecn/{ecn.pk}/change/")
    assert resp.status_code == 200
    assert "分析失败" in resp.content.decode()


# --- ECN 应用 action 异常 ---------------------------------------------------
def test_ecn_apply_action_error_not_500(admin, project, client, monkeypatch):
    import core.ecn as ecn_module

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(ecn_module, "apply_ecn", boom)
    ecn = ECN.objects.get(project=project, ecn_number="ECN-001")
    client.force_login(admin)
    resp = _post_action(client, "core", "ecn", "apply_selected_ecn", [ecn.pk])
    assert resp.status_code == 200
    assert "应用失败" in resp.content.decode()


# --- AgentRun 派发 action 异常 ----------------------------------------------
def test_agentrun_action_error_not_500(admin, client, monkeypatch):
    import agents.traceability as traceability_module

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(traceability_module, "approve_traceability", boom)
    run = AgentRun.objects.filter(agent_name="traceability").first()
    assert run is not None
    client.force_login(admin)
    resp = _post_action(client, "agents", "agentrun", "approve_selected", [run.pk])
    assert resp.status_code == 200
    assert "异常" in resp.content.decode()
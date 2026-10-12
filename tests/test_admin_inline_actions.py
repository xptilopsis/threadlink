"""D13：changelist 行内操作列（去批量下拉 + 中文行内操作 + 确认弹窗资源）。"""

from types import SimpleNamespace

import pytest
from django.contrib import admin as django_admin
from django.core.management import call_command
from django.urls import reverse

from agents.admin import AgentRunAdmin
from agents.models import AgentRun
from core.admin import GitRepoAdmin
from core.models import User


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


def test_project_changelist_has_inline_actions(seeded, client):
    client.force_login(seeded)

    response = client.get(reverse("admin:core_project_changelist"))

    assert response.status_code == 200
    html = response.content.decode()
    assert "tl-inline-actions" in html
    assert ">Edit<" in html
    assert ">Delete<" in html
    # 删除走行内 POST（复用 delete_selected），带确认弹窗属性
    assert 'data-action-name="delete_selected"' in html
    assert "data-confirm=" in html


def test_changelist_loads_inline_action_assets(seeded, client):
    client.force_login(seeded)

    html = client.get(reverse("admin:core_project_changelist")).content.decode()

    assert "admin_inline_actions.css" in html
    assert "admin_inline_actions.js" in html


def test_ecn_changelist_has_inline_apply_action(seeded, client):
    client.force_login(seeded)

    html = client.get(reverse("admin:core_ecn_changelist")).content.decode()

    assert "Apply ECN" in html
    assert 'data-action-name="apply_selected_ecn"' in html


def test_document_changelist_has_inline_extract_action(seeded, client):
    client.force_login(seeded)

    html = client.get(reverse("admin:core_document_changelist")).content.decode()

    assert "Run requirement extraction" in html
    assert 'data-action-name="run_requirement_agent_action"' in html


def test_agentrun_inline_actions_by_status():
    admin_obj = AgentRunAdmin(AgentRun, django_admin.site)

    pending = admin_obj.inline_actions(SimpleNamespace(status="needs_review"))
    labels = [spec[0] for spec in pending]
    assert labels == ["Approve", "Reject"]
    assert pending[0][1] == "approve_selected"
    assert pending[1][1] == "reject_selected"

    done = admin_obj.inline_actions(SimpleNamespace(status="success"))
    assert done == []


def test_readonly_admin_hides_edit_delete():
    assert GitRepoAdmin.tl_inline_edit is False
    assert GitRepoAdmin.tl_inline_delete is False


def test_bulk_verify_actions_have_confirm_dialog():
    from pathlib import Path

    from django.conf import settings

    js = (
        Path(settings.BASE_DIR) / "core" / "static" / "core" / "admin_inline_actions.js"
    ).read_text(encoding="utf-8")
    assert "changelist-form" in js
    assert "approve_selected" in js
    assert "reject_selected" in js
    assert "BATCH_CONFIRM" in js
    assert "batch:" in js
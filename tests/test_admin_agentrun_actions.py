"""AgentRun 页演示动线：待处理文档 + 一键需求提取 + 详情页批准（D13）。"""

import pytest
from django.core.management import call_command
from django.urls import reverse

from agents.admin import AgentRunAdmin
from agents.models import AgentRun
from core.models import Document, User


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


def test_changelist_shows_pending_documents(seeded, client):
    from core.models import Project

    Document.objects.create(
        project=Project.objects.get(code="DEMO-GW"),
        doc_no="DOC-TEST-1",
        title="刚上传的客户邮件",
        doc_type="email",
        file_path="documents/x.eml",
    )
    client.force_login(seeded)

    response = client.get(reverse("admin:agents_agentrun_changelist"))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Pending documents" in html
    assert "Extract requirements" in html
    # 黄色高亮行强制深色文字（保证明/暗主题下均可读）
    assert "background:#fff3cd;color:#333" in html
    # admin 内导航：无需手敲 URL 即可到达 criteria 表单与追溯链页
    assert "Open BOM selection form" in html
    assert "/agents/bom-selection/form/" in html
    assert "Open trace chain (SN-DEMO-001)" in html
    assert "/trace/serial/SN-DEMO-001/" in html


def test_extract_requirement_redirects_to_run(seeded, client, monkeypatch):
    client.force_login(seeded)
    doc = Document.objects.filter(doc_no="DOC-002").first() or Document.objects.first()
    monkeypatch.setattr(
        "agents.requirement.run_requirement_agent",
        lambda p, d, u: {"ok": True, "agent_run_id": 987, "cards": 5},
    )

    response = client.get(
        reverse("admin:agents_agentrun_extract_requirement", args=[doc.pk])
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("admin:agents_agentrun_change", args=[987])


def test_extract_requirement_error_is_not_500(seeded, client, monkeypatch):
    client.force_login(seeded)
    doc = Document.objects.first()

    def boom(p, d, u):
        raise RuntimeError("llm down")

    monkeypatch.setattr("agents.requirement.run_requirement_agent", boom)

    response = client.get(
        reverse("admin:agents_agentrun_extract_requirement", args=[doc.pk])
    )

    assert response.status_code == 302  # 回队列并带错误消息，不 500


def test_approve_now_redirects_back(seeded, client, monkeypatch):
    client.force_login(seeded)
    run = (
        AgentRun.objects.filter(status="needs_review").first()
        or AgentRun.objects.first()
    )
    seen = {}
    monkeypatch.setattr(
        AgentRunAdmin,
        "_handle",
        lambda self, request, queryset, action, verb: seen.update(action=action),
    )

    response = client.get(reverse("admin:agents_agentrun_approve_now", args=[run.pk]))

    assert response.status_code == 302
    assert seen.get("action") == "approve"

def test_detail_success_banner_and_history_removed(seeded, client):
    client.force_login(seeded)
    run = AgentRun.objects.filter(status="success").first()
    assert run is not None

    response = client.get(reverse("admin:agents_agentrun_change", args=[run.pk]))

    assert response.status_code == 200
    html = response.content.decode()
    # 成功栏：与待处理文档行相同的黄色高亮 + 黑字「Approved」
    assert "background:#fff3cd" in html
    assert "Approved" in html
    assert "color:#333" in html
    assert 'class="button"' in html
    # 右上角 History 按钮已移除
    assert "/history/" not in html


def test_success_banner_target_depends_on_agent(seeded, client):
    client.force_login(seeded)

    # bom_selection 批准成功 → 下一步看 S3 追溯链（而非 BOM 表单）
    bom = AgentRun.objects.filter(
        agent_name="bom_selection", status="success"
    ).first()
    assert bom is not None
    html = client.get(
        reverse("admin:agents_agentrun_change", args=[bom.pk])
    ).content.decode()
    assert "Open trace chain (SN-DEMO-001)" in html
    assert "/trace/serial/SN-DEMO-001/" in html
    assert "Open BOM agent" not in html

    # 其它（如 requirement）批准成功 → 只给 BOM 选型入口；
    # requirement run 不生成 BOM，故不显示「BOM 已存在」提醒，也不给自动跳转 BOM 按钮
    req = AgentRun.objects.filter(agent_name="requirement", status="success").first()
    assert req is not None
    html = client.get(
        reverse("admin:agents_agentrun_change", args=[req.pk])
    ).content.decode()
    assert "Open BOM agent" in html
    assert "Open BOM BOM-" not in html

    assert 'data-confirm="A BOM already exists' not in html
    assert 'data-key="regen-bom"' not in html


def test_admin_index_has_quick_links(seeded, client):
    client.force_login(seeded)

    response = client.get(reverse("admin:index"))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Quick links" in html
    assert "演示快捷入口" not in html
    assert "/agents/bom-selection/form/" in html
    assert "/trace/serial/SN-DEMO-001/" in html

def test_bom_selection_pending_shows_trace_chain(seeded, client):
    client.force_login(seeded)

    # bom_selection run 在批准前（needs_review）就应给出追溯链入口，而非仅批准后
    run = AgentRun.objects.filter(agent_name="bom_selection").first()
    assert run is not None
    AgentRun.objects.filter(pk=run.pk).update(status="needs_review")

    html = client.get(
        reverse("admin:agents_agentrun_change", args=[run.pk])
    ).content.decode()
    assert "Pending approval" in html
    assert ">Approve</a>" in html
    assert "Open trace chain (SN-DEMO-001)" in html
    assert "/trace/serial/SN-DEMO-001/" in html
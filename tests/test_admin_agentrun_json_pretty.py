"""AgentRun 详情页：input/output 以「可读卡片」呈现（D13 修复，非原始 JSON）。"""

import pytest
from django.contrib import admin as django_admin
from django.core.management import call_command
from django.urls import reverse

from agents.admin import AgentRunAdmin
from agents.models import AgentRun
from core.models import User


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


# --- 渲染器单测（构造数据，无需 DB）---


def test_requirement_renderer():
    html = AgentRunAdmin(AgentRun, django_admin.site)._requirement_html(
        {
            "summary": "客户邮件五点需求。",
            "cards": [
                {
                    "title": "宽压直流供电",
                    "content": "支持 9-36V DC，额定电流不低于 5A。",
                    "priority": "high",
                    "confidence": 0.95,
                    "params": [
                        {
                            "name": "输入电压",
                            "operator": "range",
                            "value_min": "9",
                            "value_max": "36",
                            "unit": "V DC",
                            "is_mandatory": True,
                        }
                    ],
                    "source_refs": [{"type": "document", "id": "DOC-001"}],
                }
            ],
        }
    )
    assert "Requirement cards: 1" in html
    assert "宽压直流供电" in html
    assert "9 ~ 36 V DC" in html
    assert "DOC-001" in html


def test_bom_renderer():
    html = AgentRunAdmin(AgentRun, django_admin.site)._bom_html(
        {
            "recommended_part_id": "PART-002",
            "candidates": [
                {
                    "part_number": "PART-002",
                    "name": "DCDC-45W",
                    "score": 0.9479,
                    "unit_price": "45.0000",
                    "currency": "CNY",
                    "lead_time_days": 14,
                    "lifecycle_status": "active",
                    "rationale": "交期最短、成本中等。",
                }
            ],
        }
    )
    assert "Candidates: 1" in html
    assert "recommended PART-002" in html
    assert "score 0.9479" in html
    assert "lead time 14 d" in html


def test_trace_renderer():
    html = AgentRunAdmin(AgentRun, django_admin.site)._trace_html(
        {"root": "SN-DEMO-001", "found": True, "complete": True, "nodes": [{}, {}], "edges": [{}]}
    )
    assert "root SN-DEMO-001" in html
    assert "found yes" in html
    assert "nodes 2" in html
    assert "edges 1" in html


# --- 详情页集成 ---


def test_change_page_renders_for_every_run(seeded, client):
    client.force_login(seeded)
    runs = list(AgentRun.objects.all())
    assert runs
    for run in runs:
        response = client.get(reverse("admin:agents_agentrun_change", args=[run.pk]))
        assert response.status_code == 200
        html = response.content.decode()
        assert "var(--darkened-bg" in html  # 主题变量：明/暗自适应


def test_requirement_detail_hides_raw_json(seeded, client):
    client.force_login(seeded)
    run = AgentRun.objects.filter(agent_name="requirement").first()
    assert run is not None

    response = client.get(reverse("admin:agents_agentrun_change", args=[run.pk]))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Requirement cards" in html  # rendered as readable cards
    assert "Raw JSON" not in html  # no raw JSON output


def test_agentrun_changelist_still_ok(seeded, client):
    client.force_login(seeded)
    response = client.get(reverse("admin:agents_agentrun_changelist"))
    assert response.status_code == 200
    # 队列（摘要列）不受影响
    assert django_admin.site.is_registered(AgentRun)
"""D3-R1：Requirement / TestCase / TestRun 的 Admin CRUD 验收测试。

前置数据由 ``load_demo_seed --flush`` 提供（每个测试在事务内独立导入）。
seed 的 ``admin``（fixture USER-001）由 loader 按字典 §1 / ADR-0003 的
``role=admin ⟺ is_superuser/is_staff=True`` 映射直接建成超管，测试不再提升。

预置常数（先数后写，来自 fixtures/demo_seed.json）：
- requirements.priority：high=3，medium=2
- test_runs.sample_serial：SN-DEMO-001=10，SN-DEMO-002=2
- 计数：Requirement=5，RequirementParam=12，TestCase=10，TestRun=12
"""

import pytest
from django.core.management import call_command

from core.models import (
    Project,
    Requirement,
    RequirementParam,
    User,
)
from core.models import TestCase as CaseModel
from core.models import TestRun as RunModel


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


def _result_count(response):
    return response.context["cl"].queryset.count()


# --- 1) GET 200 ------------------------------------------------------------
def test_admin_changelist_pages_200(seeded, client):
    client.force_login(seeded)
    for url in (
        "/admin/core/requirement/",
        "/admin/core/testcase/",
        "/admin/core/testrun/",
    ):
        assert client.get(url).status_code == 200, url


def test_requirement_change_form_200(seeded, client):
    client.force_login(seeded)
    requirement = Requirement.objects.order_by("id").first()
    response = client.get(f"/admin/core/requirement/{requirement.pk}/change/")
    assert response.status_code == 200


# --- 2) 过滤 / 搜索 --------------------------------------------------------
def test_requirement_search_returns_one(seeded, client):
    client.force_login(seeded)
    response = client.get("/admin/core/requirement/", {"q": "REQ-001"})
    assert response.status_code == 200
    assert _result_count(response) == 1


def test_requirement_filter_priority_high(seeded, client):
    client.force_login(seeded)
    response = client.get("/admin/core/requirement/", {"priority": "high"})
    assert response.status_code == 200
    assert _result_count(response) == 3


def test_testrun_search_by_sample_serial(seeded, client):
    client.force_login(seeded)
    response = client.get("/admin/core/testrun/", {"q": "SN-DEMO-001"})
    assert response.status_code == 200
    assert _result_count(response) == 10


# --- 3) 计数回归 -----------------------------------------------------------
def test_counts_regression(seeded):
    assert Requirement.objects.count() == 5
    assert RequirementParam.objects.count() == 12
    assert CaseModel.objects.count() == 10
    assert RunModel.objects.count() == 12


# --- 4) 编号集成冒烟 -------------------------------------------------------
def test_requirement_auto_numbering(seeded):
    project = Project.objects.get(code="DEMO-GW")
    requirement = Requirement.objects.create(project=project, title="编号冒烟")
    assert requirement.code == "REQ-006"
    requirement.delete()
    assert Requirement.objects.count() == 5
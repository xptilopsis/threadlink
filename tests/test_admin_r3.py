"""D3-R3：PurchaseOrder / WorkOrder / ECN / ECNImpact Admin 验收测试。

前置数据由 ``load_demo_seed --flush`` 提供。先数后写（fixtures 实况）：
- ``purchase_orders``：5 条，status open=2 / received=2 / partial=1；
- ``work_orders``：1 条，status in_progress；
- ``ecn_impacts``：ECN-001=5 / ECN-002=3（总 8）。
"""

import pytest
from django.core.management import call_command

from core.models import ECN, ECNImpact, PurchaseOrder, User, WorkOrder


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


def _result_count(response):
    return response.context["cl"].queryset.count()


# --- GET 200 ---------------------------------------------------------------
def test_admin_pages_200(seeded, client):
    client.force_login(seeded)
    ecn = ECN.objects.get(ecn_number="ECN-001")
    for url in (
        "/admin/core/purchaseorder/",
        "/admin/core/workorder/",
        "/admin/core/ecn/",
        f"/admin/core/ecn/{ecn.pk}/change/",
        "/admin/core/ecnimpact/",
    ):
        assert client.get(url).status_code == 200, url


# --- Step 1：PO / WO 过滤、搜索 -------------------------------------------
def test_purchaseorder_search(seeded, client):
    client.force_login(seeded)
    response = client.get("/admin/core/purchaseorder/", {"q": "PO-001"})
    assert response.status_code == 200
    assert _result_count(response) == 1


def test_purchaseorder_filter_status_open(seeded, client):
    client.force_login(seeded)
    response = client.get("/admin/core/purchaseorder/", {"status": "open"})
    assert response.status_code == 200
    assert _result_count(response) == 2


def test_workorder_search_and_filter(seeded, client):
    client.force_login(seeded)
    response = client.get("/admin/core/workorder/", {"q": "WO-001"})
    assert response.status_code == 200
    assert _result_count(response) == 1
    response = client.get("/admin/core/workorder/", {"status": "in_progress"})
    assert response.status_code == 200
    assert _result_count(response) == 1


# --- Step 2：ECN impacts ------------------------------------------------
def test_ecn_change_page_lists_impacts(seeded, client):
    client.force_login(seeded)
    ecn = ECN.objects.get(ecn_number="ECN-001")
    html = client.get(f"/admin/core/ecn/{ecn.pk}/change/").content.decode()
    # ECN-001 的 5 条 impact（先数后写）
    for affected in ("BI-001", "LOT-DCDC-001", "PO-001", "TC-001", "TC-009"):
        assert affected in html, affected


def test_ecnimpact_search_by_ecn_number(seeded, client):
    client.force_login(seeded)
    response = client.get("/admin/core/ecnimpact/", {"q": "ECN-001"})
    assert response.status_code == 200
    assert _result_count(response) == 5


# --- 计数回归 ---------------------------------------------------------------
def test_counts_regression(seeded):
    assert PurchaseOrder.objects.count() == 5
    assert WorkOrder.objects.count() == 1
    assert ECN.objects.count() == 2
    assert ECNImpact.objects.count() == 8
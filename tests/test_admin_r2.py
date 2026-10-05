"""D3-R2：Bom 只读树视图 / BomItem / InventoryLot Admin 验收测试。

前置数据由 ``load_demo_seed --flush`` 提供。先数后写（fixtures 实况）：
- 现有 ``Bom`` = 1（`BOM-001`），``BomItem`` = 16（最大 `BI-016`）；
- ``InventoryLot`` 既有序列号含 `SN-DEMO-001`（与 `DEMO-GW` 同 project）。
"""

import pytest
from django.core.management import call_command

from core.admin import BOM_TREE_CYCLE_MARKER, BOM_TREE_INDENT_UNIT
from core.models import Bom, BomItem, Part, Project, User
from core.numbering import NumberingError


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


@pytest.fixture
def project(seeded):
    return Project.objects.get(code="DEMO-GW")


# --- GET 200 ---------------------------------------------------------------
def test_admin_pages_200(seeded, client):
    client.force_login(seeded)
    bom = Bom.objects.get(bom_no="BOM-001")
    for url in (
        "/admin/core/bom/",
        f"/admin/core/bom/{bom.pk}/change/",
        "/admin/core/bomitem/",
        "/admin/core/inventorylot/",
    ):
        assert client.get(url).status_code == 200, url


# --- Bom 树视图 ------------------------------------------------------------
def test_bom_tree_all_items_and_indent(seeded, client):
    client.force_login(seeded)
    bom = Bom.objects.get(bom_no="BOM-001")
    html = client.get(f"/admin/core/bom/{bom.pk}/change/").content.decode()

    for index in range(1, 17):
        assert f"BI-{index:03d}" in html, index
    # 父先于子：BI-001（父）先于 BI-005（子）
    assert html.index("BI-001") < html.index("BI-005")
    # 缩进标记：depth>=1 的行前置缩进单元，顶层 BI-001 不缩进
    assert BOM_TREE_INDENT_UNIT + "BI-005" in html
    assert BOM_TREE_INDENT_UNIT + "BI-001" not in html


def test_bom_tree_detects_cycle(seeded, client):
    client.force_login(seeded)
    bom = Bom.objects.get(bom_no="BOM-001")
    part = Part.objects.get(part_number="PART-001")
    first = BomItem.objects.create(bom=bom, part=part)
    second = BomItem.objects.create(bom=bom, part=part)
    first.parent_item = second
    first.save()
    second.parent_item = first
    second.save()

    response = client.get(f"/admin/core/bom/{bom.pk}/change/")
    assert response.status_code == 200
    html = response.content.decode()
    assert BOM_TREE_CYCLE_MARKER.split(" ")[0] in html  # "[CYCLE:"


# --- InventoryLot 必填 / 重复 ---------------------------------------------
def _lot_post(project, part, serial_number):
    return {
        "project": project.pk,
        "part": part.pk,
        "serial_type": "lot",
        "serial_number": serial_number,
        "quantity": "1.0000",
        "qty_available": "1.0000",
        "status": "available",
        "location": "",
        "created_at_0": "2026-10-04",
        "created_at_1": "10:00:00",
        "updated_at_0": "2026-10-04",
        "updated_at_1": "10:00:00",
    }


def test_inventorylot_serial_required(seeded, client, project):
    client.force_login(seeded)
    part = Part.objects.get(part_number="PART-001")
    response = client.post(
        "/admin/core/inventorylot/add/", _lot_post(project, part, "")
    )
    assert response.status_code == 200
    form = response.context["adminform"].form
    assert "serial_number" in form.errors


def test_inventorylot_serial_duplicate(seeded, client, project):
    client.force_login(seeded)
    part = Part.objects.get(part_number="PART-001")
    response = client.post(
        "/admin/core/inventorylot/add/", _lot_post(project, part, "SN-DEMO-001")
    )
    assert response.status_code == 200
    form = response.context["adminform"].form
    assert form.errors
    assert ("serial_number" in form.errors) or ("__all__" in form.errors)


# --- 跨 BOM 编号集成 -------------------------------------------------------
def test_cross_bom_numbering(seeded, project):
    part = Part.objects.get(part_number="PART-001")
    # 先数后写
    assert Bom.objects.count() == 1
    assert BomItem.objects.count() == 16

    second_bom = Bom.objects.create(
        project=project, name="第二 BOM", version="v9.9", created_by=seeded
    )
    assert second_bom.bom_no == "BOM-002"

    item = BomItem.objects.create(bom=second_bom, part=part)
    assert item.item_no == "BI-017"

    with pytest.raises(NumberingError):
        BomItem.objects.create(bom=second_bom, part=part, item_no="BI-001")
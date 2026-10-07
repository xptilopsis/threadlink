"""D11-R1：BOM 多级展开 + 工单齐套（GT-BOM-001…007 / GT-KIT-001…008）。

确定性、零 LLM、零 AgentRun、零写路径；期望以 ``docs/golden_tests.md`` 冻原文为准。
"""

import json
from datetime import date
from decimal import Decimal

import pytest
from django.core.management import call_command

from agents.models import AgentRun
from core.bom_expand import BomExpandError, expand_bom, expand_bom_for_work_order
from core.kitting import analyze_kitting
from core.models import (
    Bom,
    BomItem,
    BomStatus,
    InventoryLot,
    Part,
    Project,
    PurchaseOrder,
    Requirement,
    Supplier,
    User,
    WorkOrder,
)
from core.numbering import numbering_suspended
from traceability.models import TraceLink


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


@pytest.fixture
def project(seeded):
    return Project.objects.get(code="DEMO-GW")


def _mk_bom(project, user, bom_no, status=BomStatus.RELEASED):
    with numbering_suspended():
        return Bom.objects.create(
            project=project,
            bom_no=bom_no,
            name="测试BOM",
            version=f"v-{bom_no}",
            status=status,
            created_by=user,
        )


def _mk_item(bom, part, quantity, item_no, parent=None):
    with numbering_suspended():
        return BomItem.objects.create(
            bom=bom,
            item_no=item_no,
            part=part,
            quantity=Decimal(str(quantity)),
            parent_item=parent,
        )


def _mk_wo(project, user, code, bom, quantity):
    with numbering_suspended():
        return WorkOrder.objects.create(
            project=project,
            code=code,
            bom=bom,
            quantity=Decimal(str(quantity)),
            status="planned",
            created_by=user,
        )


def _mk_lot(project, part, serial, qty_available, status="available"):
    return InventoryLot.objects.create(
        project=project,
        part=part,
        serial_number=serial,
        quantity=Decimal(str(qty_available)),
        qty_available=Decimal(str(qty_available)),
        status=status,
    )


def _mk_po(project, supplier, po_number, status, expected_date):
    with numbering_suspended():
        return PurchaseOrder.objects.create(
            project=project,
            po_number=po_number,
            supplier=supplier,
            status=status,
            expected_date=expected_date,
        )


def _mk_ordered(project, part_number, po_number, quantity):
    TraceLink.objects.create(
        project=project,
        from_type="part",
        from_id=part_number,
        to_type="purchase_order",
        to_id=po_number,
        relation_type="ordered_by",
        metadata={"quantity": quantity},
    )


def _get_bom(project):
    return Bom.objects.get(project=project, bom_no="BOM-001")


def _get_part(project, number):
    return Part.objects.get(project=project, part_number=number)


# --- GT-BOM-001…007 ---------------------------------------------------------
def test_gt_bom_001_top_level(seeded, project):
    result = expand_bom(_get_bom(project), quantity=1)
    assert len(result["lines"]) == 4
    assert all(line["depth"] == 0 for line in result["lines"])
    items = {line["item_no"]: line for line in result["lines"]}
    assert set(items) == {"BI-001", "BI-002", "BI-003", "BI-004"}
    assert items["BI-004"]["required_qty"] == Decimal("2")


def test_gt_bom_002_leaf(seeded, project):
    result = expand_bom(_get_bom(project), quantity=1, include_hierarchy=True)
    lines = {line["item_no"]: line for line in result["lines"]}
    assert lines["BI-005"]["depth"] == 1
    assert lines["BI-005"]["parent_item_no"] == "BI-001"
    assert lines["BI-005"]["required_qty"] == Decimal("4")
    assert lines["BI-006"]["required_qty"] == Decimal("10")
    assert lines["BI-009"]["required_qty"] == Decimal("2")
    assert lines["BI-010"]["required_qty"] == Decimal("2")
    assert not any(line["parent_item_no"] == "BI-005" for line in result["lines"])
    order = [line["item_no"] for line in result["lines"]]
    assert order.index("BI-001") < order.index("BI-005")


def test_gt_bom_003_work_order_scale(seeded, project):
    wo = WorkOrder.objects.get(project=project, code="WO-001")
    totals = {t["part_number"]: t["required_qty"] for t in expand_bom_for_work_order(wo)["totals"]}
    assert totals["PART-006"] == Decimal("20")
    assert totals["PART-010"] == Decimal("120")
    assert totals["PART-001"] == Decimal("10")


def test_gt_bom_004_multi_path_totals(seeded, project):
    part = _get_part(project, "PART-003")
    bom = _mk_bom(project, seeded, "BOM-T-MULTI")
    _mk_item(bom, part, 3, "BI-T-M1")
    _mk_item(bom, part, 5, "BI-T-M2")
    result = expand_bom(bom, quantity=1)
    assert len(result["lines"]) == 2
    totals = {t["part_number"]: t["required_qty"] for t in result["totals"]}
    assert totals["PART-003"] == Decimal("8")


def test_gt_bom_005_status(seeded, project):
    obsolete = _mk_bom(project, seeded, "BOM-T-OBS", status=BomStatus.OBSOLETE)
    with pytest.raises(BomExpandError) as exc:
        expand_bom(obsolete)
    assert exc.value.code == "bom_not_releasable"

    draft = _mk_bom(project, seeded, "BOM-T-DRAFT", status=BomStatus.DRAFT)
    assert "draft_bom" in expand_bom(draft)["warnings"]


def test_gt_bom_006_discontinued_flag(seeded, project):
    part = _get_part(project, "PART-017")  # obsolete
    bom = _mk_bom(project, seeded, "BOM-T-OBS2")
    _mk_item(bom, part, 1, "BI-T-OBS")
    line = expand_bom(bom, quantity=1)["lines"][0]
    assert line["lifecycle_status"] == "obsolete"
    assert "discontinued" in line["risk_flags"]


def test_gt_bom_007_three_levels(seeded, project):
    result = expand_bom(_get_bom(project), quantity=1, include_hierarchy=True)
    lines = {line["item_no"]: line for line in result["lines"]}
    assert lines["BI-016"]["depth"] == 2
    assert lines["BI-016"]["required_qty"] == Decimal("20")
    assert lines["BI-016"]["parent_item_no"] == "BI-006"
    order = [line["item_no"] for line in result["lines"]]
    assert order.index("BI-006") < order.index("BI-016")


# --- BOM 边界 ---------------------------------------------------------------
def test_bom_empty(seeded, project):
    bom = _mk_bom(project, seeded, "BOM-T-EMPTY")
    assert expand_bom(bom)["lines"] == []


def test_bom_cycle_detected(seeded, project):
    part = _get_part(project, "PART-003")
    bom = _mk_bom(project, seeded, "BOM-T-CYC")
    a = _mk_item(bom, part, 1, "BI-T-C1")
    b = _mk_item(bom, part, 1, "BI-T-C2", parent=a)
    with numbering_suspended():
        a.parent_item = b
        a.save(update_fields=["parent_item"])
    with pytest.raises(BomExpandError) as exc:
        expand_bom(bom)
    assert exc.value.code == "cyclic_bom_structure"


def test_bom_decimal_quantity_no_drift(seeded, project):
    part = _get_part(project, "PART-003")
    bom = _mk_bom(project, seeded, "BOM-T-Q")
    _mk_item(bom, part, "0.5", "BI-T-Q")
    result = expand_bom(bom, quantity=Decimal("0.5"))
    assert result["lines"][0]["required_qty"] == Decimal("0.2500")
    assert expand_bom(bom, quantity=Decimal("0"))["lines"][0]["required_qty"] == Decimal("0")


# --- GT-KIT-001…008 ---------------------------------------------------------
def test_gt_kit_001_ready(seeded, project):
    part = _get_part(project, "PART-003")
    bom = _mk_bom(project, seeded, "BOM-K1")
    _mk_item(bom, part, 1, "BI-K1")
    wo = _mk_wo(project, seeded, "WO-K1", bom, 10)
    _mk_lot(project, part, "LOT-K1", 10)
    result = analyze_kitting(wo)
    assert result["shortages"] == []
    assert result["ready"] is True


def test_gt_kit_002_partial_occupancy(seeded, project):
    part = _get_part(project, "PART-001")
    bom = _mk_bom(project, seeded, "BOM-K2")
    _mk_item(bom, part, 1, "BI-K2")
    wo = _mk_wo(project, seeded, "WO-K2", bom, 90)  # 需求 90；LOT-DCDC-001 可用 80
    shortage = analyze_kitting(wo)["shortages"][0]
    assert shortage["part_id"] == "PART-001"
    assert shortage["available_qty"] == Decimal("80")
    assert shortage["shortage_qty"] == Decimal("10")


def test_gt_kit_002_allocated_excluded(seeded, project):
    part = _get_part(project, "PART-002")  # fixture 仅 SN-DEMO-001（allocated）
    bom = _mk_bom(project, seeded, "BOM-K2b")
    _mk_item(bom, part, 1, "BI-K2b")
    wo = _mk_wo(project, seeded, "WO-K2b", bom, 1)
    shortage = analyze_kitting(wo)["shortages"][0]
    assert shortage["available_qty"] == Decimal("0")


def test_gt_kit_003_transit_arrival(seeded, project):
    part = _get_part(project, "PART-003")
    bom = _mk_bom(project, seeded, "BOM-K3")
    _mk_item(bom, part, 1, "BI-K3")
    wo = _mk_wo(project, seeded, "WO-K3", bom, 30)
    supplier = Supplier.objects.filter(project=project).first()
    _mk_po(project, supplier, "PO-K3A", "open", date(2026, 3, 1))
    _mk_ordered(project, "PART-003", "PO-K3A", 20)
    _mk_po(project, supplier, "PO-K3B", "open", date(2026, 3, 20))
    _mk_ordered(project, "PART-003", "PO-K3B", 50)
    shortage = analyze_kitting(wo)["shortages"][0]
    assert shortage["in_transit_qty"] == Decimal("70")
    assert shortage["latest_arrival_date"] == date(2026, 3, 20)
    assert shortage["insufficient"] is False


def test_gt_kit_003_transit_insufficient(seeded, project):
    part = _get_part(project, "PART-003")
    bom = _mk_bom(project, seeded, "BOM-K3c")
    _mk_item(bom, part, 1, "BI-K3c")
    wo = _mk_wo(project, seeded, "WO-K3c", bom, 30)
    supplier = Supplier.objects.filter(project=project).first()
    _mk_po(project, supplier, "PO-K3C", "open", date(2026, 3, 1))
    _mk_ordered(project, "PART-003", "PO-K3C", 20)  # 20 < 30
    shortage = analyze_kitting(wo)["shortages"][0]
    assert shortage["latest_arrival_date"] == date(2026, 3, 1)
    assert shortage["insufficient"] is True


def test_gt_kit_004_alternatives(seeded, project):
    InventoryLot.objects.filter(serial_number="LOT-DCDC-001").update(qty_available=Decimal("0"))
    part1 = _get_part(project, "PART-001")
    part2 = _get_part(project, "PART-002")
    _mk_lot(project, part2, "LOT-K4ALT", 1)  # PART-002 可用 1（fixture 在途 PO-002 = 50）
    bom = _mk_bom(project, seeded, "BOM-K4")
    _mk_item(bom, part1, 1, "BI-K4")
    wo = _mk_wo(project, seeded, "WO-K4", bom, 9)
    shortage = analyze_kitting(wo)["shortages"][0]
    assert shortage["shortage_qty"] == Decimal("9")
    alternative = shortage["alternatives"][0]
    assert alternative["part_id"] == "PART-002"
    assert alternative["available_qty"] == Decimal("1")
    assert alternative["in_transit_qty"] == Decimal("50")
    assert alternative["shortest_arrival_date"] == date(2026, 3, 20)
    assert alternative["sufficient"] is True


def test_gt_kit_005_discontinued_shortage(seeded, project):
    part = _get_part(project, "PART-017")
    bom = _mk_bom(project, seeded, "BOM-K5")
    _mk_item(bom, part, 1, "BI-K5")
    wo = _mk_wo(project, seeded, "WO-K5", bom, 10)
    shortage = analyze_kitting(wo)["shortages"][0]
    assert shortage["required_qty"] == Decimal("10")
    assert shortage["available_qty"] == Decimal("0")
    assert "discontinued" in shortage["risk_flags"]


def test_gt_kit_006_long_lead_time(seeded, project):
    part = _get_part(project, "PART-018")  # SUP-003 lead_time_days=90
    bom = _mk_bom(project, seeded, "BOM-K6")
    _mk_item(bom, part, 1, "BI-K6")
    wo = _mk_wo(project, seeded, "WO-K6", bom, 1)
    shortage = analyze_kitting(wo)["shortages"][0]
    assert "long_lead_time" in shortage["risk_flags"]


def test_gt_kit_007_full_fields_and_critical(seeded, project):
    InventoryLot.objects.filter(serial_number="LOT-DCDC-001").update(qty_available=Decimal("0"))
    part = _get_part(project, "PART-001")  # is_critical = True
    bom = _mk_bom(project, seeded, "BOM-K7")
    _mk_item(bom, part, 1, "BI-K7")
    wo = _mk_wo(project, seeded, "WO-K7", bom, 10)
    shortage = analyze_kitting(wo)["shortages"][0]
    for field in (
        "part_id",
        "required_qty",
        "available_qty",
        "shortage_qty",
        "in_transit_qty",
        "latest_arrival_date",
        "insufficient",
        "alternatives",
        "risk_flags",
    ):
        assert field in shortage
    assert "critical_shortage" in shortage["risk_flags"]


def test_gt_kit_008_hard_shortage(seeded, project):
    part = _get_part(project, "PART-019")  # 无库存、无在途、无替代
    bom = _mk_bom(project, seeded, "BOM-K8")
    _mk_item(bom, part, 1, "BI-K8")
    wo = _mk_wo(project, seeded, "WO-K8", bom, 10)
    shortage = analyze_kitting(wo)["shortages"][0]
    assert shortage["latest_arrival_date"] is None
    assert shortage["alternatives"] == []
    assert shortage["insufficient"] is True


def test_gt_kit_008_zero_transit_equiv_none(seeded, project):
    part = _get_part(project, "PART-019")
    bom = _mk_bom(project, seeded, "BOM-K8b")
    _mk_item(bom, part, 1, "BI-K8b")
    wo = _mk_wo(project, seeded, "WO-K8b", bom, 10)
    supplier = Supplier.objects.filter(project=project).first()
    _mk_po(project, supplier, "PO-K8Z", "open", date(2026, 3, 1))
    _mk_ordered(project, "PART-019", "PO-K8Z", 0)  # 总量 0 → 等价无在途
    shortage = analyze_kitting(wo)["shortages"][0]
    assert shortage["in_transit_qty"] == Decimal("0")
    assert shortage["latest_arrival_date"] is None
    assert shortage["insufficient"] is True


def test_gt_kit_transit_status_filtered(seeded, project):
    part = _get_part(project, "PART-019")
    bom = _mk_bom(project, seeded, "BOM-K3f")
    _mk_item(bom, part, 1, "BI-K3f")
    wo = _mk_wo(project, seeded, "WO-K3f", bom, 10)
    supplier = Supplier.objects.filter(project=project).first()
    _mk_po(project, supplier, "PO-K3F", "received", date(2026, 3, 1))
    _mk_ordered(project, "PART-019", "PO-K3F", 100)  # received → 不计入在途
    shortage = analyze_kitting(wo)["shortages"][0]
    assert shortage["in_transit_qty"] == Decimal("0")
    assert shortage["latest_arrival_date"] is None


# --- 确定性 + 只读 ----------------------------------------------------------
def _dump(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def test_deterministic(seeded, project):
    bom = _get_bom(project)
    wo = WorkOrder.objects.get(project=project, code="WO-001")
    assert _dump(expand_bom(bom, include_hierarchy=True)) == _dump(
        expand_bom(bom, include_hierarchy=True)
    )
    assert _dump(analyze_kitting(wo)) == _dump(analyze_kitting(wo))


def test_read_only_no_writes(seeded, project):
    bom = _get_bom(project)
    wo = WorkOrder.objects.get(project=project, code="WO-001")

    def counts():
        return (
            Bom.objects.count(),
            BomItem.objects.count(),
            TraceLink.objects.count(),
            AgentRun.objects.count(),
            InventoryLot.objects.count(),
            PurchaseOrder.objects.count(),
            WorkOrder.objects.count(),
            Requirement.objects.count(),
        )

    before = counts()
    expand_bom(bom, include_hierarchy=True)
    analyze_kitting(wo)
    assert counts() == before


# --- 命令冒烟 ---------------------------------------------------------------
def test_commands_smoke(seeded, project, capsys):
    call_command("bom_expand", "BOM-001", "--hierarchy", "--qty", "1")
    out = capsys.readouterr().out
    assert "BI-001" in out and "PART-001" in out and "totals" in out

    call_command("kitting_check", "WO-001")
    out2 = capsys.readouterr().out
    assert "WO-001" in out2 and "齐套" in out2

# --- D11-R2 Step 0：ordered_by.metadata.quantity 承重接口锁定 -----------------
def test_kitting_absent_quantity_is_zero(seeded, project):
    part = _get_part(project, "PART-019")
    bom = _mk_bom(project, seeded, "BOM-K9")
    _mk_item(bom, part, 1, "BI-K9")
    wo = _mk_wo(project, seeded, "WO-K9", bom, 10)
    supplier = Supplier.objects.filter(project=project).first()
    _mk_po(project, supplier, "PO-K9", "open", date(2026, 3, 1))
    # absent quantity（无 metadata）→ 0，等价无在途
    TraceLink.objects.create(
        project=project,
        from_type="part",
        from_id="PART-019",
        to_type="purchase_order",
        to_id="PO-K9",
        relation_type="ordered_by",
    )
    shortage = analyze_kitting(wo)["shortages"][0]
    assert shortage["in_transit_qty"] == Decimal("0")
    assert shortage["latest_arrival_date"] is None
    assert shortage["insufficient"] is True


def test_kitting_non_numeric_quantity_fail_loud(seeded, project):
    from decimal import InvalidOperation

    part = _get_part(project, "PART-019")
    bom = _mk_bom(project, seeded, "BOM-K9b")
    _mk_item(bom, part, 1, "BI-K9b")
    wo = _mk_wo(project, seeded, "WO-K9b", bom, 10)
    supplier = Supplier.objects.filter(project=project).first()
    _mk_po(project, supplier, "PO-K9X", "open", date(2026, 3, 1))
    TraceLink.objects.create(
        project=project,
        from_type="part",
        from_id="PART-019",
        to_type="purchase_order",
        to_id="PO-K9X",
        relation_type="ordered_by",
        metadata={"quantity": "abc"},
    )
    with pytest.raises(InvalidOperation):  # 非数值 → fail-loud（数据完整性信号）
        analyze_kitting(wo)


# --- D11-R2 Step 0.3：WorkOrderAdmin 只读面板证据 ---------------------------
def test_workorder_admin_kitting_panel_ok(seeded, project, client):
    wo = WorkOrder.objects.get(project=project, code="WO-001")
    client.force_login(seeded)
    resp = client.get(f"/admin/core/workorder/{wo.pk}/change/")
    assert resp.status_code == 200
    assert "齐套摘要" in resp.content.decode()


def test_workorder_admin_panel_error_not_500(seeded, project, client, monkeypatch):
    import core.kitting as kitting

    def boom(_work_order):  # noqa: ANN001
        raise RuntimeError("boom")

    monkeypatch.setattr(kitting, "analyze_kitting", boom)
    wo = WorkOrder.objects.get(project=project, code="WO-001")
    client.force_login(seeded)
    resp = client.get(f"/admin/core/workorder/{wo.pk}/change/")
    assert resp.status_code == 200
    assert "计算失败" in resp.content.decode()
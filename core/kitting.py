"""D11-R1：工单齐套 / 缺料（确定性、零 LLM、只读）。

口径唯一依据 = ``docs/golden_tests.md`` §2.2（GT-KIT-001…008）：

- 需求量 = §2.1 展开用量（``expand_bom_for_work_order``，全层级 × ``WorkOrder.quantity``）。
- 可用量 = ``Σ InventoryLot.qty_available``，过滤 ``part_id`` 匹配 + ``status == "available"``
  （``allocated`` / ``consumed`` / ``scrapped`` 不计入）。
- 在途量 = ``Σ`` 在途批次量；批次来源 = ``TraceLink(from=Part, relation_type="ordered_by",
  to=PurchaseOrder)``，数量取 ``TraceLink.metadata["quantity"]``，过滤 ``PO.status ∈ {open, partial}``
  （``PurchaseOrder`` 模型**无**明细/``metadata`` 字段，量存于该边 ``metadata``）。
- 判定：``可用量 ≥ 需求量`` → 齐套；否则 ``shortage_qty = 需求量 − 可用量``。
- 缺料行字段：``part_id`` / ``required_qty`` / ``available_qty`` / ``shortage_qty`` / ``in_transit_qty`` /
  ``latest_arrival_date`` / ``insufficient`` / ``alternatives`` / ``risk_flags``。
- **最晚到货日**：按 ``expected_date`` 升序累加在途量，取使累计 ``≥ shortage_qty`` 的批次日；全部不足 →
  取最后批次日并置 ``insufficient = true``；无在途 → ``latest_arrival_date = null``、``insufficient = true``。
- **替代可行项**：``TraceLink(from=替代料 Part, relation_type="replaces", to=被替代料 Part)``，仅
  ``lifecycle_status == "active"`` 的替代料；``available + in_transit ≥ shortage_qty`` → ``sufficient = true``。
- **风险标记**：``lifecycle_status ∈ {eol, obsolete, discontinued}`` → ``discontinued``；供应商
  ``lead_time_days > 60`` → ``long_lead_time``；``Part.is_critical`` 且缺料 → ``critical_shortage``。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from core.bom_expand import expand_bom_for_work_order
from core.models import (
    InventoryLot,
    InventoryLotStatus,
    Part,
    PurchaseOrder,
    PurchaseOrderStatus,
    SupplierPart,
    WorkOrder,
)
from schemas.agent_outputs import TraceRelationType
from traceability.models import TraceLink

_QTY_EXP = Decimal("0.0001")
AVAILABLE_STATUS = InventoryLotStatus.AVAILABLE.value
IN_TRANSIT_PO_STATUSES = {
    PurchaseOrderStatus.OPEN.value,
    PurchaseOrderStatus.PARTIAL.value,
}
LONG_LEAD_THRESHOLD_DAYS = 60
DISCONTINUED_LIFECYCLES = {"eol", "obsolete", "discontinued"}
REPLACES = TraceRelationType.REPLACES.value
ORDERED_BY = TraceRelationType.ORDERED_BY.value


def _available_qty(project, part_number: str) -> Decimal:
    lots = InventoryLot.objects.filter(
        project=project,
        part__part_number=part_number,
        status=AVAILABLE_STATUS,
    )
    total = Decimal("0")
    for lot in lots:
        total += lot.qty_available
    return total


def _in_transit_batches(project, part_number: str) -> list[dict]:
    """在途批次：``Part -ordered_by-> PO`` 边的 ``metadata.quantity``（``open``/``partial``）。"""

    batches: list[dict] = []
    links = TraceLink.objects.filter(
        project=project,
        from_type="part",
        from_id=part_number,
        relation_type=ORDERED_BY,
        to_type="purchase_order",
    )
    for link in links:
        po = PurchaseOrder.objects.filter(project=project, po_number=link.to_id).first()
        if po is None or po.status not in IN_TRANSIT_PO_STATUSES:
            continue
        quantity = Decimal(str((link.metadata or {}).get("quantity", 0)))
        if quantity <= 0:  # GT-KIT-008 边界：在途总量 0 等价无在途
            continue
        batches.append(
            {"po_number": po.po_number, "expected_date": po.expected_date, "quantity": quantity}
        )
    return batches


def _sorted_batches(batches: list[dict]) -> list[dict]:
    return sorted(
        batches,
        key=lambda b: (b["expected_date"] is None, b["expected_date"] or date.max),
    )


def _latest_arrival(batches: list[dict], shortage: Decimal) -> tuple[date | None, bool]:
    """返回 ``(latest_arrival_date, insufficient)``。"""

    if shortage <= 0:
        return None, False
    ordered = _sorted_batches(batches)
    if not ordered:
        return None, True
    cumulative = Decimal("0")
    for batch in ordered:
        cumulative += batch["quantity"]
        if cumulative >= shortage:
            return batch["expected_date"], False
    return ordered[-1]["expected_date"], True


def _has_long_lead(project, part_number: str) -> bool:
    return SupplierPart.objects.filter(
        part__project=project,
        part__part_number=part_number,
        lead_time_days__gt=LONG_LEAD_THRESHOLD_DAYS,
    ).exists()


def _alternatives(project, part_number: str, shortage: Decimal) -> list[dict]:
    options: list[dict] = []
    links = TraceLink.objects.filter(
        project=project,
        to_type="part",
        to_id=part_number,
        relation_type=REPLACES,
    )
    for link in links:
        alt = Part.objects.filter(project=project, part_number=link.from_id).first()
        if alt is None or alt.lifecycle_status != "active":
            continue  # GT-KIT-004 边界 2：仅 active 替代料
        alt_available = _available_qty(project, alt.part_number)
        alt_batches = _in_transit_batches(project, alt.part_number)
        alt_transit = sum((b["quantity"] for b in alt_batches), Decimal("0"))
        remaining = shortage - alt_available
        arrival, _ = _latest_arrival(alt_batches, remaining if remaining > 0 else Decimal("0"))
        options.append(
            {
                "part_id": alt.part_number,
                "available_qty": alt_available.quantize(_QTY_EXP),
                "in_transit_qty": alt_transit.quantize(_QTY_EXP),
                "shortest_arrival_date": arrival,
                "sufficient": (alt_available + alt_transit) >= shortage,
            }
        )
    return options


def analyze_kitting(work_order: WorkOrder) -> dict:
    """分析工单齐套（只读、确定性）。"""

    project = work_order.project
    expansion = expand_bom_for_work_order(work_order)

    shortages = []
    for row in expansion["totals"]:
        part_number = row["part_number"]
        required = row["required_qty"]
        available = _available_qty(project, part_number)
        if available >= required:
            continue  # GT-KIT-001（含 available == required 边界）
        shortage = required - available
        part = Part.objects.filter(project=project, part_number=part_number).first()

        batches = _in_transit_batches(project, part_number)
        in_transit = sum((b["quantity"] for b in batches), Decimal("0"))
        arrival, insufficient = _latest_arrival(batches, shortage)

        risk_flags: list[str] = []
        if part is not None and part.lifecycle_status in DISCONTINUED_LIFECYCLES:
            risk_flags.append("discontinued")
        if part is not None and part.is_critical:
            risk_flags.append("critical_shortage")
        if _has_long_lead(project, part_number):
            risk_flags.append("long_lead_time")

        shortages.append(
            {
                "part_id": part_number,
                "required_qty": required.quantize(_QTY_EXP),
                "available_qty": available.quantize(_QTY_EXP),
                "shortage_qty": shortage.quantize(_QTY_EXP),
                "in_transit_qty": in_transit.quantize(_QTY_EXP),
                "latest_arrival_date": arrival,
                "insufficient": insufficient,
                "alternatives": _alternatives(project, part_number, shortage),
                "risk_flags": risk_flags,
            }
        )

    return {
        "work_order": work_order.code,
        "bom_no": work_order.bom.bom_no,
        "quantity": work_order.quantity,
        "ready": not shortages,
        "required": expansion["totals"],
        "shortages": shortages,
    }


# 指令 §2.1 命名别名（GT §5.2 用 analyze_kitting；二者同一实现）
check_kitting = analyze_kitting
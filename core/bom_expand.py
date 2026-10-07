"""D11-R1：BOM 多级展开（确定性、零 LLM、零写路径）。

口径唯一依据 = ``docs/golden_tests.md`` §2.1（GT-BOM-001…007）：

- ``BomItem`` 以 ``parent_item_id`` 自引用成森林；``parent_item_id IS NULL`` 为顶层节点。
- 单节点**累计用量** = 根到该节点路径各 ``quantity`` 的乘积；工单场景再乘 ``WorkOrder.quantity``。
- 同一 ``part_id`` 经多路径出现时，明细各保留一行、``totals`` **汇总求和**。
- 输出顺序：``depth`` 升序；同层按 ``position``、``ref_des``、``item_no`` 稳定排序。
- 仅展开 ``Bom.status ∈ {released, draft}``；``obsolete`` **拒绝展开**（抛 ``bom_not_releasable``）；
  ``draft`` 展开附 ``warning = "draft_bom"``。
- 环形引用（父链重复 ``BomItem.id``）→ 抛 ``cyclic_bom_structure``，不返回部分结果。
- 孤儿节点（``part_id`` 指向不存在的 ``Part``）→ 抛 ``orphan_bom_item``。
- GT-BOM-001（``include_hierarchy=False``）返回**顶层行**；GT-BOM-002/007（``include_hierarchy=True``）
  返回**全部层级**；GT-BOM-003 经 ``expand_bom_for_work_order`` 全层级 × 工单数量。
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from core.models import Bom, BomItem, BomStatus, Part, WorkOrder

CYCLE_CODE = "cyclic_bom_structure"
ORPHAN_CODE = "orphan_bom_item"
NOT_RELEASABLE_CODE = "bom_not_releasable"
DRAFT_WARNING = "draft_bom"
_QTY_EXP = Decimal("0.0001")

# GT §2.2 停产口径：Part.lifecycle_status ∈ {eol, obsolete}（GT-BOM-008 边界亦含字面 discontinued）
DISCONTINUED_LIFECYCLES = {"eol", "obsolete", "discontinued"}


class BomExpandError(Exception):
    """BOM 展开错误（``code`` 为 GT 机器 token）。"""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


def _as_decimal(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _risk_flags(lifecycle_status: str) -> list[str]:
    flags: list[str] = []
    if lifecycle_status in DISCONTINUED_LIFECYCLES:
        flags.append("discontinued")
    elif lifecycle_status == "nrnd":
        flags.append("nrnd")
    return flags


def _check_cycles(items: list[BomItem]) -> None:
    by_id = {item.id: item for item in items}
    for item in items:
        seen: set[int] = set()
        cursor: BomItem | None = item
        while cursor is not None:
            if cursor.id in seen:
                raise BomExpandError(
                    CYCLE_CODE, f"检测到环：BomItem {cursor.item_no}"
                )
            seen.add(cursor.id)
            cursor = by_id.get(cursor.parent_item_id)


def _check_orphans(items: list[BomItem]) -> None:
    part_ids = {item.part_id for item in items}
    existing = set(
        Part.objects.filter(pk__in=part_ids).values_list("pk", flat=True)
    )
    for item in items:
        if item.part_id not in existing:
            raise BomExpandError(
                ORPHAN_CODE, f"BomItem {item.item_no} 指向不存在的 Part"
            )


def expand_bom(bom: Bom, quantity=Decimal("1"), include_hierarchy: bool = False) -> dict:
    """展开 ``bom`` 为结构化明细（只读）。

    - ``quantity``：展开基数（默认 1；工单场景传 ``WorkOrder.quantity``）。
    - ``include_hierarchy``：``False`` 仅顶层行（GT-BOM-001）；``True`` 全层级（GT-BOM-002/007）。
    """

    factor_root = _as_decimal(quantity)
    warnings: list[str] = []

    if bom.status == BomStatus.OBSOLETE:
        raise BomExpandError(
            NOT_RELEASABLE_CODE, f"BOM {bom.bom_no} status=obsolete 不可展开"
        )
    if bom.status == BomStatus.DRAFT:
        warnings.append(DRAFT_WARNING)

    items = list(BomItem.objects.filter(bom=bom).select_related("part").order_by("id"))
    _check_cycles(items)
    _check_orphans(items)
    by_id = {item.id: item for item in items}
    by_parent: dict[int | None, list[BomItem]] = defaultdict(list)
    for item in items:
        by_parent[item.parent_item_id].append(item)

    collected: list[tuple[int, BomItem, Decimal]] = []

    def visit(parent_id: int | None, depth: int, factor: Decimal) -> None:
        for item in by_parent.get(parent_id, []):
            cumulative = (factor * item.quantity).quantize(_QTY_EXP)
            collected.append((depth, item, cumulative))
            if include_hierarchy:
                visit(item.id, depth + 1, cumulative)

    visit(None, 0, factor_root)
    collected.sort(key=lambda row: (row[0], row[1].position or "", row[1].ref_des or "", row[1].item_no))

    lines = []
    for depth, item, cumulative in collected:
        part = item.part
        parent_item_no = by_id[item.parent_item_id].item_no if item.parent_item_id else None
        lines.append(
            {
                "item_no": item.item_no,
                "part_number": part.part_number,
                "required_qty": cumulative,
                "depth": depth,
                "parent_item_no": parent_item_no,
                "ref_des": item.ref_des,
                "position": item.position,
                "substitute_group": item.substitute_group or None,
                "is_critical": part.is_critical,
                "lifecycle_status": part.lifecycle_status,
                "risk_flags": _risk_flags(part.lifecycle_status),
                "warnings": [],
            }
        )

    totals_map: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for line in lines:
        totals_map[line["part_number"]] += line["required_qty"]
    totals = [
        {"part_number": part_number, "required_qty": total}
        for part_number, total in sorted(totals_map.items())
    ]

    return {
        "bom_no": bom.bom_no,
        "bom_status": bom.status,
        "input_quantity": factor_root,
        "include_hierarchy": include_hierarchy,
        "warnings": warnings,
        "lines": lines,
        "totals": totals,
    }


def expand_bom_for_work_order(work_order: WorkOrder) -> dict:
    """按工单展开：全层级 × ``WorkOrder.quantity``（GT-BOM-003）。"""

    return expand_bom(
        work_order.bom,
        quantity=work_order.quantity,
        include_hierarchy=True,
    )
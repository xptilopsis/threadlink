"""D11-R2：ECN 影响投影（**全零写**）+ 正式应用（唯一写路径）。

**P3-A 定稿（用户裁决）**：影响面 = ``ECNImpact`` 行**权威**；`docs/golden_tests.md` §2.3 的
「由 TraceLink/BOM 图计算」规则**不采用**（其 ``test_case`` 口径无法复现 GT-ECN-001 的
``TC-009``——`TC-009` 仅存在于 ``ECNImpact`` 行）。冲突与证据见 ADR-0015。

时序（§1 证据 + GT-ECN-005 冻原文）：

- **分析** `project_ecn_impact`：读 ``ECNImpact`` → `resolve_entity` 解析 → 分类清单 +
  ``unresolved``（fail-soft）+ ``consistency``（缺 ``affects`` 边提示）；**全零写**（不写 EI、不写边）。
- **应用** `apply_ecn`（人工动作，唯一写路径）：
  a) 每个 ``ECNImpact`` 行**确保** ``ECN→目标`` ``affects`` 边：缺 → 建（``source="agent"`` 对齐
     fixtures、``created_by``/``confirmed_by``=操作人、``confirmed_at``=now）；存在未确认 → 补确认；
     已确认 → 不动。
  b) 写回（**P1-A**）：受影响 ``bom_item`` 的 ``part ← 该 part 的 ``replaces`` 目标``；无目标 → 不写回；
     多目标 → fail-loud；非 ``bom_item`` 类不写实体。
  c) ``ECN.status`` **不迁移**（GT 未定义；最小决策，见 ADR-0015）。
- 前置门：状态门（GT-ECN-003）+ 日期门（GT-ECN-004，``missing_effective_date`` warning 照原文）。
"""

from __future__ import annotations

from datetime import date

from django.db import transaction
from django.utils import timezone

from core.models import BomItem, ECN, ECNImpact, Part
from schemas.agent_outputs import LinkSource, TraceRelationType
from traceability.models import TraceLink
from traceability.services import TraceReferenceError, resolve_entity

EFFECTIVE_STATUSES = {"approved", "implemented"}
AFFECTS = TraceRelationType.AFFECTS.value
REPLACES = TraceRelationType.REPLACES.value
AGENT_SOURCE = LinkSource.AGENT.value

# 分类键 → EntityType 值
CATEGORY_BY_TYPE = {
    "bom_item": "bom_nodes",
    "inventory_lot": "inventory_lots",
    "purchase_order": "purchase_orders",
    "test_case": "test_cases",
}


class EcnApplyError(Exception):
    """应用前置门 / 数据完整性错误（fail-loud）。"""


def _effectiveness(ecn: ECN, as_of_date: date) -> tuple[bool, str | None]:
    """GT-ECN-003 状态门 + GT-ECN-004 日期门。返回 ``(effective, warning)``。"""

    if ecn.status not in EFFECTIVE_STATUSES:
        return False, "status_not_effective"
    if ecn.effective_date is None:
        return False, "missing_effective_date"  # GT-ECN-004
    if ecn.effective_date > as_of_date:
        return False, "not_yet_effective"
    return True, None


def _resolve_display(project, affected_type: str, affected_id: str):
    try:
        obj = resolve_entity(project.pk, affected_type, affected_id)
    except TraceReferenceError:
        return None
    return {
        "affected_type": affected_type,
        "affected_id": affected_id,
        "label": str(obj),
    }


def project_ecn_impact(ecn: ECN, as_of_date: date | None = None) -> dict:
    """投影 ECN 影响面（**全零写**）。

    返回：``{ecn, status, effective_date, as_of_date, effective, warnings, impacts, unresolved, consistency}``；
    ``impacts`` 按类别（``bom_nodes`` / ``inventory_lots`` / ``purchase_orders`` / ``test_cases``）。
    """

    project = ecn.project
    as_of = as_of_date or date.today()
    effective, warning = _effectiveness(ecn, as_of)
    warnings = [warning] if warning else []

    impacts = {"bom_nodes": [], "inventory_lots": [], "purchase_orders": [], "test_cases": []}
    unresolved: list[dict] = []
    consistency: list[str] = []

    for ei in ECNImpact.objects.filter(ecn=ecn).order_by("id"):
        display = _resolve_display(project, ei.affected_type, ei.affected_id)
        if display is None:
            unresolved.append(
                {"affected_type": ei.affected_type, "affected_id": ei.affected_id}
            )
            continue
        display["impact_type"] = ei.impact_type
        bucket = CATEGORY_BY_TYPE.get(ei.affected_type)
        if bucket is not None:
            impacts[bucket].append(display)
        exists = TraceLink.objects.filter(
            project=project,
            from_type="ecn",
            from_id=ecn.ecn_number,
            relation_type=AFFECTS,
            to_type=ei.affected_type,
            to_id=ei.affected_id,
        ).exists()
        if not exists:
            consistency.append(f"missing_affects_edge:{ei.affected_type}:{ei.affected_id}")

    return {
        "ecn": ecn.ecn_number,
        "status": ecn.status,
        "effective_date": ecn.effective_date.isoformat() if ecn.effective_date else None,
        "as_of_date": as_of.isoformat(),
        "effective": effective,
        "warnings": warnings,
        "impacts": impacts,
        "unresolved": unresolved,
        "consistency": consistency,
    }


def _replacement_part(project, part: Part) -> Part | None:
    """P1-A：``part`` 的 ``replaces`` 替代料（``替代料 -replaces-> 被替代料``）。多目标 → fail-loud。"""

    links = list(
        TraceLink.objects.filter(
            project=project,
            to_type="part",
            to_id=part.part_number,
            relation_type=REPLACES,
        ).order_by("pk")
    )
    if not links:
        return None
    if len(links) > 1:
        raise EcnApplyError(f"多替换目标：{part.part_number} 有 {len(links)} 个 replaces 来源")
    return Part.objects.filter(project=project, part_number=links[0].from_id).first()


def apply_ecn(ecn: ECN, user, as_of_date: date | None = None) -> dict:
    """正式应用 ECN（唯一写路径；事务内，失败整体回滚）。

    - 前置门：状态门（GT-ECN-003）+ 日期门（GT-ECN-004）不符 → ``EcnApplyError``。
    - a) 确保 ``affects`` 边（缺→建、未确认→补确认、已确认→不动）；
    - b) 写回受影响 ``bom_item`` 的 ``part ← replaces`` 目标；
    - c) 不改 ``ECN.status``（最小决策）。
    - 幂等：二次应用为 no-op（边已确认、`part` 已替换）。
    """

    if user is None:
        raise EcnApplyError("apply_ecn 需显式操作人（人工动作）")

    as_of = as_of_date or date.today()
    effective, warning = _effectiveness(ecn, as_of)
    if not effective:
        raise EcnApplyError(f"ECN {ecn.ecn_number} 不可应用：{warning}")

    project = ecn.project
    impacts = list(ECNImpact.objects.filter(ecn=ecn).order_by("id"))
    now = timezone.now()

    created_edges = 0
    confirmed_edges = 0
    rewritten: list[dict] = []

    with transaction.atomic():
        # a) 确保 affects 边
        for ei in impacts:
            link = TraceLink.objects.filter(
                project=project,
                from_type="ecn",
                from_id=ecn.ecn_number,
                relation_type=AFFECTS,
                to_type=ei.affected_type,
                to_id=ei.affected_id,
            ).first()
            if link is None:
                TraceLink.objects.create(
                    project=project,
                    from_type="ecn",
                    from_id=ecn.ecn_number,
                    to_type=ei.affected_type,
                    to_id=ei.affected_id,
                    relation_type=AFFECTS,
                    source=AGENT_SOURCE,
                    created_by=user,
                    confirmed_by=user,
                    confirmed_at=now,
                )
                created_edges += 1
            elif link.confirmed_by_id is None:
                link.confirmed_by = user
                link.confirmed_at = now
                link.save(update_fields=["confirmed_by", "confirmed_at"])
                confirmed_edges += 1

        # b) 写回受影响 bom_item 的 part ← replaces 目标
        for ei in impacts:
            if ei.affected_type != "bom_item":
                continue
            item = BomItem.objects.filter(bom__project=project, item_no=ei.affected_id).first()
            if item is None:
                continue
            replacement = _replacement_part(project, item.part)
            if replacement is None:
                continue
            if item.part_id != replacement.pk:
                old = item.part.part_number
                item.part = replacement
                item.save(update_fields=["part"])
                rewritten.append(
                    {"bom_item": item.item_no, "from": old, "to": replacement.part_number}
                )

    return {
        "ecn": ecn.ecn_number,
        "created_edges": created_edges,
        "confirmed_edges": confirmed_edges,
        "rewritten": rewritten,
        "ecn_status": ecn.status,
    }
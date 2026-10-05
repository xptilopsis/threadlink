"""TraceLink 端点解析服务（D4-R1）。

统一按 ``(project_id, entity_type, business_no)`` 唯一定位端点实体（R9，字典 §0.1）。
**多命中一律 fail-loud**（抛 ``AmbiguousReferenceError``，禁止 take-first）——这是
ADR-0007 附录 C 登记、V3 明确要求「D4/解析层对同 project 内歧义 BI 编号 fail-loud」
的落地。

映射表 13 项与 ``docs/data_dictionary.md`` §0.1「业务编号字段（冻结）」逐项一致；
``EntityType`` 白名单唯一来源为 ``schemas/agent_outputs.py``（不在本模块复制枚举）。
"""

from __future__ import annotations

from core.models import (
    Bom,
    BomItem,
    Document,
    ECN,
    GitCommit,
    InventoryLot,
    Part,
    PurchaseOrder,
    Requirement,
    Supplier,
    TestCase,
    TestRun,
    WorkOrder,
)
from schemas.agent_outputs import EntityType
from traceability.models import TraceLink


class TraceReferenceError(Exception):
    """TraceLink 端点解析失败基类。"""

    reason = "error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class UnknownEntityTypeError(TraceReferenceError):
    """entity_type 不在 ``EntityType`` 白名单内。"""

    reason = "unknown_type"


class EntityNotFoundError(TraceReferenceError):
    """业务编号在指定 project 内不存在。"""

    reason = "not_found"


class AmbiguousReferenceError(TraceReferenceError):
    """业务编号在指定 project 内多命中（间接归属路径尤甚）。"""

    reason = "ambiguous"


# entity_type -> (model, business_no field, project-scope lookup)
ENTITY_LOOKUP = {
    EntityType.PART.value: (Part, "part_number", "project"),
    EntityType.SUPPLIER.value: (Supplier, "code", "project"),
    EntityType.REQUIREMENT.value: (Requirement, "code", "project"),
    EntityType.BOM.value: (Bom, "bom_no", "project"),
    EntityType.BOM_ITEM.value: (BomItem, "item_no", "bom__project"),
    EntityType.INVENTORY_LOT.value: (InventoryLot, "serial_number", "project"),
    EntityType.WORK_ORDER.value: (WorkOrder, "code", "project"),
    EntityType.PURCHASE_ORDER.value: (PurchaseOrder, "po_number", "project"),
    EntityType.TEST_CASE.value: (TestCase, "code", "project"),
    EntityType.TEST_RUN.value: (TestRun, "run_no", "project"),
    EntityType.ECN.value: (ECN, "ecn_number", "project"),
    EntityType.DOCUMENT.value: (Document, "doc_no", "project"),
    EntityType.GIT_COMMIT.value: (GitCommit, "sha", "repo__project"),
}


def resolve_entity(project_id, entity_type: str, business_no: str):
    """按 ``(project_id, entity_type, business_no)`` 解析**唯一**实体实例。"""

    if entity_type not in ENTITY_LOOKUP:
        raise UnknownEntityTypeError(
            f"unknown_type：实体类型 {entity_type!r} 不在白名单 "
            f"{sorted(ENTITY_LOOKUP)} 内"
        )

    model, field, scope = ENTITY_LOOKUP[entity_type]
    matches = list(
        model._default_manager.filter(**{scope: project_id, field: business_no})[:2]
    )
    if not matches:
        raise EntityNotFoundError(
            f"not_found：{entity_type} 业务编号 {business_no!r} 在 project={project_id} 内不存在"
        )
    if len(matches) > 1:
        raise AmbiguousReferenceError(
            f"ambiguous：{entity_type} 业务编号 {business_no!r} 在 project={project_id} 内多命中（≥2），拒绝 take-first"
        )
    return matches[0]


def create_trace_link(
    project_id,
    from_type: str,
    from_id: str,
    to_type: str,
    to_id: str,
    relation_type: str,
    **kwargs,
):
    """先解析双方（任一失败即抛、不落库），成功才创建 ``TraceLink``。"""

    resolve_entity(project_id, from_type, from_id)
    resolve_entity(project_id, to_type, to_id)
    return TraceLink.objects.create(
        project_id=getattr(project_id, "pk", project_id),
        from_type=from_type,
        from_id=from_id,
        to_type=to_type,
        to_id=to_id,
        relation_type=relation_type,
        **kwargs,
    )
"""跨 Agent 引用存在性核验器（D5-R2 §3）。

D1 决策指定**跨 Agent 复用**（D6/D7 共用）。规则：

- 白名单 = ``schemas.agent_outputs.EntityType``（13 项，从 schemas 导入）；
- 复用 ``traceability.services.resolve_entity`` 做同 project 校验；
- ``reason ∈ {not_found, wrong_project, unknown_type}``（``FailureReason``）；
  解析器抛 ``AmbiguousReferenceError`` → 捕获记 ``reason="ambiguous"``
  （**D4 延后项 ②：D7 对账枚举**）；
- 「存在但属其它 project」判为 ``wrong_project``（resolve 未命中后回查是否存在同编号实体）；
- **自由文本引用不核验**（无 ``type`` / ``id`` 的引用跳过）。
"""

from __future__ import annotations

from dataclasses import dataclass

from schemas.agent_outputs import FailureReason
from traceability.services import (
    ENTITY_LOOKUP,
    AmbiguousReferenceError,
    TraceReferenceError,
    resolve_entity,
)

AMBIGUOUS_REASON = "ambiguous"  # D4 延后项 ②：不在 FailureReason 枚举，D7 对账


@dataclass
class InvalidRef:
    entity_type: str
    entity_id: str
    reason: str


def _field(ref, name):
    if isinstance(ref, dict):
        value = ref.get(name)
    else:
        value = getattr(ref, name, None)
    return getattr(value, "value", value)  # str-Enum → 原始字符串


def _missing_reason(entity_type: str, entity_id: str) -> str:
    """resolve 未命中时区分 ``not_found`` 与 ``wrong_project``。"""

    model, field, _scope = ENTITY_LOOKUP[entity_type]
    if model._default_manager.filter(**{field: entity_id}).exists():
        return FailureReason.WRONG_PROJECT.value
    return FailureReason.NOT_FOUND.value


def verify_references(project_id, refs) -> list[InvalidRef]:
    """返回引用核验失败清单（空列表 = 全部通过）。"""

    invalid: list[InvalidRef] = []
    for ref in refs or []:
        entity_type = _field(ref, "type")
        entity_id = _field(ref, "id")
        if not entity_type or not entity_id:
            continue  # 自由文本 / 不完整引用：不核验
        if entity_type not in ENTITY_LOOKUP:
            invalid.append(
                InvalidRef(entity_type, str(entity_id), FailureReason.UNKNOWN_TYPE.value)
            )
            continue
        try:
            resolve_entity(project_id, entity_type, entity_id)
        except AmbiguousReferenceError:
            invalid.append(InvalidRef(entity_type, str(entity_id), AMBIGUOUS_REASON))
        except TraceReferenceError:
            invalid.append(
                InvalidRef(
                    entity_type, str(entity_id), _missing_reason(entity_type, entity_id)
                )
            )
    return invalid
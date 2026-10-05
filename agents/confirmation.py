"""D5-R3 人工确认服务（approve / reject）。

- ``approve(agent_run, user)``：前置校验（`status==needs_review` 且 `reference_check_passed is True`）→
  事务内逐卡创建 `Requirement`（编号器自动）+ `RequirementParam` + `TraceLink`（每卡对源 Document 一条），
  并**更新同一行** AgentRun（`status=success`、`confirmed_by/at`）；任一步失败**整体回滚**（保持 `needs_review`）。
- ``reject(agent_run, user)``：校验同上 → `status=rejected`、`confirmed_by/at`；**不写任何实体**。
- **幂等**：对非 `needs_review` 行调用 → 抛 `ConfirmationError`，不重复写实体。
- **边界**：approve/reject **不产生新 AgentRun 行**（只更新），AgentRun 计数不变。
- **源文档编号口径**：`AgentRun` 无 document FK，源文档编号取自卡片 `source_refs` 中 `type=="document"`
  的第一条 `id`（prompt 已强制每卡带 document 引用）；缺失则 fail-loud。
- 文件沉淀（rejected → `prompts/*/failures/`，human-rejected 标注）按契约约定 **D7 实现，本轮不做**。
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from agents.models import AgentRun
from core.models import Requirement, RequirementParam, RequirementStatus
from schemas.agent_outputs import RequirementAgentOutput
from traceability.models import TraceLink

APPROVED_STATUS = "success"
REJECTED_STATUS = "rejected"
DOCUMENT_EDGE = "derived_from"


class ConfirmationError(Exception):
    """确认/拒绝前置校验失败或数据异常。"""


def _ensure_confirmable(agent_run):
    agent_run.refresh_from_db()  # 以 DB 真实状态为准（幂等/防脏对象）
    if agent_run.status != "needs_review":
        raise ConfirmationError(
            f"不可处置：当前 status={agent_run.status!r}（须为 needs_review）"
        )
    if agent_run.reference_check_passed is not True:
        raise ConfirmationError(
            f"不可处置：reference_check_passed={agent_run.reference_check_passed!r}（须为 True）"
        )


def _enum_value(value):
    return getattr(value, "value", value)


def _document_id(card, payload):
    for ref in list(card.source_refs or []) + list(getattr(payload, "source_refs", []) or []):
        if _enum_value(getattr(ref, "type", None)) == "document":
            return getattr(ref, "id", None)
    return None


def approve(agent_run, user):
    """批准 AgentRun：逐卡写 Requirement/RequirementParam/TraceLink，并同行转 success。"""

    _ensure_confirmable(agent_run)
    payload = RequirementAgentOutput.model_validate(agent_run.output_json or {})
    created_codes = []
    now = timezone.now()

    with transaction.atomic():
        for card in payload.cards:
            document_id = _document_id(card, payload)
            if not document_id:
                raise ConfirmationError(
                    f"卡片 {card.title!r} 缺少 document 来源引用，无法建立 TraceLink"
                )
            requirement = Requirement.objects.create(
                project=agent_run.project,
                title=card.title,
                content=card.content,
                source_type=_enum_value(card.source_type),
                priority=_enum_value(card.priority) if card.priority is not None else None,
                confidence=card.confidence,
                status=RequirementStatus.CONFIRMED,
                agent_run=agent_run,
                confirmed_by=user,
                confirmed_at=now,
            )
            for param in card.params:
                RequirementParam.objects.create(
                    requirement=requirement,
                    name=param.name,
                    operator=_enum_value(param.operator),
                    value_text=param.value_text or "",
                    value_num=param.value_num,
                    value_min=param.value_min,
                    value_max=param.value_max,
                    unit=param.unit or "",
                    is_mandatory=param.is_mandatory,
                )
            TraceLink.objects.create(
                project=agent_run.project,
                from_type="requirement",
                from_id=requirement.code,
                to_type="document",
                to_id=document_id,
                relation_type=DOCUMENT_EDGE,
                source="manual",
                confidence=card.confidence,
                agent_run=agent_run,
                confirmed_by=user,
                confirmed_at=now,
                created_by=user,
            )
            created_codes.append(requirement.code)

        AgentRun.objects.filter(pk=agent_run.pk).update(
            status=APPROVED_STATUS, confirmed_by=user, confirmed_at=now
        )
    return created_codes


def reject(agent_run, user):
    """拒绝 AgentRun：仅同行转 rejected，不写任何实体。"""

    _ensure_confirmable(agent_run)
    with transaction.atomic():
        AgentRun.objects.filter(pk=agent_run.pk).update(
            status=REJECTED_STATUS, confirmed_by=user, confirmed_at=timezone.now()
        )
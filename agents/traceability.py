"""Traceability Agent 管道（D7-R1）。

**字段权属**：链结构（``root`` / ``query_type`` / ``found`` / ``complete`` / ``nodes`` / ``edges`` /
``missing``）**一律来自 DB 权威** ``traceability.chain.build_trace_chain``；LLM **只产** ``summary``
（中文文案）与 ``trace_refs``（**引用建议**，走核验）。

流程：

- 解析 ``InventoryLot``（project 域）：**未命中 → 短路**（``found=false`` 负载，**不调 LLM、不建
  AgentRun、不写任何行**，对应 GT-TRACE-003）；**多命中 → ``AmbiguousReferenceError``**（fail-loud）。
- 命中：``build_trace_chain``（DB 权威）→ 渲染 prompt（链摘要）→ ``call_json``（内部模型
  ``{summary, trace_refs}``）→ 合并（DB 权威 + LLM 文案/引用）→ ``TraceabilityAgentOutput`` 复校 →
  ``verify_references(trace_refs)`` → **同一 AgentRun 行** update（通过 → ``needs_review``；失败 →
  ``failed`` + ``invalid_references``）→ ``output_json`` 落**合并后的全文**（D6 教训）。
- 恰好 +1 AgentRun；``fake`` 后端（``agent_run is None``）不落库、不核验更新。

``trace_refs`` 口径：prompt 限定 LLM 仅可引用链上编号清单；管道做**存在性核验**（复用
``agents.verification``）；清单外自由文本（无 ``type``/``id``）不入结构字段。非法枚举的引用建议
（如未知 ``relation_type``）被丢弃，不阻断整链。
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from pydantic import BaseModel, Field

from agents import llm
from agents.confirmation import ConfirmationError
from agents.models import AgentRun
from agents.verification import verify_references
from core.models import InventoryLot
from schemas.agent_outputs import TraceRef, TraceabilityAgentOutput
from traceability.chain import build_trace_chain, serial_not_found_payload
from traceability.services import AmbiguousReferenceError

PROMPT_ID = "prompt.traceability.chain"
PROMPT_VERSION = "v1"
PROMPTS_DIR = Path(settings.BASE_DIR) / "prompts" / "traceability_agent" / "v1"
DEFAULT_MAX_TOKENS = 2048
CHAIN_ENTITY_TYPE = "inventory_lot"


class PromptMissingError(Exception):
    """prompt 文件缺失（fail-loud）。"""


class TraceabilityAgentError(Exception):
    """管道级错误。"""


class TraceRefSuggestion(BaseModel):
    """LLM 内部引用建议（宽松字符串，管道再按 schema 收窄）。"""

    from_type: str = Field(min_length=1)
    from_id: str = Field(min_length=1)
    to_type: str = Field(min_length=1)
    to_id: str = Field(min_length=1)
    relation_type: str = Field(min_length=1)


class TraceabilityExplanation(BaseModel):
    """LLM 内部解释模型：仅 ``summary`` + ``trace_refs``。"""

    summary: str = Field(min_length=1)
    trace_refs: list[TraceRefSuggestion] = Field(default_factory=list)


def _load_prompts():
    system_path = PROMPTS_DIR / "system.md"
    template_path = PROMPTS_DIR / "user_template.md"
    for path in (system_path, template_path):
        if not path.exists():
            raise PromptMissingError(f"缺少 prompt 文件：{path}")
    return (
        system_path.read_text(encoding="utf-8"),
        template_path.read_text(encoding="utf-8"),
    )


def _nodes_text(payload) -> str:
    lines = [
        f"- {node['node_type']}:{node['node_id']}（{node['label']}，depth={node['depth']}）"
        for node in payload["nodes"]
    ]
    return "\n".join(lines) if lines else "（无）"


def _edges_text(payload) -> str:
    lines = [
        f"- {edge['from_node_id']} -{edge['relation_type']}-> {edge['to_node_id']}"
        for edge in payload["edges"]
    ]
    return "\n".join(lines) if lines else "（无）"


def _allowed_ids_text(payload) -> str:
    ids = sorted({f"{node['node_type']}:{node['node_id']}" for node in payload["nodes"]})
    return "、".join(ids) if ids else "（无）"


def _render_prompt(template: str, payload) -> str:
    edges = _edges_text(payload)
    return (
        template.replace("{root}", str(payload["root"]))
        .replace("{query_type}", str(payload["query_type"]))
        .replace("{found}", str(payload["found"]))
        .replace("{complete}", str(payload["complete"]))
        .replace("{missing}", str(payload["missing"]))
        .replace("{nodes}", _nodes_text(payload))
        .replace("{edges}", edges)
        .replace("{allowed_ids}", _allowed_ids_text(payload))
    )


def _collect_trace_refs(explanation: TraceabilityExplanation) -> list[TraceRef]:
    """LLM 建议 → ``TraceRef``；非法枚举条目丢弃（不入结构字段）。"""

    refs: list[TraceRef] = []
    for suggestion in explanation.trace_refs:
        try:
            refs.append(
                TraceRef(
                    from_type=suggestion.from_type,
                    from_id=suggestion.from_id,
                    to_type=suggestion.to_type,
                    to_id=suggestion.to_id,
                    relation_type=suggestion.relation_type,
                )
            )
        except Exception:  # noqa: BLE001 —— 非法类型/关系语义：丢弃单条，不阻断整链
            continue
    return refs


def _merge(chain_payload: dict, explanation: TraceabilityExplanation) -> TraceabilityAgentOutput:
    data = dict(chain_payload)
    data["summary"] = explanation.summary
    data["trace_refs"] = [
        ref.model_dump(mode="json") for ref in _collect_trace_refs(explanation)
    ]
    return TraceabilityAgentOutput.model_validate(data)


def _trace_ref_endpoints(output: TraceabilityAgentOutput) -> list[dict]:
    refs: list[dict] = []
    for ref in output.trace_refs:
        refs.append({"type": ref.from_type.value, "id": ref.from_id})
        refs.append({"type": ref.to_type.value, "id": ref.to_id})
    return refs


def run_traceability_agent(
    project, serial, user, *, query_type: str = "serial", model=None, temperature=0.0
):
    """执行追溯链解释管道，返回摘要 dict。"""

    serial = (serial or "").strip()

    # 1) 命中判定：未命中短路（零 LLM / 零 AgentRun / 零写）；多命中 fail-loud。
    matches = list(
        InventoryLot.objects.filter(project=project, serial_number=serial)[:2]
    )
    if len(matches) > 1:
        raise AmbiguousReferenceError(
            f"ambiguous：inventory_lot 业务编号 {serial!r} 在 project={project.pk} 内多命中（≥2），拒绝 take-first"
        )
    if not matches:
        payload = serial_not_found_payload(serial, query_type)
        output = TraceabilityAgentOutput.model_validate(payload)
        return {
            "ok": True,
            "found": False,
            "agent_run_id": None,
            "output": output.model_dump(mode="json"),
        }

    # 2) DB 权威链结构 + LLM 文案/引用建议
    chain_payload = build_trace_chain(
        project.pk, CHAIN_ENTITY_TYPE, serial, query_type=query_type
    )
    system, template = _load_prompts()
    user_message = _render_prompt(template, chain_payload)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message},
    ]

    try:
        result = llm.call_json(
            TraceabilityExplanation,
            messages,
            PROMPT_ID,
            PROMPT_VERSION,
            temperature=temperature,
            max_tokens=DEFAULT_MAX_TOKENS,
            project=project,
            agent_name="traceability",
            model=model,
        )
    except llm.LLMError:
        # call_json 已落 failed 行；管道不重复写
        raise

    run = result.agent_run
    if run is None:  # fake 后端：不落库、不核验更新
        return {
            "ok": True,
            "fake": True,
            "found": True,
            "agent_run_id": None,
        }

    output = _merge(chain_payload, result.parsed)
    invalid = verify_references(project.pk, _trace_ref_endpoints(output))

    if invalid:
        payload = [
            {"entity_type": item.entity_type, "entity_id": item.entity_id, "reason": item.reason}
            for item in invalid
        ]
        AgentRun.objects.filter(pk=run.pk).update(
            reference_check_passed=False,
            status="failed",
            invalid_references=payload,
            output_json=output.model_dump(mode="json"),  # 落合并结果全文（D6 教训）
        )
        return {
            "ok": False,
            "found": True,
            "agent_run_id": run.pk,
            "invalid_references": payload,
            "output": output.model_dump(mode="json"),
        }

    AgentRun.objects.filter(pk=run.pk).update(
        reference_check_passed=True,
        output_json=output.model_dump(mode="json"),  # 落合并结果全文（D6 教训）
    )
    return {
        "ok": True,
        "found": True,
        "agent_run_id": run.pk,
        "summary": output.summary,
        "output": output.model_dump(mode="json"),
    }

def approve_traceability(agent_run, user):
    """批准 ``traceability`` 运行 → **纯审计确认**（D7-R2 裁决 A，见 ADR-0013）。

    - 前置：``status==needs_review`` 且 ``reference_check_passed is True``（``refresh_from_db`` 后判定）；
    - 事务内**同一行** ``update(status="success", confirmed_by, confirmed_at)``；
    - **零实体写入**（Requirement / Bom / BomItem / TraceLink 计数前后不变）——链结构为 DB 权威派生，
      LLM 仅补 ``summary``；``trace_refs`` 为建议，落库语义在契约 §6 无 traceability 专属定义；
    - **幂等**：非 ``needs_review`` → ``ConfirmationError``；**AgentRun 计数不变**。
    """

    agent_run.refresh_from_db()
    if agent_run.status != "needs_review":
        raise ConfirmationError(
            f"不可确认：当前 status={agent_run.status!r}（须为 needs_review）"
        )
    if agent_run.reference_check_passed is not True:
        raise ConfirmationError(
            f"不可确认：reference_check_passed={agent_run.reference_check_passed!r}（须为 True）"
        )

    now = timezone.now()
    with transaction.atomic():
        AgentRun.objects.filter(pk=agent_run.pk).update(
            status="success", confirmed_by=user, confirmed_at=now
        )
    return {"agent_run_id": agent_run.pk, "audit_only": True}
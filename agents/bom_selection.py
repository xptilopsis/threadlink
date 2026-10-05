"""BOM Selection Agent 管道（D6-R2）。

**引擎权威**：候选集 / `score` / `unit_price` / `lead_time_days` / `lifecycle_status` / 排序**一律来自
`core.selection.select()`（冻结）**；LLM **只写解释文案**（`rationale` / `summary`）与**建议字段**
`replaces_part_id`，且不得改写任何引擎值。

流程：`select()` → 渲染 prompt → `call_json`（内部说明模型）→ 合并（引擎值 + LLM 文案）→ 组装
`BomSelectionAgentOutput` 并**再跑一次 Pydantic 校验** → 引用核验（`agents/verification`）→
**同一 AgentRun 行**更新（`reference_check_passed` / `status` / `invalid_references`）。恰好 +1 AgentRun。

- `score` 映射：引擎 `total_score`（0–100）→ schema `score`（0–1，`/100`）。
- `replaces_part_id` 口径：LLM 从管道提供的「被排除清单」中选取、**仅建议字段**（落库必须经 TraceLink，登记 R3）；
  管道做**存在性核验**（经 `verify_references`）。缺省省略。
- `fake` 后端（`agent_run is None`）**不落库、不核验更新**。
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from pydantic import BaseModel, Field

from agents import llm
from agents.models import AgentRun
from agents.verification import verify_references
from core.models import Part
from core.selection import Criteria, select
from schemas.agent_outputs import (
    AgentName,
    BomCandidate,
    BomSelectionAgentOutput,
    Param,
    SourceRef,
)

PROMPT_ID = "prompt.bom.selection"
PROMPT_VERSION = "v1"
PROMPTS_DIR = Path(settings.BASE_DIR) / "prompts" / "bom_selection_agent" / "v1"


class PromptMissingError(Exception):
    """prompt 文件缺失（fail-loud）。"""


class CandidateExplanation(BaseModel):
    """LLM 内部说明模型（每候选一条；仅文案与建议字段）。"""

    part_number: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    replaces_part_id: str | None = None


class BomExplanationOutput(BaseModel):
    summary: str | None = None
    candidates: list[CandidateExplanation] = Field(min_length=1)


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


def _criteria_text(criteria: Criteria) -> str:
    return (
        f"输入电压 覆盖 {criteria.voltage_min}-{criteria.voltage_max} V；"
        f"额定电流 ≥ {criteria.current_min} A；"
        f"工作温度 覆盖 {criteria.temp_min}~{criteria.temp_max} °C；"
        f"防护等级 ≥ IP{criteria.ip_min}；"
        f"单料成本上限 {criteria.cost_max if criteria.cost_max is not None else '未启用'}"
    )


def _candidates_text(result) -> str:
    lines = []
    for candidate in result.passed:
        lines.append(
            f"- {candidate.part_number}：score={candidate.total_score}/100 "
            f"min_price={candidate.min_price} min_lead={candidate.min_lead} "
            f"有效源数={candidate.source_count} warnings={candidate.warnings}"
        )
    return "\n".join(lines) if lines else "（无候选）"


def _excluded_text(result) -> str:
    return "\n".join(
        f"- {item.part_number}：{item.reason}" for item in result.excluded
    ) or "（无）"


def _criteria_params(criteria: Criteria) -> list[Param]:
    params = [
        Param(name="input_voltage", operator="range", value_min=criteria.voltage_min, value_max=criteria.voltage_max, unit="V", is_mandatory=True),
        Param(name="rated_current", operator="gte", value_num=criteria.current_min, unit="A", is_mandatory=True),
        Param(name="operating_temp", operator="range", value_min=criteria.temp_min, value_max=criteria.temp_max, unit="C", is_mandatory=True),
        Param(name="ip_rating", operator="eq", value_text=f"IP{criteria.ip_min}", is_mandatory=True),
    ]
    if criteria.cost_max is not None:
        params.append(Param(name="bom_cost", operator="lte", value_num=criteria.cost_max, unit="CNY", is_mandatory=True))
    return params


def _build_output(project, criteria: Criteria, engine_result, explanation: BomExplanationOutput) -> BomSelectionAgentOutput:
    numbers = [candidate.part_number for candidate in engine_result.passed]
    parts = {
        part.part_number: part
        for part in Part.objects.filter(project=project, part_number__in=numbers)
    }
    explanations = {item.part_number: item for item in explanation.candidates}

    candidates = []
    for candidate in engine_result.passed:
        part = parts.get(candidate.part_number)
        item = explanations.get(candidate.part_number)
        rationale = item.rationale if item and item.rationale else "（引擎候选，无额外解释）"
        candidates.append(
            BomCandidate(
                part_number=candidate.part_number,
                name=part.name if part else candidate.part_number,
                manufacturer=(part.manufacturer or None) if part else None,
                category=(part.category or None) if part else None,
                lifecycle_status=part.lifecycle_status if part else "active",
                discontinued=(part.lifecycle_status in ("obsolete", "discontinued")) if part else False,
                unit_price=candidate.min_price,
                lead_time_days=candidate.min_lead,
                score=float(candidate.total_score) / 100,
                replaces_part_id=(item.replaces_part_id if item else None),
                rationale=rationale,
                source_refs=[],
            )
        )

    warnings = [warning for candidate in engine_result.passed for warning in candidate.warnings]
    return BomSelectionAgentOutput(
        agent_name=AgentName.BOM_SELECTION,
        summary=explanation.summary,
        request_params=_criteria_params(criteria),
        candidates=candidates,
        recommended_part_id=candidates[0].part_number if candidates else None,
        trace_refs=[],
        warnings=warnings,
    )


def run_bom_selection_agent(project, criteria: Criteria, user, *, model=None, temperature=0.2):
    """执行 BOM 选型解释管道，返回摘要 dict。"""

    engine_result = select(project, criteria)
    if not engine_result.passed:
        return {"ok": False, "reason": "no_candidates", "candidates": 0}

    system, template = _load_prompts()
    user_message = (
        template.replace("{criteria}", _criteria_text(criteria))
        .replace("{candidates}", _candidates_text(engine_result))
        .replace("{excluded}", _excluded_text(engine_result))
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message},
    ]

    try:
        result = llm.call_json(
            BomExplanationOutput,
            messages,
            PROMPT_ID,
            PROMPT_VERSION,
            temperature=temperature,
            max_tokens=2048,
            project=project,
            agent_name="bom_selection",
            model=model,
        )
    except llm.LLMError:
        raise  # call_json 已落 failed 行；管道不重复写

    run = result.agent_run
    if run is None:  # fake 后端
        return {"ok": True, "fake": True, "agent_run_id": None, "candidates": len(engine_result.passed)}

    # 合并（引擎值 + LLM 文案）→ 组装 → 二次 Pydantic 校验
    output = _build_output(project, criteria, engine_result, result.parsed)

    # 核验：source_refs + replaces_part_id
    refs = []
    for candidate in output.candidates:
        refs.extend(candidate.source_refs or [])
        if candidate.replaces_part_id:
            refs.append({"type": "part", "id": candidate.replaces_part_id})
    invalid = verify_references(project.pk, refs)

    if invalid:
        payload = [
            {"entity_type": item.entity_type, "entity_id": item.entity_id, "reason": item.reason}
            for item in invalid
        ]
        AgentRun.objects.filter(pk=run.pk).update(
            reference_check_passed=False,
            status="failed",
            invalid_references=payload,
        )
        return {
            "ok": False,
            "agent_run_id": run.pk,
            "candidates": len(output.candidates),
            "invalid_references": payload,
            "output": output.model_dump(mode="json"),
        }

    AgentRun.objects.filter(pk=run.pk).update(reference_check_passed=True)
    return {
        "ok": True,
        "agent_run_id": run.pk,
        "candidates": len(output.candidates),
        "recommended": output.recommended_part_id,
        "output": output.model_dump(mode="json"),
    }
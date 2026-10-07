"""D12-R2（commit 3）：GT-JSON-001/003/004/006/007/008 craft + JSON-002（schema 级）。

分层：本文件全部为 **T3 craft**（直调 `validate_agent_output`，无 LLM、无 DB）；
JSON-002 的 **T1 live** 面（真截断 → `failed`）由 `tests/test_llm_r1.py::test_live_truncation` 覆盖。
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from schemas.agent_outputs import (
    AgentName,
    AgentRunCreate,
    BomSelectionAgentOutput,
    Param,
    RequirementAgentOutput,
    TraceEdge,
    TraceabilityAgentOutput,
    validate_agent_output,
)


def _candidate(**over):
    base = {
        "part_number": "PART-001",
        "name": "DC-DC 电源模块",
        "lifecycle_status": "active",
        "unit_price": "42.50",
        "lead_time_days": 14,
        "score": 0.9479,
        "rationale": "交期最短、成本适中",
        "source_refs": [{"type": "part", "id": "PART-001"}],
    }
    base.update(over)
    return base


def _bom(candidates):
    return {"agent_name": "bom_selection", "candidates": candidates}


# --- JSON-001 合法输出通过（T3） -------------------------------------------
def test_json_001_valid_passes():
    result = validate_agent_output("bom_selection", _bom([_candidate()]))
    assert isinstance(result, BomSelectionAgentOutput)
    assert result.candidates[0].unit_price == Decimal("42.50")  # Decimal 解析
    # 枚举 AgentName 与字符串等价
    assert isinstance(
        validate_agent_output(AgentName.BOM_SELECTION, _bom([_candidate()])),
        BomSelectionAgentOutput,
    )


# --- JSON-002 非法载荷不可解析（T3；T1 live 见 test_llm_r1） ---------------
def test_json_002_invalid_payload_fails():
    with pytest.raises(ValidationError):
        validate_agent_output("requirement", "not-a-json-object")
    with pytest.raises(ValidationError):
        validate_agent_output("requirement", [1, 2, 3])  # 合法 JSON 但非对象


# --- JSON-003 缺必填字段（T3） ---------------------------------------------
def test_json_003_missing_required():
    with pytest.raises(ValidationError):
        validate_agent_output("requirement", {"agent_name": "requirement"})  # 缺 cards

    with pytest.raises(ValidationError):
        validate_agent_output("requirement", {"agent_name": "requirement", "cards": []})  # min_length

    candidate = _candidate()
    del candidate["lifecycle_status"]  # BomCandidate 缺必填
    with pytest.raises(ValidationError):
        validate_agent_output("bom_selection", _bom([candidate]))


# --- JSON-004 未知字段 extra="forbid"（T3） --------------------------------
def test_json_004_extra_forbidden():
    with pytest.raises(ValidationError) as ei:
        validate_agent_output("bom_selection", _bom([_candidate(magic_score=0.99)]))
    assert any(err["type"] == "extra_forbidden" for err in ei.value.errors())
    # 大小写不符 → 视为未知字段
    candidate = _candidate()
    candidate["Lifecycle_Status"] = "active"
    with pytest.raises(ValidationError):
        validate_agent_output("bom_selection", _bom([candidate]))


# --- JSON-006 数值越界与枚举非法（T3） -------------------------------------
def test_json_006_bounds_and_enum():
    with pytest.raises(ValidationError):
        validate_agent_output("bom_selection", _bom([_candidate(score=1.5)]))  # score ∈ [0,1]
    with pytest.raises(ValidationError):
        validate_agent_output("bom_selection", _bom([_candidate(lifecycle_status="unknown")]))
    with pytest.raises(ValidationError):
        TraceEdge(from_node_id="A", to_node_id="B", relation_type="foo")

    # 合法边界
    assert validate_agent_output("bom_selection", _bom([_candidate(score=0.0)])).candidates[0].score == 0.0
    assert validate_agent_output("bom_selection", _bom([_candidate(score=1.0)])).candidates[0].score == 1.0
    # temperature ∈ [0,2]
    with pytest.raises(ValidationError):
        AgentRunCreate(
            agent_name="requirement", prompt_id="p", prompt_version="v1", model="m",
            temperature=-0.1, input_json={}, input_hash="a" * 64,
        )
    AgentRunCreate(
        agent_name="requirement", prompt_id="p", prompt_version="v1", model="m",
        temperature=2.0, input_json={}, input_hash="a" * 64,
    )


# --- JSON-007 Param 取值一致性（T3） ---------------------------------------
def test_json_007_param_consistency():
    with pytest.raises(ValidationError):
        Param(name="x", operator="range", value_max=1)  # 缺 value_min
    with pytest.raises(ValidationError):
        Param(name="x", operator="range", value_min=5, value_max=1)  # min>max
    with pytest.raises(ValidationError):
        Param(name="x", operator="gte")
    with pytest.raises(ValidationError):
        Param(name="x", operator="lte")
    with pytest.raises(ValidationError):
        Param(name="x", operator="eq")
    assert Param(name="x", operator="eq", value_text="IP65").value_text == "IP65"
    assert Param(name="x", operator="range", value_min=1, value_max=1)  # min==max 合法


# --- JSON-008 agent_name 映射（T3） ----------------------------------------
def test_json_008_agent_name_routing():
    assert isinstance(
        validate_agent_output(
            "traceability",
            {"root": "SN-X", "found": False, "complete": False, "nodes": [], "missing": ["serial_not_found"]},
        ),
        TraceabilityAgentOutput,
    )
    assert isinstance(
        validate_agent_output(
            "requirement",
            {"cards": [{"title": "t", "content": "c", "source_type": "email", "confidence": 0.5}]},
        ),
        RequirementAgentOutput,
    )
    with pytest.raises((ValueError, KeyError)):
        validate_agent_output("unknown_agent", {})  # 不静默回退
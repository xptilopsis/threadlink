"""ThreadLink 智能体输出契约（Pydantic v2）。

本模块只定义**数据结构契约**与**校验模型**，不含任何 view / service / 数据库逻辑。
所有 LLM 输出必须先经本模块模型校验后才可落库；校验失败时由调用方记录
``AgentRun.status = "failed"``、``output_schema_valid = False`` 并填写 ``error``。

校验分两个**独立步骤**：①本模块 schema 校验（结构、类型、范围、枚举）；②引用
存在性核验（核验 ``SourceRef.id`` / ``recommended_part_id`` / ``TraceNode.node_id``
等引用是否真实存在）。Pydantic 无法拦截幻觉 ID，schema 通过后必须执行第 ② 步；
第 ② 步失败时同样记录 ``AgentRun.status = "failed"``、``reference_check_passed = False``
并将失败条目写入 ``invalid_references``。

引用核验规则（D2）：每个结构化引用 ``(entity_type, entity_id)`` 必须 (a) ``entity_type``
在实体类型白名单（``EntityType``）内，(b) 实体存在，(c) 属于同一 ``project_id``。
``entity_id`` 为业务编号（R2），禁用数据库主键。自由文本引用（页码 / 章节号 / 文件名片段）
不做核验。

字段命名约定：金额使用 ``Decimal``（JSON 中以字符串传输，如 "12.50"）；
时间使用 ``datetime``（ISO8601）；人工确认统一使用 ``confirmed_by`` / ``confirmed_at``
（对应数据库列 ``confirmed_by_id`` / ``confirmed_at``）。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentName(str, Enum):
    REQUIREMENT = "requirement"
    BOM_SELECTION = "bom_selection"
    TRACEABILITY = "traceability"


class AgentRunStatus(str, Enum):
    """AgentRun 状态（R1：固定四值，只对应实际发生的 LLM 调用）。

    ``failed`` / ``needs_review`` 为机器侧终态/待处理态；``success`` / ``rejected``
    为人工处置后的终态。``success`` / ``rejected`` 时 ``confirmed_by`` / ``confirmed_at``
    必填；``failed`` / ``needs_review`` 时二者必须为 NULL。
    """

    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"
    SUCCESS = "success"
    REJECTED = "rejected"


class FailureReason(str, Enum):
    """引用存在性核验失败原因（D2 决策）。"""

    NOT_FOUND = "not_found"
    WRONG_PROJECT = "wrong_project"
    UNKNOWN_TYPE = "unknown_type"


class EntityType(str, Enum):
    """可作 TraceLink from/to 端点与追溯节点（`TraceNode`）的实体类型白名单。

    与 `data_dictionary.md` §0.1「可作端点的业务编号实体」一一对应。`User` / `Project`
    仅经 FK 关联、`AgentRun` / `TraceLink` 为审计记录、明细表（`PartParam` 等，含
    `ECNImpact`）无业务编号，均**不作多态端点**，故不在白名单内。
    """

    REQUIREMENT = "requirement"
    PART = "part"
    SUPPLIER = "supplier"
    BOM = "bom"
    BOM_ITEM = "bom_item"
    INVENTORY_LOT = "inventory_lot"
    WORK_ORDER = "work_order"
    PURCHASE_ORDER = "purchase_order"
    TEST_CASE = "test_case"
    TEST_RUN = "test_run"
    ECN = "ecn"
    DOCUMENT = "document"
    GIT_COMMIT = "git_commit"


class ReferenceType(str, Enum):
    DOCUMENT = "document"
    GIT_COMMIT = "git_commit"
    PART = "part"
    REQUIREMENT = "requirement"
    TEST_CASE = "test_case"
    TEST_RUN = "test_run"
    INVENTORY_LOT = "inventory_lot"
    PURCHASE_ORDER = "purchase_order"
    BOM = "bom"
    BOM_ITEM = "bom_item"
    ECN = "ecn"
    TRACE_LINK = "trace_link"
    SUPPLIER = "supplier"


class TraceRelationType(str, Enum):
    DERIVED_FROM = "derived_from"
    SATISFIED_BY = "satisfied_by"
    IMPLEMENTED_BY = "implemented_by"
    VERIFIED_BY = "verified_by"
    DOCUMENTED_BY = "documented_by"
    ORDERED_BY = "ordered_by"
    SOURCED_FROM = "sourced_from"
    TESTED_BY = "tested_by"
    AFFECTED_BY = "affected_by"
    AFFECTS = "affects"
    EVIDENCES = "evidences"
    ALLOCATES = "allocates"
    REPLACES = "replaces"
    SUPERSEDES = "supersedes"
    REFERENCES = "references"


class ParamOperator(str, Enum):
    EQ = "eq"
    GTE = "gte"
    LTE = "lte"
    RANGE = "range"


class SourceType(str, Enum):
    PRD = "prd"
    SOR = "sor"
    EMAIL = "email"
    MANUAL = "manual"


class LifecycleStatus(str, Enum):
    ACTIVE = "active"
    NRND = "nrnd"
    EOL = "eol"
    OBSOLETE = "obsolete"


class LinkSource(str, Enum):
    MANUAL = "manual"
    AGENT = "agent"
    IMPORT = "import"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class _StrictModel(BaseModel):
    """LLM 输出基类：禁止未声明字段，保证输出 schema 可校验、防幻觉。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceRef(_StrictModel):
    """可核验的引用来源，用于防幻觉。"""

    type: ReferenceType
    id: str = Field(min_length=1)
    locator: str | None = Field(default=None, description="页码 / 行号 / commit path 等")
    snippet: str | None = Field(default=None, description="引用原文片段")


class TraceRef(_StrictModel):
    """建议写入 TraceLink 的跨域追溯关系（未经确认不得生效）。"""

    from_type: EntityType
    from_id: str = Field(min_length=1)
    to_type: EntityType
    to_id: str = Field(min_length=1)
    relation_type: TraceRelationType
    source: LinkSource = LinkSource.AGENT
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: list[SourceRef] | None = Field(
        default=None, description="证据引用（文件 / Git 提交 / 业务记录），防幻觉核验"
    )
    metadata: dict[str, Any] | None = None
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None


class Param(_StrictModel):
    """参数契约，覆盖 eq / gte / lte / range 四种取值方式。"""

    name: str = Field(min_length=1)
    operator: ParamOperator = ParamOperator.EQ
    value_text: str | None = None
    value_num: Decimal | None = None
    value_min: Decimal | None = None
    value_max: Decimal | None = None
    unit: str | None = None
    is_mandatory: bool = True

    @model_validator(mode="after")
    def _check_operator_values(self) -> "Param":
        if self.operator == ParamOperator.RANGE:
            if self.value_min is None or self.value_max is None:
                raise ValueError("range 操作符必须提供 value_min 与 value_max")
            if self.value_min > self.value_max:
                raise ValueError("value_min 不能大于 value_max")
        elif self.operator in (ParamOperator.GTE, ParamOperator.LTE):
            if self.value_num is None:
                raise ValueError("gte / lte 操作符必须提供 value_num")
        elif self.operator == ParamOperator.EQ:
            if self.value_num is None and self.value_text is None:
                raise ValueError("eq 操作符必须提供 value_num 或 value_text")
        return self


class RequirementCard(_StrictModel):
    """需求智能体产出的单张需求卡（候选，需人工确认）。"""

    id: str | None = Field(default=None, description="草稿 ID，例如 REQ-DRAFT-01")
    code: str | None = None
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source_type: SourceType
    priority: Priority | None = None
    params: list[Param] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    confirmed: bool = False
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None


class RequirementAgentOutput(_StrictModel):
    """需求智能体完整输出契约（对应 AgentName.REQUIREMENT）。"""

    agent_name: AgentName = AgentName.REQUIREMENT
    summary: str | None = None
    cards: list[RequirementCard] = Field(min_length=1, description="至少 1 张需求卡")
    source_refs: list[SourceRef] = Field(default_factory=list)
    trace_refs: list[TraceRef] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

class BomCandidate(_StrictModel):
    """选型候选物料，须含停产、交期、成本与替代理由。"""

    part_id: str | None = None
    part_number: str | None = None
    name: str = Field(min_length=1)
    manufacturer: str | None = None
    category: str | None = None
    lifecycle_status: LifecycleStatus
    discontinued: bool = False
    unit_price: Decimal | None = None
    currency: str = "CNY"
    lead_time_days: int | None = Field(default=None, ge=0)
    moq: int | None = Field(default=None, ge=0)
    supplier_id: str | None = None
    score: float = Field(ge=0.0, le=1.0, description="规则评分")
    is_alternative: bool = False
    replaces_part_id: str | None = Field(
        default=None, description="被替代物料的业务编号（`Part.part_number`，R2；非数据库主键）"
    )
    rationale: str = Field(min_length=1, description="替代 / 推荐理由（LLM 解释，须有依据）")
    source_refs: list[SourceRef] = Field(default_factory=list)


class BomSelectionAgentOutput(_StrictModel):
    """BOM / 选型智能体完整输出契约（对应 AgentName.BOM_SELECTION）。"""

    agent_name: AgentName = AgentName.BOM_SELECTION
    summary: str | None = None
    request_params: list[Param] = Field(default_factory=list)
    candidates: list[BomCandidate] = Field(min_length=1, description="至少 1 个候选")
    recommended_part_id: str | None = None
    trace_refs: list[TraceRef] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TraceNode(_StrictModel):
    """追溯链上的一个节点。"""

    node_type: EntityType
    node_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    relation_type: TraceRelationType | None = Field(
        default=None, description="指向前驱节点的关系语义"
    )
    depth: int = Field(default=0, ge=0)
    source_refs: list[SourceRef] = Field(default_factory=list)
    confirmed: bool = False
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None


class TraceEdge(_StrictModel):
    """追溯链上的一条边。"""

    from_node_id: str = Field(min_length=1)
    to_node_id: str = Field(min_length=1)
    relation_type: TraceRelationType
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_refs: list[SourceRef] = Field(default_factory=list)


class TraceabilityAgentOutput(_StrictModel):
    """追溯智能体完整输出契约（对应 AgentName.TRACEABILITY）。

    ``found`` 表示**查询根实体（序列号 / 批次号）是否存在**，而非链上是否有节点。
    强制不变量：``found=False`` 时 ``nodes`` 必须为空；``found=True`` 时 ``nodes``
    至少包含根节点本身。根实体存在但未建立任何 TraceLink 时，返回
    ``found=True`` + 根节点 + ``complete=False`` + ``missing=["no_trace_links"]``
    （机器 token；``warnings`` 可保留人类可读镜像，不作机器判定依据）。

    ``found`` 与 ``complete`` 是**准正交**维度（``found=False`` 时 ``complete`` 必为
    ``False``）。``complete`` 表示链路是否完整，与 ``missing`` 满足**双向强制**：
    ``complete=True ⟺ missing=[]``（即 ``complete=False`` 且 ``missing=[]`` 非法）。
    ``missing`` 为导致链不完整的原因列表（机器 token，如 ``serial_not_found`` /
    ``no_trace_links``），必有值。
    """

    agent_name: AgentName = AgentName.TRACEABILITY
    summary: str | None = None
    root: str = Field(min_length=1, description="查询输入的回显（序列号 / 批次号），不代表命中")
    query_type: Literal["serial", "lot"] = "serial"
    found: bool = Field(description="查询根实体是否存在")
    complete: bool = Field(description="链路是否完整（准正交：found=False 时必为 False；complete ⇔ missing=[]）")
    nodes: list[TraceNode] = Field(default_factory=list)
    edges: list[TraceEdge] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list, description="链路中缺失的环节")
    trace_refs: list[TraceRef] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _empty_chain_invariant(self) -> "TraceabilityAgentOutput":
        if not self.found and self.nodes:
            raise ValueError("found=False 时 nodes 必须为空")
        if self.found and not self.nodes:
            raise ValueError("found=True 时 nodes 至少包含根节点")
        if not self.found and self.complete:
            raise ValueError("found=False 时 complete 必须为 False")
        if self.complete and self.missing:
            raise ValueError("complete=True 时 missing 必须为空")
        if not self.complete and not self.missing:
            raise ValueError("missing 为空时 complete 必须为 True（complete ⇔ missing=[] 双向）")
        return self


class InvalidReference(_StrictModel):
    """引用存在性核验失败条目（D2 决策）。``entity_id`` 为业务编号（R2）。"""

    entity_type: EntityType = Field(description="实体类型白名单，与 TraceLink 共用 EntityType")
    entity_id: str = Field(min_length=1, description="业务编号，非数据库主键")
    reason: FailureReason


class AgentRunCreate(_StrictModel):
    """创建一次智能体调用时提交的审计信息（不含输出）。"""

    agent_name: AgentName
    prompt_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    model: str = Field(min_length=1)
    temperature: float = Field(ge=0.0, le=2.0)
    input_json: dict[str, Any]
    input_hash: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$", description="输入 SHA-256"
    )
    references: list[SourceRef] = Field(default_factory=list)


class AgentRunRead(BaseModel):
    """AgentRun 审计记录的读取契约（一次调用一条）。"""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    agent_name: AgentName
    prompt_id: str
    prompt_version: str
    model: str
    temperature: float
    input_json: dict[str, Any]
    input_hash: str
    output_json: dict[str, Any] | None = None
    output_schema_valid: bool
    reference_check_passed: bool | None = Field(
        default=None,
        description="引用存在性核验是否通过；None=未执行到核验步骤，False=核验失败",
    )
    invalid_references: list[InvalidReference] = Field(default_factory=list)
    references: list[SourceRef] = Field(default_factory=list)
    status: AgentRunStatus
    error: str | None = None
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    created_at: datetime


OUTPUT_MODELS: dict[AgentName, type[BaseModel]] = {
    AgentName.REQUIREMENT: RequirementAgentOutput,
    AgentName.BOM_SELECTION: BomSelectionAgentOutput,
    AgentName.TRACEABILITY: TraceabilityAgentOutput,
}


def validate_agent_output(agent_name: AgentName | str, payload: Any) -> BaseModel:
    """校验 LLM 输出并返回对应模型实例。

    仅做 schema 校验，不涉及任何业务或数据库逻辑。校验失败时抛出
    ``pydantic.ValidationError``，调用方应据此将 AgentRun 标记为
    ``status="failed"`` 且 ``output_schema_valid=False``。
    """

    name = agent_name if isinstance(agent_name, AgentName) else AgentName(str(agent_name))
    return OUTPUT_MODELS[name].model_validate(payload)


__all__ = [
    "AgentName",
    "AgentRunStatus",
    "FailureReason",
    "EntityType",
    "ReferenceType",
    "TraceRelationType",
    "ParamOperator",
    "SourceType",
    "LifecycleStatus",
    "LinkSource",
    "Priority",
    "SourceRef",
    "TraceRef",
    "Param",
    "RequirementCard",
    "RequirementAgentOutput",
    "BomCandidate",
    "BomSelectionAgentOutput",
    "TraceNode",
    "TraceEdge",
    "TraceabilityAgentOutput",
    "InvalidReference",
    "AgentRunCreate",
    "AgentRunRead",
    "OUTPUT_MODELS",
    "validate_agent_output",
]
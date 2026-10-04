# ADR-0002：空链语义（found/complete/missing）、引用存在性核验与 R1 AgentRun 边界

| 项 | 内容 |
| --- | --- |
| 状态 | 已接受（Accepted） |
| 日期 | 2026-10-04 |
| 里程碑 | D1（范围冻结） |
| 关联 | `docs/interface_contract.md` §3.1 · `schemas/agent_outputs.py` · `docs/golden_tests.md` §2.4/§2.5/§6 · R1/R2 |

## 背景

原始契约有三处冲突/缺口：

1. `TraceabilityAgentOutput.nodes` 曾定义 `min_length = 1`，与「序列号查不到应返回空链、禁止编造」冲突；
2. Pydantic 只做结构校验，**无法拦截幻觉 ID**（引用不存在的实体）；
3. 「什么算一次 AgentRun」未明确，容易被纯查询污染审计。

## 决策

### 1. 空链语义（两个正交维度）

`TraceabilityAgentOutput` 用 `found` 与 `complete` 表达结果：

- `found`：**查询根实体（序列号 / 批次号）是否存在**，与「链上是否有节点」无关；
- `complete`：**链路是否完整**（`missing` 非空即 `false`；`found=false` 时必为 `false`）。

强制不变量（`@model_validator`）：`found=false ⟺ nodes=[]`；`found=true ⟹ nodes` 至少含根节点；`complete=true ⟹ missing=[]`。

响应情形（与 `interface_contract` §3.1 情形表一致）：

| 情形 | found | complete | nodes | missing / warnings |
| --- | --- | --- | --- | --- |
| 根实体不存在 | false | false | `[]` | `missing=["serial_not_found"]` |
| 根存在但无 TraceLink | true | false | 含根节点 | `warnings=["未建立追溯链"]` |
| 链路完整 | true | true | 全链 | `missing=[]` |
| 链路有断点 | true | false | 已存在节点 | `missing=[...]` |

- `root` 字段：查询输入回显（仅审计，**不代表命中**），`found=false` 时仍须回显；
- **`found=false` 是合法业务结果（HTTP 200），严禁记 `failed`**；未命中**先查库、短路返回、不调用 LLM**；每个 `TraceNode` 必须带 `source_refs`。

### 2. 引用存在性核验（独立步骤）

时机：LLM 返回 → Pydantic 结构校验 → **引用核验** → 人工确认队列。

每个结构化引用 `(entity_type, entity_id)` 必须：(a) `entity_type` 在 `EntityType` 白名单内；(b) 实体存在；(c) 属同一 `project_id`。`entity_id` 为业务编号（R2）。失败：`AgentRun.status="failed"`、`reference_check_passed=false`、`invalid_references=[{entity_type, entity_id, reason}]`（`reason ∈ {not_found|wrong_project|unknown_type}`）、`output_json` 保留供调试并沉淀到 `prompts/<agent>/v1/failures/`，**不进入人工确认队列**，HTTP `422`。自由文本引用（页码/章节/文件名片段）不核验。

### 3. R1 AgentRun 边界与 status 四值

- **AgentRun 只对应实际发生的 LLM 调用**：无 LLM 调用（短路返回、纯 DB 查询、LLM 前输入校验失败）= **无 AgentRun**；LLM 已调用但输出非法 = 记 AgentRun，`status="failed"`。
- `AgentRun.status` 四值：`failed | needs_review | success | rejected`；`success`/`rejected` ⟹ `confirmed_by`/`confirmed_at` 必填，`failed`/`needs_review` ⟹ 二者必须 NULL；确认队列 = `status=needs_review`。

## 后果

- 正向：空结果不再被误判为失败；幻觉 ID 在结构校验后被独立拦截；审计只记录真实 LLM 调用。
- 负向 / 成本：需维护 `EntityType` 白名单与 `(project_id, entity_type, business_no)` 解析规则，D2 引用核验与 TraceLink 端点解析共用同一规则。
- 本 ADR 只冻结契约，不写业务逻辑、不做迁移。
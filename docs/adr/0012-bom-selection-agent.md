# ADR-0012：BOM 选型解释层（D6-R2）

| 项 | 内容 |
| --- | --- |
| 状态 | 已接受（Accepted） |
| 日期 | 2026-10-05 |
| 里程碑 | D6-R2（LLM 解释层 + bom_selection 管道 + 队列派发） |
| 关联 | `core/selection.py`（引擎，ADR-0011 冻结） · `schemas/agent_outputs.BomSelectionAgentOutput` / `BomCandidate` · `docs/interface_contract.md` §4.2 · `agents/bom_selection.py` · `agents/verification.py` · `agents/admin.py` · `prompts/bom_selection_agent/v1/` |

## 背景

引擎（ADR-0011）已**权威**产出候选集 / `score` / `unit_price` / `lead_time_days` / `lifecycle_status` / 排序；R2 引入 LLM **解释层**，必须严格分离「引擎事实」与「LLM 文案」，且 LLM 不得改写任何引擎值。

## 决策

### 1. 字段权属（引擎权威 vs LLM 生成）

| `BomCandidate` / 顶层字段 | 权属 | 来源 |
| --- | --- | --- |
| `part_number` / `name` / `manufacturer` / `category` / `lifecycle_status` / `discontinued` | **引擎权威** | `Part` + `select()` |
| `score` | **引擎权威** | `total_score/100`（见 §2） |
| `unit_price` / `lead_time_days` | **引擎权威** | 有效源 `min(unit_price)` / `min(lead_time_days)` |
| 排序 / `recommended_part_id` | **引擎权威** | `select()` 排序，Top1 |
| `warnings` | **引擎权威** | `nrnd_source:*` |
| `request_params` | 引擎/criteria | 由 `Criteria` 生成 |
| `rationale` | **LLM 生成** | 每候选中文理由（覆盖交期/成本/生命周期/替代适用性） |
| `summary` | **LLM 生成** | 中文概述 |
| `replaces_part_id` | **LLM 建议** | 见 §3 |
| `source_refs` / `trace_refs` | LLM（建议，核验） | 默认空列表 |

**硬约束**：LLM 输出（`rationale`/`summary`/`replaces_part_id`）经合并后才组装 `BomSelectionAgentOutput`，并**再跑一次 Pydantic 校验**——引擎值**不经 LLM 往返**。

### 2. `score` 映射

引擎 `total_score`（0–100）→ schema `BomCandidate.score`（**float 0–1**）= `total_score / 100`（`PART-002 94.79` → `0.9479`）。

### 3. `replaces_part_id` 口径

- LLM **从管道提供的「被排除清单」中选取**明显可替代对象（**仅建议字段**）；
- 管道做**存在性核验**（`verify_references`，`type="part"`）；无合适对象则**省略**（`null`）；
- **落库必须经 `TraceLink`**（approve 时）——**登记 R3**（本轮不落库）。

### 4. 核验范围

合并结果中的**全部结构化引用** = 各 `BomCandidate.source_refs` + `replaces_part_id`，统一经 `agents/verification.verify_references`（复用 R2 核验器）。失败 → `reference_check_passed=False`、`status=failed`、`invalid_references` 落库。**未改 `verification.py`**（仅调用）。

### 5. 派发规则（`AgentRunAdmin` actions 按 `agent_name`）

| agent_name | approve | reject |
| --- | --- | --- |
| `requirement` | 现有 confirmation 流程（写 Requirement + TraceLink） | 通用 rejected（不写实体） |
| `bom_selection` | **返回消息「bom_selection 确认流程未实现（D6-R3）」**——不写实体、不 500 | 通用 rejected（同一行、绑定字段、不写实体） |
| 其他/未知 | **跳过 + 计数消息** | 同 |

**不得消费或改动 D5 遗留 `needs_review`（requirement，id 8–11）**。

### 6. `prompt_id` / `prompt_version`

照契约 §4.2：**`prompt.bom.selection` / `v1`**（`agents/bom_selection.py` 常量）。

### 7. 两阶段 AgentRun

`call_json` 落**一行**（成功 `needs_review` / 失败 `failed`）并回传 `CallResult.agent_run`；核验以 `filter(pk).update(...)` 更新**同一行**——**恰好 +1**。`fake` 后端（`agent_run is None`）**不落库、不核验更新**。

### 8. D13 登记

**criteria 输入表单页面本轮不做**，演示用 `management command run_bom_selection` 或契约端点 `POST /agents/bom-selection/run/`（登记 D13）。

## 后果

- 引擎事实与 LLM 文案彻底分离，`score`/价格/交期/排序不可被模型改写（合并后二次 Pydantic 校验兜底）。
- 队列派发按 `agent_name` 生效，D5 遗留 requirement 行语义不变；`bom_selection` approve 待 R3 实现。
- 留痕：字段权属、score 映射、replaces 口径、核验范围、派发规则、prompt 取值、两阶段写与 D13 登记均固化于本 ADR。
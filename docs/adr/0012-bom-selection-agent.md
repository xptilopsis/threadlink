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
## 附：`BomItem.substitute_group` 受控扩展（D6-R3）

**发现过程**：D6-R3 指令 §1.c 要求 approve 为候选 `BomItem` 落**共享 `substitute_group`**（`SG-SEL-<agent_run_id>`），但实现前核验发现 `Bom`/`BomItem` **均无该字段**（`grep substitute_group core/models.py` 零匹配）——模型不可表达，遂按纪律停下汇报。

**字典核对结论**：读 `docs/data_dictionary.md` §10 BomItem 字段表，**原无 `substitute_group`** → 属**有意受控扩展**（非 D2 实现遗漏）；逐字段比对模型与字典，**其余字段全部一致、无其它遗漏**。

**裁决依据（用户，2026-10-05）**：不违反架构边界——D1 分层规则「结构 / 计算强依赖走字段 / FK，跨域追溯走 TraceLink」；替代组是 **BOM 结构属性**（一个位置放哪些可互换料），本应落字段；`TraceLink(replaces)` 承载**事件性 / 追溯性**信息（谁替换了谁、因何 ECN），两者互补。D12 覆盖要求明文含「替代料组」、D13 演示「替代可行项」依赖组语义；选「不落字段」会让已冻结需求载体悬到 D7。先例已开：`d2-schema-freeze` 后第一次受控小改（`Part.lifecycle_status` 拆分，`core/0003` 纯 `AlterField`），本条为第二次、同流程处置。**边界是「禁止未经裁决的模型变更」，不是「禁止任何模型变更」。**

**变更范围**：`app=core`，字段 `BomItem.substitute_group`；迁移 **`core/migrations/0004_bomitem_substitute_group.py`**（**AddField-only**，`makemigrations core --dry-run` 输出仅 `+ Add field substitute_group to bomitem`）；字典 §10 补行 + 补录脚注；`BomItemAdmin.list_display` 体现该字段；`description` 同步。

**字段形态**：`CharField(max_length=64, blank=True, default="")`（对齐同域 `position` 风格，**非 null**、无唯一约束、无索引）。

**标签 / 版本定稿**：`substitute_group = "SG-SEL-<agent_run_id>"`；`Bom.version = "v0.1-sel-<agent_run_id>"`（避开 `(project, version)` 唯一约束）。
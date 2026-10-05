# ADR-0010：人工确认流程（approve / reject，D5-R3）

| 项 | 内容 |
| --- | --- |
| 状态 | 已接受（Accepted） |
| 日期 | 2026-10-05 |
| 里程碑 | D5-R3（Requirement Agent 人工确认 + 端到端） |
| 关联 | `agents/confirmation.py` · `agents/admin.py`（AgentRunAdmin actions） · `core/models.py`（Requirement / RequirementParam / RequirementStatus） · `traceability/models.py`（TraceLink） · `schemas/agent_outputs.RequirementAgentOutput` · ADR-0009 |

## 背景与范围

R2 产出的 `needs_review` AgentRun 携带需求卡（`RequirementAgentOutput`）；R3 提供**人工确认**：approve → 写实体（Requirement + RequirementParam + TraceLink）；reject → 不写实体。确认/拒绝动作是 R1 边界之外唯一的"写实体"路径。

## 决策

### 1. 四值状态迁移（AgentRunStatus）

```
needs_review --approve--> success
needs_review --reject --> rejected
failed / rejected / success  → 不可再处置（fail-loud）
```
（枚举四值 = `failed` / `needs_review` / `success` / `rejected`。）

### 2. 前置校验

`status == needs_review` **且** `reference_check_passed is True`；否则抛 `ConfirmationError`（消息含当前 `status`/`reference_check_passed`）。校验前 `refresh_from_db()`——**幂等以 DB 真实状态为准**（防脏内存对象绕过）。

### 3. 绑定规则

- **approve**：`Requirement.status=confirmed`（人工已确认）、`confirmed_by=user`、`confirmed_at=now`、`agent_run=run`；`AgentRun.status=success`、`confirmed_by/at`。
- **reject**：仅 `AgentRun.status=rejected` + `confirmed_by/at`；**不写任何实体**。

### 4. 事务与幂等

`approve` 全程 `transaction.atomic()`；逐卡创建 + 最后同行 `update`，**任一步失败整体回滚**（AgentRun 保持 `needs_review`）。对非 `needs_review` 行处置 → `ConfirmationError`（**不重复写实体**）。approve/reject **不产生新 AgentRun 行**（只 `update`），AgentRun 计数不变。

### 5. 字段映射表（`RequirementCard` → `Requirement` / `RequirementParam` / `TraceLink`）

| 卡片字段 | 落库位置 |
| --- | --- |
| `id?` / `code?` | **不使用**（编号器自动生成 `REQ-###`；卡片 code 若存在仅入报告） |
| `title` | `Requirement.title` |
| `content` | `Requirement.content` |
| `source_type` | `Requirement.source_type` |
| `priority` | `Requirement.priority`（同源 `Priority={low,medium,high}`） |
| `confidence` | `Requirement.confidence` |
| — | `Requirement.project` / `status=confirmed` / `agent_run` / `confirmed_by` / `confirmed_at` |
| `params[].name` / `operator` / `value_text` / `value_num` / `value_min` / `value_max` / `unit` / `is_mandatory` | `RequirementParam` **同名字段** |
| `source_refs[]` | 不入 `Requirement`；用于派生 TraceLink（见 §7） |

### 6. 卡片 `code` 处置

编号器自动生成 `REQ-###`（R8）；**卡片自带 `code` 不采用**（避免与编号器/唯一约束冲突），差异入报告。

### 7. TraceLink 形态

每张卡对**源 Document** 各写一条：`from_type="requirement", from_id=requirement.code` → `to_type="document", to_id=<源文档业务编号>`，`relation_type="derived_from"`（需求源于文档），`source="manual"`，`confirmed_by=created_by=user`，`agent_run=run`，`confidence=card.confidence`。
**源文档编号口径**：`AgentRun` 无 document FK，取自卡片 `source_refs` 中 `type=="document"` 的第一条 `id`（prompt 强制每卡带 document 引用）；缺失 → fail-loud。**卡内 `source_refs` 指向的其它目标边本轮不写，登记 D7+**。

### 8. 边界

- approve/reject **不产生新 AgentRun 行**（只更新）。
- rejected 输出文件沉淀（`prompts/*/failures/`，`human-rejected` 标注）按 `interface_contract` 约定 **D7 实现，本轮不做**。
- Admin：`AgentRunAdmin` 增 `approve_selected` / `reject_selected`（仅对 `needs_review` 生效，其余跳过并计数提示；异常以 admin message 呈现、不 500）；detail 仍只读、**不做内嵌按钮**（最小实现）。

### 9. 「修改后确认」延后声明

**D5 明确不做"编辑后再确认"**（`confirmed_output_json` 之类）：演示路径为「卡片 → 确认/拒绝」**全量处置**；编辑后再确认会让 R3 膨胀且收益不明。若后续真实需要，以**新字段 + 迁移**演进，登记 **D7+**。

## 后果

- 四值走全：approve→`success`、reject→`rejected`，与 `failed`/`needs_review` 共同覆盖 `AgentRunStatus`。
- 演示端到端闭环：邮件 → 卡片（`needs_review`）→ approve → `Requirement` 列表可见 + `TraceLink` 可回查。
- 留痕：状态迁移、绑定、幂等、回滚、字段映射、code 处置、TraceLink 口径与延后项均固化于本 ADR。
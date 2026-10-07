# ADR-0015：ECN 影响投影 + 正式应用（D11-R2）

| 项 | 内容 |
| --- | --- |
| 状态 | 已接受（Accepted） |
| 日期 | 2026-10-07 |
| 里程碑 | D11-R2（ECN 影响投影 + 正式应用） |
| 关联 | `docs/golden_tests.md` GT-ECN-001…006 · `core/ecn.py` · `core/admin.py::ECNAdmin` · `core/management/commands/{ecn_impact,ecn_apply}.py` · `tests/test_ecn_r2.py` |

## 背景

D11-R2 实现 ECN 两阶段：**分析**（投影影响面）与**正式应用**（人工确认后写回）。前置 HEAD=`c0b1236`。
`ECN` 模型字段仅 `ecn_number/title/description/change_type/status/effective_date/approved_by/...`——**无「替换 PART→PART」字段，亦无「被变更 part / 替换目标」字段**。

## 裁决记录（P1 / P2 / P3，含口径修正）

- **P1-A（被变更/替换目标载体）**：不新增 models 字段（P1-C 否决）。「被变更 part」= `TraceLink(ECN -affects-> bom_item)` 所指 `BomItem.part`；「替代料」= 该 part 的 `TraceLink(替代料 -replaces-> 被替代料)`（`PART-002 -replaces-> PART-001`，TL-039）；**应用 := `BomItem.part ← 替代料`**。
- **P2 口径修正**：初版「分析零写」作废 → 定稿 **分析为「全零写」**（既不写 `ECNImpact`、也不写 `affects` 边）；缺失的 `affects` 边（如 `TC-009`）由**应用**补建（确认态）。P2-b「分析写明细」作废。
- **P3-A（影响面来源）**：**影响面 = `ECNImpact` 行权威**；`docs/golden_tests.md` §2.3 的「由 TraceLink/BOM 图计算」规则**不采用**。

### P3 冲突与证据（§2.3 不采用的理由）

GT-ECN-001 期望 `test_case = TC-001, TC-009`，但 §2.3 计算规则**无法复现 `TC-009`**：

- `verified_by` 边仅 4 条：`REQ-001→TC-001`、`REQ-002→TC-003`、`REQ-003→TC-005`、`REQ-005→TC-006`。
- 被变更 part = `PART-001`（`ECN-001 -affects-> BI-001` → `BI-001.part`）；其需求 = `REQ-001`（`satisfied_by`），经 BOM 亦得 `REQ-001/002/003/004`（`implemented_by`）。
- 按 §2.3 计算的 test_case = `{TC-001, TC-003, TC-005}`（或仅 `TC-001`）——**含 `TC-003/005`、缺 `TC-009`**，与 GT-ECN-001 **不一致**。
- `TC-009` **仅**存在于 `ECNImpact` 行 `EI-005`（`affected_type=test_case`）。
- 若走「计算 + upsert `ECNImpact`」，会新增 `TC-003/005` 明细 → 违反「对 fixture 重算与 `EI-001…008` 无净变化」。

**结论**：影响面以 `ECNImpact` 为权威（fixtures `EI-001…008` 与 GT-ECN-001 逐条一致）。**自动推导（计算式影响面）/ agent 提案 → v2**；`ECNImpact` 的新增行承载「未确认/agent 提案」语义留 v2（NULL/来源语义预留）。

## 时序（§1 证据 + GT-ECN-005 冻原文）

**证据（fixtures `affects` 边）**：`TL-029…035` 全部 `source="agent"`、`created_by_id=NULL`、`agent_run=AR-004`、`confirmed_by=USER-005`（**已确认态 = 「应用后」**）。`ECN-001`（`approved`, `effective_date=2026-03-05`）/ `ECN-002`（`reviewing`, `null`）。`ECNImpact` 全表 8 行（`EI-001…008`）。

**GT-ECN-005 原文**：「为每个受影响对象写一条 `TraceLink(from=ECN, relation_type=affects, confirmed_by != null)`」；边界「**未确认时 `confirmed_by_id IS NULL`**」。

**定稿时序**：

- **分析**：读 `ECNImpact` → 解析 → 清单；**不写**（对 fixture 已确认边不触碰）。
- **应用**：a) 每个 `ECNImpact` 行**确保** `affects` 边——缺 → 建（`source="agent"` 对齐fixtures、`created_by`/`confirmed_by`=操作人、`confirmed_at`=now）；存在未确认 → 补确认；**已确认 → 不动**；b) 写回；c) 状态不迁移。

## 计算规则 / 数据来源

| 项 | 来源 |
| --- | --- |
| 影响面 | `ECNImpact.objects.filter(ecn=ecn)`（权威；`affected_type ∈ EntityType`） |
| 显示字段 | `resolve_entity(project, affected_type, affected_id)` → `str(obj)`；未解析 → `unresolved`（fail-soft） |
| 缺边提示 | `consistency`：`missing_affects_edge:<type>:<id>`（`ECN→*` `affects` 边缺失） |
| 生效门 | 状态 ∈ `{approved, implemented}`（GT-ECN-003）+ `effective_date` 非空且 ≤ `as_of_date`（GT-ECN-004：空 → `missing_effective_date`） |
| 替换目标 | `TraceLink(替代料 -replaces-> 被替代料)`；**无 → 不写回；多 → fail-loud** |
| 写回 | 仅 `affected_type="bom_item"` 的受影响项：`BomItem.part ← 替代料`；**非 `bom_item` 类不写实体** |

## 写回范围

- **唯一写路径** = `apply_ecn`（人工动作：Admin action / service / command）。
- 写**边**（`ECN→目标` `affects`）+ 写**正式实体**（`BomItem.part`）。
- **不写** `ECNImpact`（分析零写）；**不迁移** `ECN.status`。
- 事务内整体提交；中途失败**整体回滚、零残留**（测试 `test_apply_rollback_on_failure`）。

## 幂等（GT-ECN-005 / 006 落地）

- **005**：应用后每受影响对象**恰 1 条** `ECN→目标` `affects` 边（唯一约束 `uq_tracelink_edge` 全元组）；重复插入 → `IntegrityError`；未确认态（`NULL`）语义以构造测试保留。
- **006**：`ECNImpact` 三元组 `(ecn_id, affected_type, affected_id)` 为影响面权威；分析**零净变化**（重跑不改）；应用重跑 → **no-op**（`created_edges=0`、`confirmed_edges=0`、`rewritten=[]`）。

## 最小决策清单（GT 未覆盖）

1. **`ECN.status` 应用后不迁移**（保持 `approved`）——GT 未定义迁移；若需 `approved→implemented` 走后续裁决。
2. **无替换目标 → 不写回**（不报错）；**多替换目标 → fail-loud**（数据完整性信号）。
3. **应用需显式操作人**（`user is None` → `EcnApplyError`）。
4. `as_of_date` 默认 `date.today()`；调用方可显式传入（GT-ECN-002 基准日）。
5. **二次应用 = no-op**（幂等），非错误。

## fixture 债务记录（应用后达自洽终态）

| 债务 | 现状 | 应用后 |
| --- | --- | --- |
| `ECN-001` `affects` 边已确认（4 条，`USER-005`） | fixtures 呈「应用后」态 | 不动（幂等） |
| `EI-005` `TC-009` **缺 `affects` 边** | `consistency` 提示 | **应用补建**（确认态） |
| `BI-001.part` 仍 `PART-001`（未写回） | 未应用 | **应用写回 `PART-002`** |

→ 应用 `ECN-001` 后达**自洽终态**：`affects` 边 5 条齐、`BI-001.part=PART-002`；`ECNImpact` 始终 8 行。

## 已知局限

- 影响面**不自算**（依赖 `ECNImpact` 录入）；「自动推导影响面」留 v2。
- `ECNImpact` 无「未确认/来源」字段（NULL 语义预留 v2）。
- `ECN.status` 不发生 `implemented` 迁移（最小决策，见上）。

## E2E 状态声明

生产库执行 `apply_ecn(ECN-001, admin)` 后**进入「ECN-001 已应用」态**（`BI-001.part=PART-002`、`affects` 边 5 条、`TraceLink_total` 45→46）。R3 收口按需重引导（D7-R3 先例）。
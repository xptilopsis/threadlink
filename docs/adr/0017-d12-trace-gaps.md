# ADR-0017：D12-R2 追溯缺口补齐（四条裁决 + 默认决策）

| 项 | 内容 |
| --- | --- |
| 状态 | 已接受（Accepted） |
| 日期 | 2026-10-07 |
| 里程碑 | D12-R2（GT 覆盖缺口补齐：数据 + `chain.py` + 契约 + 测试） |
| 关联 | `docs/qa/2026-10-07-d12-gt-coverage-matrix.md`（R1 盘点）· `fixtures/demo_seed.json` · `scripts/validate_seed.py` · `traceability/chain.py` · `docs/interface_contract.md` §3.2 · GT-TRACE-002/004/005/006 |

## 背景

D12-R1 盘点出 **3 条冲突（C1/C2/C3）+ 若干缺口**。用户就 **C1/C2/C3 + TRACE-002** 给出四条裁决，并授权受控修改（fixtures evidence 补录、`chain.py` 证据聚合/断点 token/depth-direction/confirmed 过滤、契约 §3.2 标注与示例、条件性 schemas、既有测试更新）。本 ADR 记录裁决与默认决策。

## 裁决 C1：`trace_links` evidence 补录（破解 GT-TRACE-004「每节点 source_refs 非空」）

- **形态**：每条边**恰 1 条** evidence：`[{"type": "document", "id": "<DOC号>"}]`（SourceRef 最小形态，`locator`/`snippet` 省略）。
- **谓词（纯函数、确定性）**：边的 `from_type` 或 `to_type` == `requirement` → **`DOC-001`**（客户邮件，全链根）；否则 → **`DOC-002`**（PRD）。
- **实测结果**：39/39 全覆盖；**DOC-001 ×16**、**DOC-002 ×23**（逐条表见收口报告）。
- **硬约束**：`type ∈ ReferenceType` 且 `id` 可解析；evidence **只影响 `source_refs` 聚合**，**不得改变节点/边集合**（默认链 31/37 不漂移）。
- **守卫**：`scripts/validate_seed.py::check_trace_link_evidence`（长度=1 / `type` 白名单 / `id` 闭包）。
- **连带**：D7-R2 既有「根 `source_refs=[]` / 链 `source_refs` 全空」断言按新规则更新（见 §chain 变更）。

## 裁决 C2：断点 token（GT-TRACE-005）

- `missing` 采用 GT-005 字面 token：**`no_purchase_order`** / **`no_test_run`**。
- **触发=关系缺失**（判据）：根 `InventoryLot` **无 `sourced_from` 出边** → `no_purchase_order`；**无 `tested_by` 出边** → `no_test_run`。
- **dangling（边在、端点不可解析）** 保持 `unresolved_reference:<type>:<no>` **独立类别**（不并入 `no_*`）。
- **默认决策（判定范围）**：仅对**根批次（`inventory_lot`）**判定；GT-005 未限定查询类型 → **serial 与 lot 均适用**（记此默认）。
- 演示链 `SN-DEMO-001` 同时具备 `sourced_from`（TL-025）与 `tested_by`（TL-027/028）→ **无新增 token**（`missing=[]` 不漂移）。

## 裁决 C3：`depth` / `direction`（GT-TRACE-006）

- **先读 GT-006 原文**：`depth=0`→全链；`depth=2`→≤2 跳；`direction=backward`（默认）/`forward`；`depth` 负值 / `direction` 非法 → **400**（视图层）。**原文未定义截断与 `complete/missing` 的关系** → 按默认。
- **默认决策（截断语义）**：
  - `depth=0`（缺省）→ 全链，**与现行为逐字节一致**；
  - `depth=N>0` → 保留距根 ≤N 跳的节点 + **两端均在保留集内**的边；
  - **截断判定**：仅当保留边界存在指向被裁掉的更深节点的边（确实裁边）→ `complete=false` + `missing` 增 **`depth_truncated`**；链真实深度 ≤N（裁无可裁）→ 不截断、`complete` 正常；
  - 非法/负值 `depth`、非枚举 `direction` → **400**（视图层）。
- **⚠️ 停下列项（冲突上报，不自行取舍）**：GT-006 字面默认 `direction=backward`（「从批次回溯来源」）与现行**无向遍历**不一致——若按字面默认改为有向回溯，默认链将从 **31/37 缩水**，违反硬约束「无参数默认必须保持现状 31/37」。→ **本轮默认遍历保持无向（31/37 不漂移）**；`direction` 仅在**显式指定**时生效（`forward`/`backward` 有向变体），该偏差上报待裁决。

## 裁决 TRACE-002：`confirmed` 过滤

- **仅 `confirmed_by` 非空边入链**（GT-002 / 契约 §2.5 `confirmed_by_id IS NULL` 的链不进入结果）。
- 实测 fixtures 39 条 **`confirmed_by_id` 全非空（NULL=0）** → 过滤后默认链 **零漂移（31/37）**。
- **过滤逻辑必须实现**并以构造测试锁定（ORM 建未确认边 → 排除；确认后 → 纳入）。

## 登记项关账

- **D4 收口报告延后项 ⑥**（`depth`/`direction` 未实现、v1 忽略）：**本轮实现**（`depth` 完整；`direction` 除默认语义外实现），据此**关账**（`direction` 默认偏差另记）。

## 影响面

| 文件 | 变更 |
| --- | --- |
| `fixtures/demo_seed.json` | 39 条 `trace_links` 增 `evidence`（本 ADR §C1） |
| `scripts/validate_seed.py` | 增 `check_trace_link_evidence` |
| `traceability/chain.py` | `source_refs` 含根聚合、`no_*` token、`depth`/`direction`、`confirmed` 过滤 |
| `docs/interface_contract.md` §3.2 | `depth`/`direction` 标注「v1 忽略」→「已实现」+ 截断一句话；示例刷新 |
| 既有测试 | D4-R3 / D7-R2 中与「空 `source_refs`」相关断言更新 |
## D12-R3 增补：`direction` 语义 + `TRACE-003` 输入规范化

### 1. `direction`（GT-006；默认冲突按裁决以 31/37 优先）

**GT-TRACE-006 冻原文（逐字）**：

> - `depth = 0` → 全链路
> - `depth = 2` → 距起点 ≤2 跳
> - `direction = backward`（默认）→ 从批次回溯来源
> - `direction = forward` → 从批次正向展开受影响对象
> - **边界**：`depth` 为负值 → `400`；`direction` 非法值 → `400`

- **默认冲突（登记、不回问）**：GT-006 字面默认 `backward`；若据此把默认设为**单向回溯**，`/trace/serial/SN-DEMO-001/` 默认链将从 **31 节点 / 37 边** 缩水 → 违反「默认不漂移」硬约束及 GT-TRACE-001/003/004 与 D4/D7 既有断言。**默认保持双向（全链，31/37）**；`direction` 仅**显式指定**时生效。
- **最小决策（方向极性）**：`forward` = 沿 `from→to` 顺向可达；`backward` = 逆向可达；均自 root BFS，受 `MAX_DEPTH` 与 `confirmed` 过滤（有向子图）。
- **与 `depth` 组合**：方向过滤在**遍历层**、深度截断在**返回层**（先按方向 BFS，再按 `depth` 裁剪节点/边）。
- 非法/负值 `depth`、非枚举 `direction` → HTTP `400`（视图层）。

### 2. `TRACE-003` 输入规范化（边界2 收口）

**GT-TRACE-003 边界2 冻原文（逐字）**：

> **边界 2**：大小写/空格差异（`" sn-demo-001 "`）→ 规范化后按存在/不存在分别处理，不误报编造

- 规范化口径：`sn.strip()` + 匹配用 `serial_number__iexact`（大小写不敏感）；**命中后以库中规范编号**（`lots[0].serial_number`）**建链并回显 `root`**（因 `resolve_entity` 为大小写敏感精确匹配）；未命中时 `root` = `strip` 原文；存储 / 唯一性 / 多命中守卫（409）口径不变。
- 实施位置：`traceability/views.py::serial_trace`（**查询入口层**）。`agents/traceability.py` 的 run 入口属 D12 禁改边界（`agents/`）→ 规范化**未**覆盖该入口，登记为剩余缺口（去向 D13/D14）。

### 3. 影响面增补

| 文件 | 变更 |
| --- | --- |
| `traceability/views.py` | 输入 `strip` + `__iexact` 匹配；docstring |
| `docs/interface_contract.md` §3.2 | `direction` 默认「`backward`」→「双向（全链）＋显式按方向过滤」；输入规范化注记 |
| `tests/golden/test_trace_query.py` | `forward`+`depth` 组合、规范化变体（小写 / 空格 / 混合）→ 31/37 |
# ThreadLink Golden Tests 冻结清单（D1）

> 里程碑：**D1**（只冻结测试清单，**不编写测试代码**；D12 落地实现）。
> 状态：**已冻结（Frozen）**。本文件为关键计算的验收基线，变更须走变更流程并同步 `docs/PRD.md`、`docs/milestone.md`。
> 关联文档：`docs/PRD.md`（§7 验收标准）、`docs/demonstration_project_requirements.md`（§三 演示场景）、`docs/data_dictionary.md`、`docs/er_diagram.md`、`docs/interface_contract.md`、`schemas/agent_outputs.py`。

---

## 0. 约束与约定

| 项 | 约定 |
| --- | --- |
| 本阶段交付 | 仅**测试清单**（用例定义、输入、期望、边界）。**不写任何测试代码** |
| 实现阶段 | D12：按本清单实现 golden tests，映射见 §7 |
| 用例格式 | 每条用例含 **Given / When / Then**，并显式列出 **输入 / 期望 / 边界** |
| ID 命名 | `GT-<域>-<三位序号>`；域：`BOM` / `KIT` / `ECN` / `JSON` / `TRACE` |
| 时间基准 | 所有涉及"生效日"的计算必须注入**固定基准日**（`as_of_date`），禁止依赖系统当前时间，保证测试确定性 |
| 货币/数量 | 使用 `Decimal`，金额以字符串传输（如 `"42.50"`）；禁止浮点误差断言 |
| 术语 | 代码/实体名保持英文（`BomItem`/`qty_available`/`effective_date`），说明用中文 |
| 运行环境 | golden tests **默认在 SQLite 运行**（R5）；不得依赖 PostgreSQL / pgvector；PostgreSQL 仅为部署目标 |

---

## 1. 目的与范围

本清单冻结下列**五类关键计算**的可判定行为：

1. **BOM 展开**（多层父子、工单用量放大）
2. **齐套 / 缺料**（库存批次部分占用、在途 PO、替代料、风险料）
3. **ECN 影响**（生效日期边界、影响面圈定、固化）
4. **LLM JSON 校验**（非法 JSON、缺字段、幻觉 ID）
5. **TraceLink 反查**（序列号驱动全链路、查不到返回空链）

范围外：CRUD、UI、权限、只读约束（另见 `docs/PRD.md` AC-008）、Git 解析细节。

---

## 2. 计算口径与不变量（冻结）

> 以下口径为测试判定的**唯一依据**；实现若偏离，视为缺陷。

### 2.1 BOM 展开

- `BomItem` 以 `parent_item_id` 自引用成森林，`parent_item_id IS NULL` 为顶层节点。
- 单个节点的**累计用量** = 根到该节点路径上各 `quantity` 的乘积；工单场景再乘以 `WorkOrder.quantity`。
- 同一 `part_id` 经多条路径出现时，**汇总求和**。
- 输出顺序：按 `depth` 升序；同层按 `position`、`ref_des` 稳定排序（保证结果可复现）。
- 仅展开 `Bom.status ∈ {released, draft}` 的 BOM；`obsolete` 默认拒绝展开（可配置）。**`draft` BOM 展开须附 `warning = "draft_bom"`**（口径与 GT-BOM-005 边界、GT-ECN 系列无关，统一按此判定）。
- 环形引用（父链出现重复 `BomItem.id`）→ 抛 `cyclic_bom_structure`，**不返回部分结果**。
- 孤儿节点（`part_id` 指向不存在的 `Part`）→ 抛 `orphan_bom_item`。
- **ECN 影响分析与正式应用（两阶段，R6）**：当 `ECN.status ∈ {approved, implemented}` 且 `effective_date ≤ as_of_date`（`effective_date` 为空视为未生效）时——**影响分析**在计算视图中投影受影响 `BomItem` 的 `part_id` 将被替换为替代料，**不写回正式实体**（仅 `ECNImpact` 记录）；**ECN 正式应用**须经人工确认，确认后更新正式 `BomItem.part_id` 并写 `TraceLink`（`ECN→目标, affects`，含 `confirmed_by`/`confirmed_at`）留痕。空 `effective_date` **不得生效**。系统**不存在「自动改 BOM」（无人工确认的静默写入）**，但**存在**「ECN 生效经人工确认后的正式 BOM 变更」。

### 2.2 齐套 / 缺料

- 需求量 = §2.1 展开用量。
- 可用量 = `Σ InventoryLot.qty_available`，过滤：`part_id` 匹配、`status = available`（`allocated` / `consumed` / `scrapped` **不计入**可用）。
- 在途量 = `Σ PO 明细量`，过滤：`PO.status ∈ {open, partial}`；明细来源为 `TraceLink(from=Part, relation_type=ordered_by, to=PurchaseOrder)`，数量取 `metadata.quantity`。
- 判定：`可用量 ≥ 需求量` → 齐套；否则 `shortage_qty = 需求量 − 可用量`。
- 缺料行字段：`part_id`、`required_qty`、`available_qty`、`shortage_qty`、`in_transit_qty`、`latest_arrival_date`、`insufficient`、`alternatives[]`、`risk_flags[]`。
- **最晚到货日**：按 `expected_date` 升序累加在途量，取使累计量 `≥ shortage_qty` 的批次日；若全部在途仍不足，取最后批次日并置 `insufficient = true`；无在途则 `latest_arrival_date = null`。
- **替代可行项**：对缺料 `part`，查 `TraceLink(from=替代料 Part, relation_type=replaces, to=被替代料 Part)`；若替代料 `available + in_transit ≥ shortage_qty`，则列入 `alternatives` 并给出替代料最晚到货日。
- **风险标记**：`lifecycle_status ∈ {eol, obsolete}` → `discontinued`；供应商 `lead_time_days > 60` → `long_lead_time`；`is_critical = true` 且缺料 → `critical_shortage`。
- 全部满足 → 缺料列表为空。

### 2.3 ECN 影响

- 仅 `ECN.status ∈ {approved, implemented}` 参与"生效影响"；`draft / reviewing / rejected` **不产生生效影响**。
- 生效边界：`as_of_date == effective_date` → **生效**；`as_of_date = effective_date − 1 day` → **不生效**。
- 影响面：
  - `bom_item`：所有使用"被变更 `part`"的 `BomItem`。
  - `inventory_lot`：所有 `part_id ∈ 被变更 part` 的 `InventoryLot`。
  - `purchase_order`：`TraceLink(Part→PO, ordered_by)` 指向被变更 part 且 `PO.status ∈ {open, partial}`。
  - `test_case`：经 `TraceLink(Requirement→TestCase, verified_by)` 关联到受影响 `part` / `BomItem` 的需求所挂接的测试用例。
- 影响明细写入 `ECNImpact`（可重算，**分析投影不写回** `BomItem`）；人工确认后另写 `TraceLink(ECN→目标, affects)` 作为审计关联，并按 §2.1 更新正式 `BomItem.part_id`。
- 幂等：同一 `(ecn_id, affected_type, affected_id)` 重算不产生重复记录。

### 2.4 LLM JSON 校验

- 唯一入口：`schemas.agent_outputs.validate_agent_output(agent_name, payload)`。
- `payload` 可为 `dict` 或原始字符串；字符串先 `json.loads`，失败即校验失败。
- Pydantic 模型 `extra="forbid"`：未知字段、缺必填、类型/范围不符、枚举越界 → `ValidationError`。
- **schema 校验 ≠ 防幻觉**：schema 通过后，业务层必须核验 `SourceRef.id` / `recommended_part_id` / `TraceNode.node_id` 等引用的**实体存在性**（按 `(project_id, entity_type, 业务编号)` 反解，R2）；失败 → 写入 `invalid_references`，不得落库为正式数据。
- 失败语义：schema 失败 → `AgentRun.status = "failed"`、`output_schema_valid = false`、`output_json = null`、`error` 为摘要，HTTP `422`；引用核验失败 → `reference_check_passed = false`（独立于 `output_schema_valid`）、`invalid_references = [{entity_type, entity_id, reason}]`（`reason ∈ {not_found|wrong_project|unknown_type}`）、同样 `status = "failed"`、**不进入人工确认队列**；两种情况**均保留输入、引用与 `output_json`**。
- `AgentRun.status` 为**四值**枚举：`failed` / `needs_review` / `success` / `rejected`（绑定规则：`success`/`rejected` ⟹ `confirmed_by`/`confirmed_at` 必填，`failed`/`needs_review` ⟹ 二者必须为 NULL；见 R1 与 `docs/data_dictionary.md` §22）。

### 2.5 TraceLink 反查

- 起点：按 `serial_number` + `project_id` 定位 `InventoryLot`。
- 遍历 `TraceLink`；默认 `direction = backward`、`depth = 0`（全链路）。
- 每个 `TraceNode` 必须带 `source_refs`；`confirmed_by_id IS NULL` 的链**不进入结果**。
- 链路断点写入 `missing`（如 `"no_purchase_order"`, `"no_test_run"`）。
- **查不到序列号 → `found=false` 空链，禁止编造**：`found = false`、`complete = false`、`nodes = []`、`edges = []`、`missing = ["serial_not_found"]`、`warnings` 含 `"serial_not_found"`；先查库判定 `found`，未命中**短路返回、不调用 LLM**。
- **根实体存在但无 TraceLink**：`found = true`、`nodes` 含根节点自身、`warnings` 含 `"未建立追溯链"`（**不是空链**）。
- 结果去重、稳定排序、防环。

---

## 3. 基准数据集（fixture 基线）

测试使用**固定 fixture**（可基于 `fixtures/demo_seed.json` 扩展为最小可控集）。关键基线：

| 实体 | 关键值 |
| --- | --- |
| `BOM-001` | `status = released`；16 个 `BomItem`，其中顶层 4 个（`BI-001`~`BI-004`），二级 11 个（`BI-005`~`BI-015`），三级 1 个（`BI-016`，父为 `BI-006`） |
| `BI-001` | `part_id = PART-001`, `quantity = 1`, `is_critical = true`；子项 `BI-005/006/009/010` |
| `BI-002` | `part_id = PART-004`；子项 `BI-012/013/015` |
| `BI-003` | `part_id = PART-005`；子项 `BI-007/008/011/014` |
| `BI-004` | `part_id = PART-006`, `quantity = 2`；无子项 |
| `BI-005` | 叶子节点（无子项），用于叶子判定用例（GT-BOM-002） |
| `BI-016` | `parent_item_id = BI-006`, `part_id = PART-009`, `quantity = 2`；三级嵌套用例（GT-BOM-007） |
| `WO-001` | `bom_id = BOM-001`, `quantity = 10`, `due_date = 2026-04-30` |
| `LOT-DCDC-001` | `PART-001`, `quantity = 100`, `qty_available = 80`, `status = available`（**部分占用**） |
| `LOT-ENCL-001` | `PART-004`, `quantity = 50`, `qty_available = 40`, `status = available`（**部分占用**） |
| `SN-DEMO-001` | `PART-002`, `qty_available = 1`, `status = allocated`（业务编号 = `serial_number`） |
| `PO-001` | `PART-001`, `status = open`, `expected_date = 2026-03-01`, `metadata.quantity = 100` |
| `PO-002` | `PART-002`, `status = open`, `expected_date = 2026-03-20`, `metadata.quantity = 50` |
| `PO-005` | `PART-006`, `status = partial`, `expected_date = 2026-03-06`, `metadata.quantity = 200` |
| `ECN-001` | `status = approved`, `effective_date = 2026-03-05`, 替换 `PART-001 → PART-002` |
| `ECN-002` | `status = reviewing`, `effective_date = null` |
| `PART-017` | `lifecycle_status = obsolete` |
| `PART-018` | `supplier lead_time_days = 90`（长交期） |
| 替代关系 | `TL-039`：`PART-002 replaces PART-001` |
| 选型关键参数（补齐后） | `PART-001`/`PART-002` 补 `ip_rating = IP65`；`PART-018` 补 `input_voltage 9-36V` / `rated_current 5A` / `operating_temp -40~85°C` / `ip_rating IP65` / `unit_cost 88.00`；`PART-011` 补电压/温度/IP/成本（`rated_current = 3A` 不足 → 阈值排除）；`PART-012` 补电压/电流/IP/成本（`operating_temp -20~70°C` 不足 → 阈值排除） |
| 选型有效渠道（排除 `eol`） | `PART-001` = 2（`SP-001`/`SP-011`；`SP-003` `eol` 排除）、`PART-002` = 3（`SP-002`/`SP-012`/`SP-013`）、`PART-018` = 1（`SP-005`）；`SP-007`（`nrnd`）保留 + `warning` |

---

## 4. 覆盖矩阵（强制项 → 用例）

| 强制覆盖项 | 对应用例 |
| --- | --- |
| 多层 BOM 父子展开 | GT-BOM-001、GT-BOM-002、GT-BOM-003、GT-BOM-004、GT-BOM-007 |
| 选型评分 Top3 排序（规则 v1） | GT-BOM-008、GT-BOM-009 |
| 替代料组 | GT-KIT-004、GT-KIT-008 |
| 库存批次部分占用 | GT-KIT-002、GT-KIT-007 |
| 在途 PO 最晚到货日 | GT-KIT-003、GT-KIT-008 |
| ECN 生效日期前后 | GT-ECN-001、GT-ECN-002、GT-ECN-004 |
| 停产料、长交期料 | GT-BOM-006、GT-KIT-005、GT-KIT-006 |
| LLM 非法 JSON / 缺字段 / 幻觉 ID | GT-JSON-002、GT-JSON-003、GT-JSON-005 |
| 序列号查不到返回空链（不编造） | GT-TRACE-003 |

---

## 5. 测试清单

### 5.1 BOM 展开（GT-BOM-*）

#### GT-BOM-001 顶层节点直接展开
- **Given** BOM-001 已加载，存在 4 个 `parent_item_id IS NULL` 的顶层 `BomItem`
- **When** 调用 `expand_bom(BOM-001, quantity=1)`
- **Then** 返回顶层 4 行：`BI-001(PART-001×1)`、`BI-002(PART-004×1)`、`BI-003(PART-005×1)`、`BI-004(PART-006×2)`
- **输入**：`bom_id=BOM-001`, `quantity=1`
- **期望**：`len(rows) == 4`；每行 `depth == 0`；`BI-004.required_qty == 2`
- **边界**：BOM 无任何 `BomItem` → 返回空列表（非报错）

#### GT-BOM-002 叶子节点判定（BI-005 为叶子）
- **Given** `BI-001` 存在子项 `BI-005/006/009/010`；`BI-005` 为叶子（无任何子项）
- **When** 展开 BOM-001 且保留层级
- **Then** `BI-005` 的 `depth == 1`、`parent_item_id == BI-001`，且结果中**不存在** `parent_item_id == BI-005` 的行
- **输入**：`bom_id=BOM-001`, `include_hierarchy=true`
- **期望**：`BI-005(PART-007×4)`、`BI-006(PART-008×10)`、`BI-009(PART-011×2)`、`BI-010(PART-012×2)`；`BI-001` 出现在这 4 行之前；`BI-005.children == []`
- **边界**：非叶子节点（如 `BI-001`）`children` 非空；叶子判定与 `depth` 无关（深层节点仍可为叶子）

#### GT-BOM-003 工单数量放大（用量连乘）
- **Given** `WO-001.quantity = 10`，`BI-004.quantity = 2`，`BI-008.quantity = 12`
- **When** 按工单展开 `expand_bom_for_work_order(WO-001)`
- **Then** 每行需求量为 `路径连乘 × 工单数量`
- **输入**：`work_order_id=WO-001`
- **期望**：`PART-006` 需求 = `2 × 10 = 20`；`PART-010` 需求 = `12 × 10 = 120`；`PART-001` 需求 = `1 × 10 = 10`
- **边界**：`quantity = 0` → 全部需求为 0；`quantity` 为小数（如 `0.5`）→ 结果保留 4 位小数，无浮点漂移

#### GT-BOM-004 同一物料多路径汇总
- **Given** 同一 `part_id` 经两条不同父路径出现（构造 fixture）
- **When** 展开并按 `part_id` 汇总
- **Then** 该 `part_id` 需求 = 两条路径用量之和
- **输入**：两条路径用量分别为 `3` 与 `5`
- **期望**：汇总用量 = `8`；明细中仍保留两条来源路径
- **边界**：同一路径重复出现相同 `part_id` → 视为两行分别累加，不自动去重

#### GT-BOM-005 非发布 BOM 展开限制
- **Given** 构造 `BOM-002.status = obsolete`
- **When** 展开 `BOM-002`
- **Then** 依据配置拒绝或告警
- **输入**：`bom_id=BOM-002`, 默认配置
- **期望**：抛 `bom_not_releasable`（或按配置返回空并附 `warning`）
- **边界**：`status = draft` → 允许展开并附 `warning = "draft_bom"`

#### GT-BOM-006 停产料 / 替代料在展开中的标记
- **Given** 构造 BOM 含 `PART-017`（`obsolete`），且存在 `PART-002 replaces PART-001`
- **When** 展开 BOM
- **Then** 停产物料行标记 `risk_flags` 含 `discontinued`；替代料关系不影响展开用量（仅作为齐套替代来源）
- **输入**：`bom_id` 指向含停产物料的 BOM
- **期望**：停产物料行 `lifecycle_status == "obsolete"` 且 `risk_flags` 含 `discontinued`
- **边界**：`nrnd` 物料 → 标记 `nrnd` 但不阻断

---

#### GT-BOM-007 三层嵌套展开（depth 递增 + 累计用量连乘）
- **Given** fixture 含三层链 `BI-001`（顶层，`quantity = 1`）→ `BI-006`（`depth 1`，`quantity = 10`）→ `BI-016`（`depth 2`，`quantity = 2`）
- **When** 展开 BOM-001 且保留层级
- **Then** `depth` 逐层递增（`BI-001 = 0`、`BI-006 = 1`、`BI-016 = 2`），`BI-016` 累计用量 = 路径连乘 = `1 × 10 × 2 = 20`
- **输入**：`bom_id=BOM-001`, `include_hierarchy=true`
- **期望**：`BI-016(PART-009×20)`、`depth == 2`、`parent_item_id == BI-006`，且出现在 `BI-006` 之后
- **边界**：再挂一层（构造 `BI-017` 起）→ `depth == 3` 且累计用量继续按路径连乘；父链重复出现同一 `BomItem.id` → 抛 `cyclic_bom_structure`

---

#### GT-BOM-008 选型评分 Top3 排序（规则 `rules/bom_scoring.v1.json` v1）
- **Given** 规则文件 `rules/bom_scoring.v1.json`（`status = frozen`，v1）与一组**通过阶段 1 硬过滤**的构造候选（最小可控集，仅用于锁定排序口径）：
  - `C1`：`unit_price = 10`、`lead_time_days = 5`、可供供应商数 = 1
  - `C2`：`unit_price = 20`、`lead_time_days = 5`、可供供应商数 = 3
  - `C3`：`unit_price = 20`、`lead_time_days = 10`、可供供应商数 = 2
- **When** 按规则执行阶段 2（`min-max` 归一化 + 加权）并取 Top3
- **Then** 归一化与加权结果确定，排序为 `C1 > C2 > C3`
- **输入**：上述构造候选（`cost_max` 未提供）
- **期望**：
  - `cost`（lower_better，min=10 / max=20）：`C1=1.0`、`C2=0.0`、`C3=0.0`
  - `lead_time`（lower_better，min=5 / max=10）：`C1=1.0`、`C2=1.0`、`C3=0.0`
  - `multi_source`（higher_better，min=1 / max=3）：`C1=0.0`、`C2=1.0`、`C3=0.5`
  - 总分（`100 × (0.5·cost + 0.3·lead_time + 0.2·multi_source)`）：`C1 = 80`、`C2 = 50`、`C3 = 10`
- **边界**：
  - 总分相同 → 先按 `cost` 升序，再按 `part_number` 升序
  - 某维度 `max == min` → 该维度计 `1.0`
  - 停产料（`lifecycle_status = discontinued`）在阶段 1 排除，**不进入候选**，并给出 `replaces_part_id` 与替代理由
  - `nrnd` 渠道：保留为有效渠道并附 `warning`、不降权（`eol` 渠道排除）；可用构造 `SupplierPart` 测该 `warning`（GT-BOM-009 渠道级口径引用本边界）
- **备注**：本用例以构造最小集锁定排序口径（与 fixture 无关）。冻结权重下 `80/50/10` 经复核与两阶段公式一致。演示 fixture 的真实演算基线见 GT-BOM-009（OI-6 已决议）。

#### GT-BOM-009 AC-004 演示 fixture 全表演算基线（OI-6 处置后）
- **Given** 已补齐关键参数的演示 fixture（`fixtures/demo_seed.json`）与冻结规则 `rules/bom_scoring.v1.json`（v1）
- **When** 对全部 20 个 `Part` 执行阶段 1 硬过滤（顺序：`lifecycle → param_completeness → param_threshold → cost_max`），再对通过者执行阶段 2 评分并取 Top3
- **Then** 阶段 1 通过 **3** 个（`PART-001`/`PART-002`/`PART-018`），满足 AC-004「候选 ≥ 3」；Top3 分数互不相同
- **输入**：全表 `Part`（`cost_max` 未启用）；渠道口径见 §3
- **期望**：
  - 通过者评分（有效渠道 min 单价 / 有效渠道 min 交期 / 有效渠道数）：
    - `PART-002`：`45.00` / `14` / `3` → 总分 **94.79**（Top1）
    - `PART-001`：`40.00` / `21` / `2` → 总分 **87.24**（Top2）
    - `PART-018`：`88.00` / `90` / `1` → 总分 **0.00**（Top3）
  - 排序：`PART-002 > PART-001 > PART-018`
  - 排除 **17** 个，三类原因齐全：
    - `lifecycle:obsolete`（1）：`PART-017`
    - `missing_param`（14）：`PART-003/004/005/006/007/008/009/010/013/014/015/016/019/020`
    - 阈值类（2）：`PART-011`（`current_below_min`，`rated_current = 3 < 5`）、`PART-012`（`temp_out_of_range`，`-20~70°C` 不覆盖 `-40~85°C`）
  - 渠道级：`SP-003`（`eol`）计算 `PART-001` 时**排除**（有效源 = `SP-001` + `SP-011` = 2）；`nrnd` 渠道保留为规则层行为（保留渠道 + `warning`，不降权）——本基线中其归属物料（`PART-004`）因 `missing_param` 被排除、不进入评分，故基线不体现该 `warning`（`SP-007`；可测化构造口径见 GT-BOM-008 边界）
- **边界**：
  - 权重/公式核对：构造集 `C1/C2/C3` 的 `80/50/10` 与冻结公式一致（GT-BOM-008）
  - Top3 分数并列 → 按 `cost` 升序、再按 `part_number` 升序（本基线无并列）
  - 若再次修改 fixture 物料参数 → 必须重跑本基线并更新，**不得边跑边调数据凑结果**
- **备注**：OI-6 处置 = 补齐 fixture 关键参数（人工放行修数据），修数据前阶段 1 通过者为 **0**；详见 ADR-0005。

---

### 5.2 工单齐套 / 缺料（GT-KIT-*）

#### GT-KIT-001 齐套全部满足
- **Given** 构造工单需求全部可由 `available` 库存覆盖
- **When** 执行 `analyze_kitting(WO)`
- **Then** `shortages == []`，`ready == true`
- **输入**：需求量 10、可用库存 10
- **期望**：无缺料行
- **边界**：可用量恰好等于需求量 → 齐套（含边界）

#### GT-KIT-002 库存批次部分占用（使用 qty_available）
- **Given** `LOT-DCDC-001`：`quantity = 100`、`qty_available = 80`；某物料需求 90
- **When** 执行齐套
- **Then** 可用量取 **80**（而非 100），缺口 = `90 − 80 = 10`
- **输入**：需求 90，批次 `LOT-DCDC-001`
- **期望**：`available_qty == 80`、`shortage_qty == 10`
- **边界**：`status = allocated` 的批次（如 `SN-DEMO-001`）→ **不计入**可用量，`available_qty == 0`

#### GT-KIT-003 在途 PO 最晚到货日
- **Given** 某物料 `shortage_qty = 30`；在途 `PO-A(expected=2026-03-01, qty=20)`、`PO-B(expected=2026-03-20, qty=50)`，均 `status = open`
- **When** 计算最晚到货日
- **Then** 累计 `20 < 30`，再加 `PO-B` 后 `70 ≥ 30` → 最晚到货日 = `2026-03-20`
- **输入**：见上
- **期望**：`latest_arrival_date == 2026-03-20`、`in_transit_qty == 70`、`insufficient == false`
- **边界 1**：在途总量不足 → 取最后批次日且 `insufficient == true`
- **边界 2**：`PO.status = received / closed / cancelled` → **不计入**在途
- **边界 3**：无在途 → `latest_arrival_date == null`

#### GT-KIT-004 替代料组可行性
- **Given** 缺料物料为 `PART-001`，`PART-002 replaces PART-001`；`PART-002` 可用 1、在途 50
- **When** 计算替代可行项
- **Then** 替代料 `PART-002` 覆盖缺口则列入 `alternatives`
- **输入**：`PART-001` 缺口 9；`PART-002` 可用+在途 = 51
- **期望**：`alternatives` 含 `{part_id: PART-002, available_qty: 1, in_transit_qty: 50, shortest_arrival_date: 2026-03-20}`；`replaces` 方向为 `替代料 → 被替代料`
- **边界 1**：替代料覆盖不足 → 仍列出但标 `sufficient = false`
- **边界 2**：仅统计 `status = active` 的替代料；`obsolete` 替代料 → 不列入

#### GT-KIT-005 停产料风险
- **Given** BOM 展开含 `PART-017`（`obsolete`）且缺料
- **When** 执行齐套
- **Then** 缺料行 `risk_flags` 含 `discontinued`
- **输入**：`PART-017` 需求 10、可用 0、无在途
- **期望**：`risk_flags` 含 `discontinued`，并建议替代
- **边界**：停产物料有库存可满足 → 仍标记 `discontinued` 但不计入缺料

#### GT-KIT-006 长交期料风险
- **Given** `PART-018` 供应商 `lead_time_days = 90`（> 60）
- **When** 执行齐套 / 选型
- **Then** 标记 `long_lead_time`
- **输入**：`PART-018` 缺料
- **期望**：`risk_flags` 含 `long_lead_time`；`recommended` 中该料 `rationale` 含长交期提示
- **边界**：`lead_time_days = 60` → **不**标记（阈值 `> 60` 严格）

#### GT-KIT-007 缺料清单全字段与关键件标记
- **Given** 存在缺料且物料 `is_critical = true`
- **When** 执行齐套
- **Then** 每条缺料含全部字段，且关键件带 `critical_shortage`
- **输入**：`PART-001`（`is_critical = true`）缺料
- **期望**：字段齐全：`part_id`、`required_qty`、`available_qty`、`shortage_qty`、`in_transit_qty`、`latest_arrival_date`、`insufficient`、`alternatives`、`risk_flags`；含 `critical_shortage`
- **边界**：非关键件缺料 → 无 `critical_shortage`

#### GT-KIT-008 无在途且不可替代的硬缺料
- **Given** 物料缺料、无在途 PO、无可用替代料
- **When** 执行齐套
- **Then** 缺口行 `latest_arrival_date == null`、`alternatives == []`、`insufficient == true`
- **输入**：需求 10、可用 0、无在途、无 `replaces`
- **期望**：满足上述全部断言
- **边界**：有在途但总量为 0（`metadata.quantity = 0`）→ 等价无在途

---

### 5.3 ECN 影响（GT-ECN-*）

#### GT-ECN-001 ECN-001 影响面圈定
- **Given** `ECN-001`（`approved`, `effective_date=2026-03-05`，替换 `PART-001→PART-002`），`as_of_date = 2026-03-05`
- **When** 执行 `analyze_ecn_impact(ECN-001)`
- **Then** 影响面含 BOM 节点、库存批次、在途 PO、测试用例
- **输入**：`as_of_date = 2026-03-05`
- **期望**：
  - `bom_item`：`BI-001`
  - `inventory_lot`：`LOT-DCDC-001`（`PART-001`）
  - `purchase_order`：`PO-001`（`open`, `PART-001`）
  - `test_case`：`TC-001`、`TC-009`（经需求/BOM 关联）
- **边界**：`PO-003`（`received`）→ 不计入"在途 PO"影响

#### GT-ECN-002 生效日期前后边界 + 正式应用两阶段
- **Given** `ECN-001.effective_date = 2026-03-05`，替换 `PART-001 → PART-002`
- **When** 分别在 `as_of_date = 2026-03-04` 与 `2026-03-05` 执行影响分析 / 展开；随后对生效日结果执行**人工确认正式应用**
- **Then** 严格区分两阶段（不得混同）：
  - **(a) 影响分析（计算视图）**：生效判断正确，投影出替换目标，但**不写回**正式 `BomItem`
  - **(b) 正式应用（人工确认后）**：`BomItem.part_id` 真正更新为替代料，并留下 `TraceLink` 审计
- **输入**：两个基准日；确认人 `USER-005`
- **期望**：
  - `as_of_date = 2026-03-04` → 影响/展开沿用 `PART-001`，`effective = false`
  - `as_of_date = 2026-03-05`（a）→ 影响分析输出将 `PART-002` 列为替换目标，`effective = true`，且该 `BomItem`（`BI-001`）**未被修改**（`part_id` 仍为 `PART-001`）
  - `as_of_date = 2026-03-05`（b）→ 人工确认应用后 `BomItem.part_id == 'PART-002'`，且存在对应 `TraceLink`（`ECN→BomItem, affects`，`confirmed_by != null`）
- **边界**：`as_of_date = 2026-03-05T23:59:59` 与 `2026-03-05T00:00:00` 均视为当天 → 生效；**未确认时** `BomItem.part_id` 保持 `PART-001`

#### GT-ECN-003 非生效状态 ECN 不参与
- **Given** `ECN-002.status = reviewing`、`effective_date = null`
- **When** 执行影响分析 / BOM 展开
- **Then** 不产生任何生效影响，不替换物料
- **输入**：`ECN-002`
- **期望**：`impacts == []`（或 `effective == false`）；`PART-004` 保持原状
- **边界**：`draft` / `rejected` 同样不生效；`implemented` 生效

#### GT-ECN-004 effective_date 为空的处理
- **Given** ECN 状态为 `approved` 但 `effective_date = null`
- **When** 执行展开 / 影响
- **Then** 视为**未生效**
- **输入**：`approved` + `effective_date = null`
- **期望**：`effective == false`，不替换物料，并附 `warning = "missing_effective_date"`
- **边界**：不得将 `null` 当作"立即生效"

#### GT-ECN-005 影响固化为 TraceLink(affects)
- **Given** 影响分析结果经人工确认
- **When** 执行固化
- **Then** 为每个受影响对象写一条 `TraceLink(from=ECN, relation_type=affects, confirmed_by != null)`
- **输入**：`ECN-001` + 确认人 `USER-005`
- **期望**：`TraceLink` 满足唯一约束 `(project_id, from_type, from_id, to_type, to_id, relation_type)`；未确认时 `confirmed_by_id IS NULL`
- **边界**：重复固化同一目标 → 触发唯一约束，不产生重复行

#### GT-ECN-006 影响重算幂等
- **Given** 已存在 `ECNImpact` 明细
- **When** 对同一 ECN 重算
- **Then** 按 `(ecn_id, affected_type, affected_id)` 覆盖/去重，不产生重复
- **输入**：重复执行两次
- **期望**：`ECNImpact` 数量不变；`ECNImpact` 可随 ECN 级联删除后重算
- **边界**：影响面新增对象时重算 → 新增对应明细，旧明细保留

---

### 5.4 LLM JSON 校验（GT-JSON-*）

> 校验入口统一为 `validate_agent_output(agent_name, payload)`（`schemas/agent_outputs.py`）。

#### GT-JSON-001 合法输出通过
- **Given** 符合 `BomSelectionAgentOutput` 的完整 JSON（≥1 个 `BomCandidate`，含 `lifecycle_status`/`lead_time_days`/`unit_price`/`rationale`/`source_refs`）
- **When** `validate_agent_output("bom_selection", payload)`
- **Then** 返回模型实例，无异常
- **输入**：合法 dict
- **期望**：`isinstance(result, BomSelectionAgentOutput)`；字段值与输入一致（`Decimal` 正确解析）
- **边界**：`temperature = 0.0` 与 `2.0` 均在 `[0.0, 2.0]` 内合法

#### GT-JSON-002 非法 JSON（原始字符串不可解析）
- **Given** LLM 返回非 JSON 文本（如 `"抱歉，我无法完成"` 或截断的 `'{"cards": ['`）
- **When** 进入校验流程
- **Then** 解析失败 → `AgentRun.status = "failed"`、`output_schema_valid = false`、`output_json = null`
- **输入**：非法字符串
- **期望**：抛解析异常（`json.JSONDecodeError`）或 `ValidationError`；HTTP `422`；`error` 含摘要；输入与引用仍保留
- **边界**：合法 JSON 但非对象（如 `[1,2]` / `"str"`）→ 同样失败

#### GT-JSON-003 缺必填字段
- **Given** `RequirementAgentOutput` 缺少 `cards`，或 `BomCandidate` 缺少 `lifecycle_status` / `rationale`
- **When** 校验
- **Then** `ValidationError`
- **输入**：缺字段 payload
- **期望**：错误 `loc` 指向缺失字段；`status = "failed"`
- **边界**：`cards = []` → 违反 `min_length=1`，失败；`nodes = []`（Traceability）在 `found=false` 时**合法通过**，在 `found=true` 时失败（不变量 `found=true ⟹ nodes≥1`，见 §6 OI-1）

#### GT-JSON-004 未知字段（extra="forbid"）
- **Given** payload 含模型未声明的字段（如 `BomCandidate` 额外带 `"magic_score": 0.99`）
- **When** 校验
- **Then** `ValidationError`
- **输入**：含未知字段 payload
- **期望**：错误类型为 `extra_forbidden`
- **边界**：字段名大小写不符（`Lifecycle_Status`）→ 视为未知字段，失败

#### GT-JSON-005 幻觉 ID（引用不存在实体）
- **Given** schema 合法，但 `SourceRef.id = "PART-999"` / `recommended_part_id = "PART-404"` / `TraceNode.node_id = "REQ-999"` 在库中不存在
- **When** 依次执行**两个独立步骤**：①schema 校验；②引用存在性核验
- **Then** schema 校验通过，但核验失败 → 写入 `invalid_references`，**不得落库为正式数据**
- **输入**：schema 合法、引用不存在
- **期望**：`output_schema_valid == true` 但 `reference_check_passed == false`、`invalid_references` 非空；`AgentRun.status = "failed"`；**不进入人工确认队列**；不生成正式 `TraceLink`
- **边界**：
  - 引用 ID 存在但类型不匹配（`type=part` 实际是 `document`）→ 同样失败
  - `confirmed = false` 的候选（正常候选态）**不**触发该失败
  - 合法演示引用（如 `PART-001`、`DOC-001`）→ 核验通过

#### GT-JSON-006 数值越界与枚举非法
- **Given** `confidence = 1.5`、`temperature = -0.1`、`lifecycle_status = "unknown"`、`relation_type = "foo"`
- **When** 校验
- **Then** 全部 `ValidationError`
- **输入**：越界/非法枚举值
- **期望**：`confidence` 限于 `[0,1]`；`temperature` 限于 `[0,2]`；枚举仅接受白名单值
- **边界**：`confidence = 0.0` 与 `1.0` 合法；`confidence = null` 合法（`TraceRef`/`TraceNode` 处可选）

#### GT-JSON-007 Param 取值一致性校验
- **Given** `Param` 模型 `model_validator` 约束
- **When** 校验以下输入
- **Then** 按规则判定
- **输入 / 期望**：
  - `operator=range` 且缺 `value_min`/`value_max` → 失败
  - `operator=range` 且 `value_min > value_max` → 失败
  - `operator=gte` 且缺 `value_num` → 失败
  - `operator=lte` 且缺 `value_num` → 失败
  - `operator=eq` 且 `value_num`、`value_text` 均缺 → 失败
  - `operator=eq` 且仅 `value_text` → 通过
- **边界**：`value_min == value_max` → 通过

#### GT-JSON-008 agent_name 映射与非法 agent_name
- **Given** `agent_name ∈ {requirement, bom_selection, traceability}`
- **When** 调用 `validate_agent_output`
- **Then** 路由到正确模型
- **输入 / 期望**：
  - `"requirement"` → `RequirementAgentOutput`
  - `"bom_selection"` → `BomSelectionAgentOutput`
  - `"traceability"` → `TraceabilityAgentOutput`
  - `"unknown_agent"` → 抛出（`ValueError`/`KeyError`），不静默回退
- **边界**：传入枚举 `AgentName.REQUIREMENT` 与字符串 `"requirement"` 等价

---

### 5.5 TraceLink 反查（GT-TRACE-*）

#### GT-TRACE-001 序列号命中完整链路
- **Given** `SN-DEMO-001`（`PART-002`）及 `TL-025`、`TL-027`、`TL-039` 等已确认链
- **When** `GET /trace/serial/SN-DEMO-001/`
- **Then** 返回"需求→BOM→物料批次→采购单→测试→ECN→Git 提交"链路，含引用
- **输入**：`sn = SN-DEMO-001`, `direction = backward`
- **期望**：节点含 `REQ-001`、`BOM-001`、`SN-DEMO-001`、`PO-002`、`TR-001`、`ECN-001`、`b2c3d4e5f60718293a4b5c6d7e8f90123456789a`（该 GitCommit 的提交 SHA）；每个 `TraceNode.source_refs` 非空；`edges` 关系语义正确（`implemented_by`/`sourced_from`/`tested_by`/`affects`/`evidences`/`replaces`）；`found == true`、`complete == true`、`missing == []`
- **边界**：`depth = 1` → 仅返回距起点 1 跳的节点；`direction = forward` → 反向展开

#### GT-TRACE-002 未确认链过滤
- **Given** 存在 `confirmed_by_id IS NULL` 的智能体候选链
- **When** 反查
- **Then** 未确认链**不进入**结果
- **输入**：库中含一条未确认 `TraceLink`
- **期望**：结果不含该边/节点；不因未确认链断裂而编造
- **边界**：未确认链与已确认链指向同一目标 → 仅保留已确认链

#### GT-TRACE-003 序列号查不到 → `found=false` 空链而非编造
- **Given** 查询库中不存在的 `SN-DOES-NOT-EXIST`
- **When** `GET /trace/serial/SN-DOES-NOT-EXIST/`
- **Then** 返回 `HTTP 200` + `found=false` 空链，**禁止编造节点**，且**短路返回、不调用 LLM**
- **输入**：`sn = SN-DOES-NOT-EXIST`
- **期望**：
  - HTTP 状态码 `200`
  - `found == false`
  - `complete == false`
  - `nodes == []`、`edges == []`
  - `missing == ["serial_not_found"]`
  - `warnings` 含 `"serial_not_found"`
  - **零 LLM 调用**（mock LLM 客户端断言未被调用）
  - **无新增 AgentRun**（R1：无 LLM 调用即无 AgentRun）
  - **无新增 TraceLink**
  - **不得**出现任何 `REQ-*` / `BOM-*` / `PART-*` 节点
- **边界 1**：序列号存在但无任何 `TraceLink`（零链）→ `found == true`、`complete == false`，`nodes` 含该 `InventoryLot` 自身，`missing == ["no_trace_links"]`（机器 token），`warnings` 含 `"未建立追溯链"`（人类可读镜像）；**先查库、无 LLM 调用时同链不产生 AgentRun**
- **边界 2**：大小写/空格差异（`" sn-demo-001 "`）→ 规范化后按存在/不存在分别处理，不误报编造
- **备注**：**`found=false` 是合法业务结果，严禁记 `failed`**；契约已冻结为 `found: bool` + 不变量 `found=false ⟺ nodes=[]`、`found=false ⇒ complete=false`、`complete ⇔ missing=[]`（双向）、`found=true ⟹ nodes` 含根节点（见 §6 OI-1，已决议）。**无 LLM 调用 → 无 AgentRun（R1）**。

#### GT-TRACE-004 每个节点必须带引用
- **Given** 命中链路的节点
- **When** 校验输出
- **Then** 每个 `TraceNode.source_refs` 非空，且 `SourceRef` 可核验
- **输入**：`SN-DEMO-001`
- **期望**：无引用节点视为链路不完整，写入 `missing` 并告警；不得以无引用节点充当"完整链"
- **边界**：批量查询时，含无引用节点的链路不得标记为 `complete`

#### GT-TRACE-005 链路断点写入 missing
- **Given** 构造"批次无来源采购单"或"物料无测试执行"的断链
- **When** 反查
- **Then** 缺失环节写入 `missing`，已存在环节照常返回
- **输入**：`INV` 无 `sourced_from` 边
- **期望**：`missing` 含 `"no_purchase_order"`；已有节点保留，绝不补造该环节节点
- **边界**：多个断点 → `missing` 列出全部，顺序稳定

#### GT-TRACE-006 depth 与 direction 参数
- **Given** 完整链路
- **When** 指定 `depth` / `direction`
- **Then** 结果规模与方向符合参数语义
- **输入 / 期望**：
  - `depth = 0` → 全链路
  - `depth = 2` → 距起点 ≤2 跳
  - `direction = backward`（默认）→ 从批次回溯来源
  - `direction = forward` → 从批次正向展开受影响对象
- **边界**：`depth` 为负值 → `400`；`direction` 非法值 → `400`

#### GT-TRACE-007 批次（lot）反查
- **Given** `query_type = "lot"` 与批次号（如 `LOT-DCDC-001`）
- **When** 反查
- **Then** 按批次号定位并返回链路
- **输入**：`query_type = "lot"`, `LOT-DCDC-001`
- **期望**：起点为对应 `InventoryLot`；其余口径同 `serial`
- **边界**：序列号当作批次号查询且不存在 → `found=false`、`complete=false` 空链（同 GT-TRACE-003）；不因参数类型差异编造

---

## 6. 待冻结的契约分歧点（Open Issues）

> 冻结过程中发现的**契约冲突**。**OI-1、OI-2、OI-6 已于 2026-10-04 决议并冻结**（见下）；其余项需在 D12 前决议，决议前 D12 以本节"建议口径"为准。

| ID | 问题 | 现状 | 处置 |
| --- | --- | --- | --- |
| **OI-1** ✅ 已决议 | `TraceabilityAgentOutput.nodes` 曾定义 `min_length = 1`，与"序列号查不到返回空链"冲突 | 原 `min_length=1` 要求 `nodes ≥ 1` | **已冻结（2026-10-04）**：新增 `found: bool`（语义=查询根实体是否存在）、`query` → `root`（仅回显）、`nodes` 允许为空；`@model_validator` 强制 `found=false ⟺ nodes=[]`、`found=true ⟹ nodes` 至少含根节点；未命中**短路不调用 LLM**，**不产生 AgentRun**（R1）；`found=false` 是合法业务结果，严禁记 `failed`（GT-TRACE-003） |
| **OI-2** ✅ 已决议 | 幻觉 ID 无法由 Pydantic schema 检测 | `validate_agent_output` 仅做结构校验 | **已冻结（2026-10-04）**：schema 校验后增加"引用存在性核验"**独立步骤**；新增 `AgentRunRead.reference_check_passed: bool \| null`（`null`=未执行到核验步骤）与 `invalid_references: [{entity_type, entity_id, reason}]`、`FailureReason ∈ {not_found｜wrong_project｜unknown_type}`，与 `output_schema_valid` 分离记录；核验失败记 `status=failed`、`reference_check_passed=false`（GT-JSON-005） |
| **OI-3** | 齐套"在途量"来源 | 明细数量存于 `TraceLink.metadata`（无行明细表） | 冻结为 `TraceLink(Part→PO, ordered_by).metadata.quantity`（§2.2）；缺失 `quantity` 视为 0 并告警 |
| **OI-4** | ECN 生效时间粒度 | `effective_date` 为 `date` | 冻结为"按自然日、含当日生效"（GT-ECN-002） |
| **OI-5** | 展开/影响是否自动应用未生效 ECN | 未明确 | 冻结为"仅 `approved`/`implemented` 且 `effective_date ≤ as_of_date` 生效；`null` 不生效"（§2.3） |
| **OI-6** ✅ 已决议 | 选型评分硬过滤后候选 **0** 个（不满足 AC-004 "≥3"） | `fixtures/demo_seed.json` 20 个 `Part` 中，仅 `PART-001`/`PART-002` 同时满足电压 9–36V + 电流 ≥5A + 温度 −40~85°C，但**均缺 `ip_rating` 参数**；其余料普遍缺关键参数；`lifecycle_status` 仅取 `active`/`obsolete`（无 `discontinued` 字面值），`supplier_parts` 另有 `nrnd`/`eol` | **已冻结（2026-10-04）**：采纳选项 (a) = **补齐 fixture 关键参数**（人工放行修数据）。`PART-001`/`PART-002` 补 `ip_rating=IP65`；`PART-018` 补完整关键参数；`PART-011`/`PART-012` 补参数但分别因电流（`3A`）/ 温度（`-20~70°C`）不足被阈值排除；新增 `SP-011`~`SP-013` 使多源有区分度；`PART-017`（`obsolete`）保留不补参数，作为 lifecycle 排除载体。lifecycle 映射冻结为 `Part ∈ {obsolete, discontinued}` 排除、`SupplierPart eol` 排除渠道、`nrnd` 保留 + `warning`。修数据后阶段 1 通过 **3** 个（`PART-002`/`PART-001`/`PART-018`），Top3 分数 `94.79 / 87.24 / 0.00`（详见 GT-BOM-009）。规则 `status = frozen`，见 ADR-0005 |

---

## 7. D12 实现映射（建议）

> 仅规定落点与命名约定，**本阶段不写代码**。

| 域 | 建议测试文件（pytest + Django） | 建议被测单元 |
| --- | --- | --- |
| BOM 展开 | `tests/golden/test_bom_expansion.py` | `bom.expand_bom()` / `bom.expand_bom_for_work_order()` |
| 齐套 / 缺料 | `tests/golden/test_kitting.py` | `kitting.analyze_kitting()` |
| ECN 影响 | `tests/golden/test_ecn_impact.py` | `ecn.analyze_ecn_impact()` / `ecn.freeze_impact()` |
| LLM JSON 校验 | `tests/golden/test_agent_output_schema.py` | `schemas.agent_outputs.validate_agent_output()` + 引用核验 |
| TraceLink 反查 | `tests/golden/test_trace_query.py` | `trace.resolve_serial_chain()` / `GET /trace/serial/<sn>/` |

实现要求：
- 固定 fixture（最小可控集），**不依赖系统当前时间**；注入 `as_of_date`。
- 断言 `Decimal` 精确值，禁止浮点近似比较。
- 每条用例须可在 CI 独立运行且结果确定。

---

## 8. 冻结声明与变更流程

- 本文件在 **D1 冻结**；D12 按本清单实现，**不得擅自增删判定口径**。
- 用例 ID 一经冻结不复用；新增用例追加编号。
- 若实现发现口径不可行，须提交变更请求，更新本文件 §2 / §6，并同步 `docs/PRD.md` §7 与 `docs/milestone.md`。
- §6 Open Issues 须在 D12 前给出决议并回填本文件。

---

## 附：覆盖自检

| 强制覆盖项 | 是否覆盖 | 用例 |
| --- | --- | --- |
| 多层 BOM 父子展开 | 是 | GT-BOM-001/002/003/004/007 |
| 选型评分 Top3 排序（规则 v1） | 是 | GT-BOM-008/009 |
| 替代料组 | 是 | GT-KIT-004/008 |
| 库存批次部分占用 | 是 | GT-KIT-002/007 |
| 在途 PO 最晚到货日 | 是 | GT-KIT-003/008 |
| ECN 生效日期前后 | 是 | GT-ECN-001/002/004 |
| ECN 人工确认后正式应用 | 是 | GT-ECN-002(b)、GT-ECN-005 |
| 停产料、长交期料 | 是 | GT-BOM-006、GT-KIT-005/006 |
| LLM 非法 JSON / 缺字段 / 幻觉 ID | 是 | GT-JSON-002/003/005 |
| 序列号查不到返回空链 | 是 | GT-TRACE-003 |

> 5 个必测域（BOM 展开 / 齐套缺料 / ECN 影响 / LLM JSON 校验 / TraceLink 反查）全部覆盖，共 **38 条**用例：BOM 9、KIT 8、ECN 6、JSON 8、TRACE 7。
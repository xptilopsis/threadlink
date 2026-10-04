# ADR-0007：D2 schema 实现注记（§6 补录与承重字段排查）

| 项 | 内容 |
| --- | --- |
| 状态 | 已接受（Accepted） |
| 日期 | 2026-10-04 |
| 里程碑 | D2（DB schema、迁移、Project/Part/Supplier CRUD、种子导入） |
| 关联 | `docs/data_dictionary.md` §0.1 / §6 / §18 / §22 · `docs/adr/0005-bom-scoring-v1-frozen.md` · `rules/bom_scoring.v1.json` · `fixtures/demo_seed.json` · `docs/er_diagram.md` |

## 背景

D2 B 段开工前的前置核验（只读）发现：**字典 §6 SupplierPart 遗漏 `lifecycle_status` 字段**，而该字段被 `fixtures/demo_seed.json`（SP-001…SP-013 全部携带）与 `rules/bom_scoring.v1.json`（`phase_1_hard_filter.supplier_lifecycle`、`phase_2_scoring` 渠道过滤）承重引用，并由 `docs/adr/0005-bom-scoring-v1-frozen.md` 冻结了渠道级语义。

指令口径为「字典是唯一事实来源，禁止自行发明 schema；字典未明确处停下汇报」。经人工裁决（选项：先改字典再继续），采纳「**post-freeze 补录字典 §6 + 建立承重字段排查记录**」，使字典重新成为自洽的唯一事实来源，再据此生成 models。本 ADR 为该裁决与排查结果的留痕。

## 决策

### 1. §6 字段遗漏与补录

- 补录字段：`SupplierPart.lifecycle_status`，类型 `varchar(16)`（对齐同域 `Part.lifecycle_status`），必填，默认 `active`。
- 字典正文已在 §6 表格 `is_preferred` 之后新增该行，并附补录脚注（来源 fixture + rules v1，见本 ADR）。
- **仅新增、不删改**任何既有字段（post-freeze 修订原则，见 §5）。
- `docs/er_diagram.md` 经核对**仅**给出 SupplierPart 的索引建议 `(supplier_id, part_id)` 唯一与结构归属 FK 说明，**未枚举实体属性**，故无需同步修改。

### 2. 键名核验结果（只读）

| 来源 | 引用的键名 | 结论 |
| --- | --- | --- |
| `rules/bom_scoring.v1.json` | `supplier_parts.lifecycle_status`（`scope`）、`supplier_parts.lifecycle_status != eol`（阶段 2 维度取值） | 键名 `lifecycle_status`，snake_case |
| `fixtures/demo_seed.json` `supplier_parts[*]` | 键集含 `lifecycle_status`；另含 `supplier_id` / `part_id` / `supplier_part_number` / `unit_price` / `currency` / `lead_time_days` / `moq` / `is_preferred` | 键名一致 |
| `docs/adr/0005-bom-scoring-v1-frozen.md` | `SupplierPart.lifecycle_status` | 键名一致 |
| `docs/demonstration_project_requirements.md` §2.3 | 「`supplier_parts` 关系须包含：价格、MOQ、交期、**生命周期**」 | 承重需求依据 |
| `schemas/agent_outputs.py` | `BomCandidate.lifecycle_status`（输出 DTO，`LifecycleStatus` 枚举） | 非 SupplierPart 字段，无同步 |

**结论：全部来源键名一致，无键名冲突（无 ③ 类）。**

### 3. 枚举集与默认值（经核验）

- **取值集 = 实际出现值**（fixture SP-001…SP-013 分布）：`active`(10) / `nrnd`(1) / `eol`(1) / `obsolete`(1)，并集 = `active` / `nrnd` / `eol` / `obsolete`，与同域 `Part.lifecycle_status` 一致。
- **默认值**：`active`。依据：① 同域 `Part.lifecycle_status` 默认 `active`；② fixture 常规渠道全部取 `active`（10/13）；文档未另行规定默认，取同域对齐值。
- **语义（一句）**：渠道级生命周期，独立于物料级判定——`eol` 渠道在 `min(unit_price)` / `min(lead_time)` / `multi_source` 计算中排除；`nrnd` 渠道保留并计入 warning、v1 不降权（指向 `rules/bom_scoring.v1.json`，留 D6 评估）。

### 4. 承重字段全量排查表（只读）

口径：①=fixture 使用而字典缺失（承重）→ 字典补录 + 本 ADR 记录；②=字典定义而 fixture 未填充（可空未用）→ 仅列出；③=键名 / 类型 / 取值冲突 → 停下汇报。

| 集合 | ①类（fixture 有、字典无） | ②类（字典有、fixture 无） | ③类 |
| --- | --- | --- | --- |
| `supplier_parts` | **`lifecycle_status`** | — | — |
| `users` | — | `password` / `is_superuser` / `last_login` | — |
| `trace_links` | — | `evidence` / `created_by_id` | — |
| 其余 18 集合 | — | — | — |

- ①类仅 1 项，已补录。
- ②类均为可空 / 由 Django 或加载器处理字段（`password` 走 `set_unusable_password`；`is_superuser`/`last_login` 由框架管理；`evidence`/`created_by_id` 可为空且 fixture 未用），**不影响 schema，不补录**。
- 规则 / schema / 契约字段引用扫描：`rules/bom_scoring.v1.json` 另引用 `part.lifecycle_status`（字典 §3 已有）与关键参数名 `input_voltage` / `rated_current` / `operating_temp` / `ip_rating`（属 `PartParam.name` 取值，非字段）、`unit_cost`（参数名）；`interface_contract.md` 引用均为 API DTO 字段（`part_number` / `lifecycle_status` / `params[]`、`BomCandidate.*`）。**均无字典缺失或冲突（无 ③ 类）。**
- **结论：无 ③ 类冲突，B 段无需因排查停下。**

### 5. post-freeze 文档修订声明

- 本次对 `docs/data_dictionary.md` 的修订**仅为补录**（新增 §6 一行字段 + 一条补录脚注），**不删改任何既有内容**，不改变任何已冻结字段的类型 / 必填 / 语义。
- `fixtures/demo_seed.json` 与 `rules/bom_scoring.v1.json` **禁止改动**，本次未改。
- 后续 B 段实现注记（on_delete 决策表、金额精度、`temperature` 类型、`agent_name` choices、枚举并集等）将在本 ADR 追加，作为 §7 报告项的留痕。

## 后果

- 正向：字典恢复自洽，`SupplierPart.lifecycle_status` 可作为 B 段 model 字段直接生成；渠道级规则（D6）有字段承载。
- 成本：引入一次 post-freeze 文档修订；已以「仅补录不删改」与独立小提交隔离，降低对既有冻结内容的影响。
- 留痕：补录依据、键名核验、枚举默认值、全量排查表均固化于本 ADR；后续实现注记追加于 §5。
## 附：B 段实现注记（2026-10-04）

### A. on_delete 决策（字典逐条写明，无未决项）

| 关系 | on_delete |
| --- | --- |
| `Project.created_by` / `Bom.created_by` / `ECN.requested_by` → User | PROTECT |
| `BomItem.part` / `InventoryLot.part` / `WorkOrder.bom` / `PurchaseOrder.supplier` → 目标 | PROTECT |
| 各 `*.project`（Part/Supplier/Requirement/Bom/InventoryLot/WorkOrder/PurchaseOrder/TestCase/TestRun/ECN/Document/GitRepo/GitCommit/TraceLink/AgentRun）→ Project | CASCADE |
| `PartParam.part` / `RequirementParam.requirement` / `BomItem.bom` / `BomItem.parent_item` / `TestRun.test_case` / `ECNImpact.ecn` / `GitCommit.repo` | CASCADE |
| `SupplierPart.supplier` / `SupplierPart.part` | CASCADE |
| `Requirement.agent_run` / `ECN.agent_run` / `TraceLink.agent_run` → AgentRun | SET_NULL |
| `Requirement.confirmed_by` / `WorkOrder.created_by` / `TestRun.tester` / `ECN.approved_by` / `Document.uploaded_by` / `TraceLink.confirmed_by` / `TraceLink.created_by` / `AgentRun.confirmed_by` → User | SET_NULL |

**D2 收口抽查（2026-10-04）**：上表**全部为字典各字段说明的明文**，无原则推导误植。逐字抽查：`Project.created_by`（§2「FK → User，创建人（on_delete=PROTECT）」）、`Bom.created_by`（§9「FK → User（PROTECT）」）、`ECN.requested_by`（§16「FK → User（PROTECT）」）、`BomItem.part`（§10「FK → Part（PROTECT，BOM 展开必需）」）、`InventoryLot.part`（§11「FK → Part（PROTECT）」）、`WorkOrder.bom`（§12「FK → Bom（PROTECT）」）、`PurchaseOrder.supplier`（§13「FK → Supplier（PROTECT）」）、`Requirement.confirmed_by`（§7「FK → User（SET NULL）」）、`TestRun.tester`（§15「FK → User（SET NULL）」）、`ECN.approved_by`（§16「FK → User（SET NULL）」）、`TraceLink.created_by`（§18「FK → User（SET NULL）」）——**11/11 逐字一致，无改动**。

### B. 字段级歧义与处置

- **`temperature`**：字典 §22 为 `numeric(3,2)`（模型 `agents.AgentRun.temperature`），`interface_contract.md` §6 与 `schemas` 为 `float`。按「字典为唯一事实来源」落为 `DecimalField(max_digits=3, decimal_places=2)`（上限 ±9.99）。**域核验（D2 收口）**：用途为 LLM 采样温度，`interface_contract.md` §6 明确 `0.0 ~ 2.0`；fixture 实际取值 `0.0`/`0.1`/`0.2`，域为 `[0,2]`，**不含 |x| ≥ 10**，`(3,2)` 宽度足够，**保留、无改动**。
- **枚举 choices**：`agent_name` / `status` / `relation_type` / `source` / `source_type` / `operator` / `priority` 及 **`SupplierPart.lifecycle_status`**（渠道级四值）由 `schemas/agent_outputs.py` 对应枚举经 `enum_choices()` 生成；**`Part.lifecycle_status`（物料级）为例外**——物料级须覆盖规则消费的 `obsolete`/`discontinued`，故新增 `core.models.PartLifecycleStatus = {active, nrnd, eol, obsolete, discontinued}`（superset），与渠道级四值**拆分、互不替代**（D2 收口）。
- **`ECNImpact.affected_type`**：按指令从 `EntityType`（13 值）生成 choices；字典 §17 列出业务子集（`bom_item`/`inventory_lot`/`purchase_order`/`test_case`/`part`）。二者为子集关系，本次采用 `EntityType`（superset），D 段如需收紧按业务限制。
- **金额 / 数量**：一律 `DecimalField(max_digits=18, decimal_places=4)`（字典 §0）。
- **时间戳**：`created_at` / `updated_at` 用 `default=timezone.now`（非 `auto_now_add`/`auto_now`），以便加载器保留 fixture 时间戳。

### C. 业务编号

- 自动前缀、scope、重试、例外同 ADR-0006 §2。
- `BomItem` 无 `project` FK（字典 §10），故 project 级唯一性由**三层**共同承担：① 编号器经 `bom__project` 解析 + 人工预检；② DB 层 `UniqueConstraint(bom, item_no)` 兜底（项目级唯一蕴含 BOM 级唯一，不误拒）；③ `scripts/validate_seed.py` 文件级唯一（fixture `id == item_no` 且逐值唯一）。**D4 约束（遗留）**：D4/解析层若遇同一 project 内出现**同号不同 BOM 的 `BI-###` 歧义**，必须 **fail-loud**（报错而非静默取一条），此约束记入 D4 任务。
- `InventoryLot.serial_number` / `GitCommit.sha` 人工直写，不继承 `NumberedModel`。

### D. 迁移结构

`makemigrations` 自动将 `AgentRun.project` 拆到 `agents 0002`，形成无环 DAG：`core 0001 → agents 0001 → core 0002 → agents 0002 → traceability 0001`。

### E. 加载顺序偏差（种子导入）

指令顺序中 `project` 在 `users` 前、`agent_runs` 最后，但 `Project.created_by` 与 `Requirement`/`ECN`/`TraceLink.agent_run` 的 FK 依赖要求先建 User / AgentRun。实际顺序调整为：`users → project → agent_runs → parts → …`（其余保持指令相对顺序）。`fixtures` 与 `rules` 未改。

### F. Admin 字段偏差

指令 §3 提及 Supplier 的 `rating` / `lead_time_days`，但字典 §5 Supplier 无此二字段（`lead_time_days` 属 `SupplierPart`）。`SupplierAdmin` 按字典实际字段实现：`code` / `name` / `status` / `contact_name` + search/filter + `SupplierPart` inline。

### G. 验证结果

- 迁移：`check` 0 issues；`showmigrations` 全部 `[X]`。
- 种子：`load_demo_seed --flush` 计数 `parts 20 / requirements 5 / test_cases 10 / test_runs 12 / suppliers 3 / purchase_orders 5 / inventory_lots 3 / ecns 2 / trace_links 39 / git_commits 3`（另 `agent_runs 5 / part_params 36 / requirement_params 12 / supplier_parts 13 / bom_items 16 / ecn_impacts 8 / documents 5 / git_repos 1`）；无 `--flush` 复跑幂等。
- 认证态 Admin：`/admin/`、`/admin/core/project/`、`/admin/core/part/`、`/admin/core/supplier/` 均 200。
- 编号实测：现有 20 个 Part 下新建自动编号 `PART-021`；手填重复抛 `NumberingError`。
- `validate_seed.py` 仍 OK（fixtures 未改）；`compileall -q core traceability agents` 通过；`pytest -q` 6 passed。
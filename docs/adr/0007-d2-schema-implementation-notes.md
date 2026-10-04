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
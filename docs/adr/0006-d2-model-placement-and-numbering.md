# ADR-0006：D2 模型归属与业务编号生成策略

| 项 | 内容 |
| --- | --- |
| 状态 | 已接受（Accepted） |
| 日期 | 2026-10-04 |
| 里程碑 | D2（DB schema、迁移、Project/Part/Supplier CRUD） |
| 关联 | `docs/data_dictionary.md` §0.1 / §1 · `docs/adr/0003-d3-role-functional-enum.md` · 全批次口径 R2 / R7–R9 |

## 背景

D2 起进入数据库落地：需要为 D1 冻结的全部实体分配 Django app，并冻结**业务编号的生成策略**。业务编号是 R2 定义的唯一对外标识（URL `<id>`、TraceLink 端点、ECNImpact.affected_id、AgentRun.references 等全部使用它），其生成规则必须在开始建 models 前定稿，否则 B 段迁移会反复返工。

D1 冻结实体共 22 个（D1 原 23 实体，移除 `KnowledgeItem`）；其中 `User` 属本段（A 段）落地，其余 21 个属 B 段。A 段落地 `User` 与前置数据库动作；本 ADR 同时作为 B 段模型生成与编号实现的依据。

## 决策

### 1. app 归属映射（B 段按此建 models）

| app | 实体 | 数量 |
| --- | --- | --- |
| `core` | `User`（A 段已落地）、`Project`、`Part`、`PartParam`、`Supplier`、`SupplierPart`、`Requirement`、`RequirementParam`、`Bom`、`BomItem`、`InventoryLot`、`WorkOrder`、`PurchaseOrder`、`TestCase`、`TestRun`、`ECN`、`ECNImpact`、`Document`、`GitRepo`、`GitCommit` | `User` + `Project` + 19 |
| `traceability` | `TraceLink` | 1 |
| `agents` | `AgentRun` | 1 |

- 合计 22 实体：`core` 承载 `Project` 与 19 个业务实体（`Part` … `GitCommit`），`traceability` 承载跨域追溯权威表 `TraceLink`（R3），`agents` 承载 LLM 调用审计 `AgentRun`（R1）。
- `data_dictionary.md` / `er_diagram.md` 未另行规定 app 归属，本映射为冻结取值；若后续文档出现不同约定，以文档为准并报告差异。

### 2. 业务编号生成策略（B 段实现）

**自动前缀表**（缺省 `TYPE-NNN` 风格，R9）：

| 实体 | 编号字段 | 前缀 | 生成方式 | 唯一性范围 |
| --- | --- | --- | --- | --- |
| Part | `part_number` | `PART-` | 自动，人工可覆盖 | `(project_id, part)` |
| Supplier | `code` | `SUP-` | 自动，人工可覆盖 | `(project_id, supplier)` |
| Requirement | `code` | `REQ-` | 自动，人工可覆盖 | `(project_id, requirement)` |
| Bom | `bom_no` | `BOM-` | 自动，人工可覆盖 | `(project_id, bom)` |
| BomItem | `item_no` | `BI-` | 自动，人工可覆盖 | `(project_id, bom_item)` |
| WorkOrder | `code` | `WO-` | 自动，人工可覆盖 | `(project_id, work_order)` |
| PurchaseOrder | `po_number` | `PO-` | 自动，人工可覆盖 | `(project_id, purchase_order)` |
| TestCase | `code` | `TC-` | 自动，人工可覆盖 | `(project_id, test_case)` |
| TestRun | `run_no` | `TR-` | 自动，人工可覆盖 | `(project_id, test_run)` |
| ECN | `ecn_number` | `ECN-` | 自动，人工可覆盖 | `(project_id, ecn)` |
| Document | `doc_no` | `DOC-` | 自动，人工可覆盖 | `(project_id, document)` |
| InventoryLot | `serial_number` | —（`SN-*` / `LOT-*` 天然标识） | **人工必填** | `(project_id, inventory_lot)` |
| GitCommit | `sha` | —（真实提交 SHA） | **Git 只读同步** | `(repo, git_commit)` |

**例外说明**：
- `InventoryLot.serial_number` = 批次或序列单元的可追溯标识，语义上**不是序号产物**，故**人工必填**、不自动生成。
- `GitCommit.sha` 由 Git 同步写入（只读），不参与自动生成。

**算法与约束**：
- 生成：per `(project, 编号字段)` 解析现有编号中的最大数字，**+1**，**三位零填充**（`001`…`999`，超过 999 自然进位为四位，不截断）。
- 落地：**应用层生成 + `UniqueConstraint(project, 编号字段)` 兜底**；两个层级同时保证唯一。
- 人工覆盖：先校验唯一，通过则以人工值为准。
- 冲突重试：自动生成遇唯一冲突**重试 ≤3 次**，仍失败则报错。
- **BomItem 编号 scope = project 级**（§0.1 冻结值）：因 `ECNImpact.affected_id` 需用 `BI-###` 直接引用，per-BOM 递增会在跨 BOM 引用时产生歧义，故 `item_no` 在项目内全局唯一。
- **数据导入路径（fixture 回填）不触发自动生成**——显式指定编号保存（R8 要求 fixture `id == 编号`）。

### 3. create_superuser 的 role 口径

- 自定义 `UserManager.create_superuser` **强制** `role="admin"`、`is_staff=True`、`is_superuser=True`，与 `data_dictionary.md` §1「`role=admin` ⟺ 系统管理员」一致。
- `create_user` 默认 `role="engineer"`、`is_staff=False`、`is_superuser=False`；`User.role` 字段默认值 `engineer`。
- `role` 冻结枚举 `admin` / `engineer` / `procurement` / `test` / `quality`（ADR-0003）。

## 后果

- 正向：B 段可一次性按字典建全部 models + 迁移（schema 冻结），D3 只补视图与页面；编号策略统一，R2 的多态引用可直接用编号定位。
- 成本：应用层需实现编号生成器与重试逻辑；`BomItem` 的 project 级唯一约束使其无法简单用「每 BOM 独立编号」。
- **实现落点**：本 ADR 是 B 段模型生成与编号器实现的依据；编号生成策略的实际代码（生成器、唯一约束、重试）在 **B 段**落地，A 段不实现。
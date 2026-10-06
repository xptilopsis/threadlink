# ThreadLink 数据字典

> 与 `docs/er_diagram.md` 配套。定义每个实体字段的**类型、是否必填、说明**。类型以 PostgreSQL 为准，同时给出 Django ORM 映射约定。

---

## 0. 通用约定

| 约定 | 说明 |
| --- | --- |
| 主键 | 统一 `id bigint` 自增（Django `BigAutoField`），全表必填 |
| 外键 | `*_id bigint`，指向目标实体主键；Django `ForeignKey`。**FK 仅表达层级 / 包含 / 归属 / 计算强依赖；跨域、需审计、多对多的追溯关系一律用 `TraceLink`（§18）承载，FK 不构成追溯声明**（PRD §6.1）；`on_delete` 见各字段说明 |
| 时间 | 统一 `timestamptz`（Django `DateTimeField`）；`date` 用 `DateField` |
| 金额 / 数量 | `numeric(18,4)`（Django `DecimalField`），避免浮点误差 |
| JSON | `json`（Django `JSONField`）；描述与查询均按 `JSONField`，**不写 `jsonb`**，避免依赖 PostgreSQL jsonb 包含查询（R4） |
| 软删除 | 审计相关实体（`TraceLink`、`ECN`、`Document`、`AgentRun`）**不做物理删除**，用状态位 / 标记留痕 |
| 多态字段 | 以 `*_type varchar` + `*_id varchar`（**业务编号**，非数据库主键）成对出现（`TraceLink`、`ECNImpact`）（R2，见 §0.1） |

**必填列约定**：`是` = NOT NULL 且需应用层提供；`否` = 可空（NULL）。

### 0.1 标识约定（业务编号，R2 / R7–R9）

- **业务编号是唯一对外标识（R2）**：URL 路径中的 `<id>`、`TraceLink.from_id/to_id`、`ECNImpact.affected_id`、`AgentRun.references`、`SourceRef`/`TraceRef` 的 `entity_id` 等**全部使用业务编号（varchar）**，**不使用数据库主键**。
- **主键仅内部使用（R2）**：所有表主键为 `id bigint` 自增（Django `BigAutoField`），不对外暴露。
- **一个实体一个业务编号字段（R7）**：业务编号**复用各实体现有编号字段**承载（**不新增平行字段**）；上一版表中的 `part_no`/`req_no`/`po_no`/`ecn_no` 等命名作废。同一实体若出现两套编号，**以被外部契约（URL 路径 / 跨实体引用 / golden tests）承重的取值为准，其余作废**（清点结果见下表）。
- **fixture 自洽（R8）**：`fixtures/demo_seed.json` 中每个条目的 `id` **必须等于**该实体业务编号字段的值（**逐值照搬、不得重编号**）；`scripts/validate_seed.py` 对此强制断言。
- **格式与解析（R9）**：业务编号稳定、可读、带类型前缀（`TYPE-NNN` 为缺省风格；`SN-*` / `LOT-*` / 提交 SHA 属天然标识，不受前缀风格约束）；**不设严格正则**（`SN-DEMO-001` 合法）。解析规则统一为 `(project_id, entity_type, business_no)` 唯一定位，**D2 引用存在性核验与 TraceLink 端点解析共用同一规则**。
- **多态端点白名单**：仅下表「端点=是」的业务编号实体可作 `TraceLink.from_id/to_id`、`ECNImpact.affected_id`、`TraceNode.node_type`（与 `schemas/agent_outputs.py` 的 `EntityType` **一一对应**）。`User`/`Project` 仅经 FK 关联；`AgentRun`/`TraceLink` 为审计记录；明细表（`PartParam`/`RequirementParam`/`SupplierPart`/`ECNImpact`）随父行定位——均**不作多态端点**。
- **明细表无业务编号（§A-2）**：`PartParam` / `RequirementParam` / `SupplierPart` / `ECNImpact` **无独立业务编号**（fixture 中的 `PP-*` / `RP-*` / `SP-*` / `EI-*` 仅为集合内 `id`，**非** R2/R9 意义上的对外业务编号），因此**不可作为多态引用目标**（不得出现在 `TraceLink.from_id/to_id`、`ECNImpact.affected_id`、`TraceNode.node_id`），**也不可作为任何 URL 的 `<id>`**，一律经父行 FK 定位。**唯一例外**：`ECNImpact.affected_id` 是**指向端点实体的出站多态引用**（取被影响实体的业务编号，按 T1.3 规则），**不是 ECNImpact 自身的编号**，二者不可混淆。
- **加载与反解（R8）**：`fixtures/` 用业务编号互引，加载器负责解析为 pk。

**业务编号字段（冻结）**：

| 实体 | 端点 | 业务编号字段 | 取值示例（定稿） | 唯一性范围 | 作废旧值 |
| --- | --- | --- | --- | --- | --- |
| Part | 是 | `part_number` | `PART-001` | `(project_id, part)` | `PN-1001` / `PN-10` |
| Supplier | 是 | `code` | `SUP-001` | `(project_id, supplier)` | `SUP-A` / `SUP-B` / `SUP-C` |
| Requirement | 是 | `code` | `REQ-001` | `(project_id, requirement)` | `REQ-PWR-001` |
| Bom | 是 | `bom_no`（新增） | `BOM-001` | `(project_id, bom)` | —（新增，无旧值） |
| BomItem | 是 | `item_no`（新增） | `BI-001` | `(project_id, bom_item)` | —（新增，无旧值） |
| InventoryLot | 是 | `serial_number` | `SN-DEMO-001` / `LOT-DCDC-001` | `(project_id, inventory_lot)` | `INV-###` |
| WorkOrder | 是 | `code` | `WO-001` | `(project_id, work_order)` | `WO-2026` |
| PurchaseOrder | 是 | `po_number` | `PO-001` | `(project_id, purchase_order)` | `PO-2026-001` |
| TestCase | 是 | `code` | `TC-001` | `(project_id, test_case)` | `TC-PWR` |
| TestRun | 是 | `run_no`（新增） | `TR-001` | `(project_id, test_run)` | —（新增，无旧值） |
| ECN | 是 | `ecn_number` | `ECN-001` | `(project_id, ecn)` | `ECN-2026` |
| Document | 是 | `doc_no`（新增） | `DOC-001` | `(project_id, document)` | —（新增，无旧值） |
| GitCommit | 是 | `sha` | 真实提交 SHA（`a1b2c3…`） | `(repo, git_commit)` | `GC-###` |
| Project | 否 | —（`code` 为项目编码，非多态编号） | — | — | — |
| User | 否 | —（`username` 为登录名） | — | — | — |
| GitRepo | 否 | —（`name` 为仓库名） | — | — | — |
| TraceLink / AgentRun | 否 | —（审计记录，内部主键不对接多态） | — | — | — |
| 明细表 PartParam / RequirementParam / SupplierPart / ECNImpact | 否 | —（随父行定位，无独立业务编号；不可作多态目标 / URL `<id>`，`ECNImpact.affected_id` 为出站引用例外） | — | — | —（无） |

> - **清点结论（R7，2026-10-04）**：全实体**无「双编号被同时承重」**情形。端点实体的业务编号字段值 **均等于 fixture `id`**（`validate_seed.py` 逐值断言，实测 0 处不一致）；`Project`/`User`/`GitRepo` 的 `code`/`username`/`name` 为**属性字段，非多态编号**，不参与 R7 清点。
> - `InventoryLot` 以 `serial_number`（批次号 / 序列号）作业务编号；`TraceLink`/`ECNImpact` 对库存批次的引用一律用 `serial_number`（**不再使用 `INV-###`**）。
> - `GitCommit` 以真实 `sha` 作业务编号（**不再使用 `GC-###`**）。
> - `TYPE-NNN` 为缺省风格；批次 / 序列号（`SN-*`、`LOT-*`）与提交 SHA 属天然标识，不受此风格约束。
> - 端点实体上表之外的类型（含 `project`/`agent_run`/`knowledge_item`/`trace_link`/明细表）**不得**出现在 `EntityType`。

---

## 1. User（用户）

> 采用 Django 的 `AbstractUser` 扩展（下阶段设 `AUTH_USER_MODEL`）；**D1 只冻结契约，不执行任何数据库操作**。下表列关键字段。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| username | varchar(150) | 是 | 登录名，唯一 |
| password | varchar(128) | 是 | 密码哈希（Django 管理，禁止明文） |
| email | varchar(254) | 否 | 邮箱 |
| first_name | varchar(150) | 否 | 名 |
| last_name | varchar(150) | 否 | 姓 |
| role | varchar(16) | 是 | **职能角色（冻结枚举，以 PRD §3 为权威）**：`admin` / `engineer` / `procurement` / `test` / `quality` |
| is_active | boolean | 是 | 是否启用，默认 true |
| is_staff | boolean | 是 | 是否可进 Admin，默认 false |
| is_superuser | boolean | 是 | 是否超级用户，默认 false |
| last_login | timestamptz | 否 | 最近登录时间 |
| date_joined | timestamptz | 是 | 创建时间 |

> - **`role` 冻结枚举（以 PRD §3 为权威，与 fixtures 取并集）**：固定 `admin` / `engineer` / `procurement` / `test` / `quality`（与 `fixtures/demo_seed.json` 一致）。映射 PRD §3 岗位：`admin`=系统管理员；`engineer`=研发工程师 · 硬件/结构工程师；`procurement`=采购/供应链；`test`=测试工程师；`quality`=质量/项目经理。PRD §3 的 6 类**人类**角色全部落入上述 5 值（`engineer`、`quality` 各合并 2 类），**无 PRD 独有而 fixtures 缺失的角色**；「系统（AI 智能体）」不是 User，不占 `role`。`scripts/validate_seed.py` 断言每个 `user.role` ∈ 该枚举。
> - **与 Django 内置的关系**：`role=admin` ⟺ 系统管理员，落地时置 `is_superuser=True`、`is_staff=True`；其余四个角色 `is_staff=False`（无 Django Admin 后台权限，写权限由应用层按下方映射判定）。`is_superuser`/`is_staff` 不参与业务判权。
> - **role → 可写实体集（映射框架，D11 实现）**：以 PRD §3「主要使用功能」为骨架，D11 落为权限映射——`admin`=全部；`engineer`=`Requirement` / `RequirementParam` / `Part` / `PartParam` / `Bom` / `BomItem`；`procurement`=`Supplier` / `SupplierPart` / `PurchaseOrder` / `InventoryLot` / `WorkOrder`（齐套）；`test`=`TestCase` / `TestRun`；`quality`=`ECN` / `ECNImpact` / `TraceLink` / `AgentRun`（审计）。**D1 仅冻结框架，不实现判定逻辑**；只读查询不受限。
> - **ADR**：本次修正为「role 从上一版**权限档位**三值 `admin`/`engineer`/`viewer` 改为**职能枚举**」，理由＝职能即业务权限、D11 可直接映射；见 `docs/adr/0003-d3-role-functional-enum.md`。
> - **D2 落地**：实现时设 `AUTH_USER_MODEL`，前置动作（删除 `db.sqlite3`、重建迁移、重跑 `createsuperuser`）写入 ADR；D1 不执行任何数据库操作。

---

## 2. Project（项目）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| code | varchar(64) | 是 | 项目编码，全局唯一 |
| name | varchar(200) | 是 | 项目名称 |
| description | text | 否 | 描述 |
| status | varchar(16) | 是 | active / archived，默认 active |
| created_by_id | bigint | 是 | FK → User，创建人（on_delete=PROTECT） |
| created_at | timestamptz | 是 | 创建时间 |
| updated_at | timestamptz | 是 | 更新时间 |

---

## 3. Part（物料）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| project_id | bigint | 是 | FK → Project（CASCADE） |
| part_number | varchar(100) | 是 | **业务编号**（料号），项目内唯一，如 `PART-001` |
| name | varchar(200) | 是 | 物料名称 |
| description | text | 否 | 描述 |
| category | varchar(64) | 否 | 类别（电阻 / 电容 / 连接器等） |
| manufacturer | varchar(200) | 否 | 制造商 |
| mpn | varchar(200) | 否 | 制造商料号 |
| lifecycle_status | varchar(16) | 是 | active / nrnd / eol / obsolete，默认 active（含**停产**语义） |
| unit | varchar(16) | 否 | 计量单位 |
| is_critical | boolean | 是 | 是否关键料，默认 false |
| created_at | timestamptz | 是 | 创建时间 |
| updated_at | timestamptz | 是 | 更新时间 |

---

## 4. PartParam（物料参数）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| part_id | bigint | 是 | FK → Part（CASCADE，**层级归属**） |
| name | varchar(64) | 是 | 参数名（如 voltage / current / ip_rating） |
| value_text | varchar(255) | 否 | 文本型取值 |
| value_num | numeric(18,4) | 否 | 数值型取值 |
| value_min | numeric(18,4) | 否 | 范围下界 |
| value_max | numeric(18,4) | 否 | 范围上界 |
| unit | varchar(16) | 否 | 单位 |
| is_key | boolean | 是 | 是否关键参数，默认 false |
| created_at | timestamptz | 是 | 创建时间 |

---

## 5. Supplier（供应商）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| project_id | bigint | 是 | FK → Project（CASCADE） |
| code | varchar(64) | 是 | **业务编号**（供应商编码），项目内唯一，如 `SUP-001` |
| name | varchar(200) | 是 | 供应商名称 |
| contact_name | varchar(100) | 否 | 联系人 |
| email | varchar(254) | 否 | 邮箱 |
| phone | varchar(32) | 否 | 电话 |
| status | varchar(16) | 是 | active / inactive，默认 active |
| created_at | timestamptz | 是 | 创建时间 |
| updated_at | timestamptz | 是 | 更新时间 |

---

## 6. SupplierPart（供应商-物料）

> 供料字典关系，属**结构归属**，用 FK。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| supplier_id | bigint | 是 | FK → Supplier（CASCADE） |
| part_id | bigint | 是 | FK → Part（CASCADE） |
| supplier_part_number | varchar(100) | 否 | 供应商料号 |
| unit_price | numeric(18,4) | 否 | 单价 |
| currency | varchar(8) | 否 | 币种，默认 CNY |
| lead_time_days | integer | 否 | 交期（天） |
| moq | integer | 否 | 最小起订量 |
| is_preferred | boolean | 是 | 是否优选，默认 false |
| lifecycle_status | varchar(16) | 是 | active / nrnd / eol / obsolete，默认 active；**渠道级生命周期**（eol=渠道排除；nrnd=保留 + warning，v1 不降权，见 `rules/bom_scoring.v1.json`） |
| created_at | timestamptz | 是 | 创建时间 |
| updated_at | timestamptz | 是 | 更新时间 |

> **补录说明（2026-10-04，D2 前置修正）**：`lifecycle_status` 为 **post-freeze 补录字段**——fixture（SP-001…SP-013 实际取值 `active`/`nrnd`/`eol`/`obsolete`）与 `rules/bom_scoring.v1.json`（`supplier_lifecycle`）、`docs/adr/0005-bom-scoring-v1-frozen.md`（渠道级 eol 排除 / nrnd warning）均以该字段承重，而原 §6 遗漏。类型 / 长度对齐同域 `Part.lifecycle_status`，默认值取 `active`。**仅新增、不删改既有字段**，依据见 `docs/adr/0007-d2-schema-implementation-notes.md`。

---

## 7. Requirement（需求）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| project_id | bigint | 是 | FK → Project（CASCADE） |
| code | varchar(64) | 是 | **业务编号**（需求编号），项目内唯一，如 `REQ-001` |
| title | varchar(300) | 是 | 需求标题 |
| content | text | 否 | 需求正文 |
| source_type | varchar(16) | 是 | prd / sor / email / manual，默认 manual |
| source_ref | varchar(255) | 否 | 来源引用（邮件主题 / 文档行号等） |
| status | varchar(24) | 是 | draft / pending_confirmation / confirmed / rejected / implemented，默认 draft |
| priority | varchar(8) | 否 | low / medium / high |
| confidence | numeric(5,4) | 否 | 智能体置信度（0–1） |
| agent_run_id | bigint | 否 | FK → AgentRun（SET NULL），产出该需求卡的智能体调用 |
| confirmed_by_id | bigint | 否 | FK → User（SET NULL），人工确认人 |
| confirmed_at | timestamptz | 否 | 人工确认时间 |
| created_at | timestamptz | 是 | 创建时间 |
| updated_at | timestamptz | 是 | 更新时间 |

> 来源文档关联通过 `TraceLink`（`Requirement → Document`, `derived_from`）表达，故不设 `source_document_id` FK。

---

## 8. RequirementParam（需求参数）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| requirement_id | bigint | 是 | FK → Requirement（CASCADE，**层级归属**） |
| name | varchar(64) | 是 | 参数名（如 voltage） |
| operator | varchar(8) | 是 | eq / gte / lte / range，默认 eq |
| value_text | varchar(255) | 否 | 文本型取值 |
| value_num | numeric(18,4) | 否 | 数值型取值 |
| value_min | numeric(18,4) | 否 | 范围下界（operator=range） |
| value_max | numeric(18,4) | 否 | 范围上界（operator=range） |
| unit | varchar(16) | 否 | 单位 |
| is_mandatory | boolean | 是 | 是否强制满足，默认 true |
| created_at | timestamptz | 是 | 创建时间 |

---

## 9. Bom（物料清单）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| project_id | bigint | 是 | FK → Project（CASCADE） |
| bom_no | varchar(64) | 是 | **业务编号**，项目内唯一，如 `BOM-001`（新增） |
| name | varchar(200) | 是 | BOM 名称 |
| version | varchar(32) | 是 | 版本号 |
| status | varchar(16) | 是 | draft / released / obsolete，默认 draft |
| created_by_id | bigint | 是 | FK → User（PROTECT），创建人 |
| created_at | timestamptz | 是 | 创建时间 |
| updated_at | timestamptz | 是 | 更新时间 |

> BOM 与需求的关联通过 `TraceLink`（`Requirement → Bom`, `implemented_by`）表达。

---

## 10. BomItem（BOM 明细）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| bom_id | bigint | 是 | FK → Bom（CASCADE，**层级归属**） |
| item_no | varchar(64) | 是 | **业务编号**，如 `BI-001`（新增；供 `ECNImpact.affected_id` 与 `TraceLink` 引用） |
| parent_item_id | bigint | 否 | FK → BomItem（CASCADE），自引用父子层级，顶层为 NULL |
| part_id | bigint | 是 | FK → Part（PROTECT，**BOM 展开必需**） |
| quantity | numeric(18,4) | 是 | 用量，默认 1 |
| unit | varchar(16) | 否 | 单位 |
| ref_des | varchar(255) | 否 | 位号（如 R1,R2,C3） |
| position | varchar(64) | 否 | 位置 / 装配位 |
| is_critical | boolean | 是 | 是否关键件，默认 false |
| notes | text | 否 | 备注 |
| substitute_group | varchar(64) | 否 | **替代料组标签**（同组候选可互换），如 `SG-SEL-<agent_run_id>`；受控扩展字段，见 ADR-0012 |
| created_at | timestamptz | 是 | 创建时间 |
| updated_at | timestamptz | 是 | 更新时间 |

> **补录说明（2026-10-05，D6-R3 受控扩展）**：`substitute_group` 为 **post-D2-freeze 受控扩展字段**——D12 覆盖要求明文含「替代料组」、D13 演示「替代可行项」依赖组语义，而原 §10 遗漏该载体；经人工裁决按 D2 先例（`Part.lifecycle_status` 拆分，`core/0003`）受控添加。类型 / 长度对齐同域 `position`（`varchar(64)`）、`blank=True default=""`、**无唯一约束、无索引**。**仅新增、不删改既有字段**，依据见 `docs/adr/0012-bom-selection-agent.md`。

---

## 11. InventoryLot（库存批次 / 序列）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| project_id | bigint | 是 | FK → Project（CASCADE） |
| part_id | bigint | 是 | FK → Part（PROTECT），所属物料 |
| serial_type | varchar(8) | 是 | lot / serial，默认 lot |
| serial_number | varchar(100) | 是 | **业务编号**（批次号 / 序列号），项目内唯一，如 `SN-DEMO-001` / `LOT-DCDC-001` |
| quantity | numeric(18,4) | 是 | 入库数量 |
| qty_available | numeric(18,4) | 是 | 可用数量 |
| location | varchar(100) | 否 | 库位 |
| status | varchar(16) | 是 | available / allocated / consumed / scrapped，默认 available |
| received_at | timestamptz | 否 | 到货时间 |
| created_at | timestamptz | 是 | 创建时间 |
| updated_at | timestamptz | 是 | 更新时间 |

> 来源采购单通过 `TraceLink`（`InventoryLot → PurchaseOrder`, `sourced_from`）表达；被测关系通过 `InventoryLot → TestRun`（`tested_by`）。
> - **`serial_number` 语义（R9）**：单字段同时承载「批次号」与「序列号」，由 `serial_type ∈ {lot, serial}` 区分类型（批次号如 `LOT-DCDC-001`、序列号如 `SN-DEMO-001`）；二者共享同一命名空间，在 `(project_id, inventory_lot)` 内唯一。`/trace/serial/<sn>/` 的 `<sn>` **接受两类取值**，先按 `serial_number` 定位，未命中即 `found=false` 空链（`serial_not_found`）；**不新增 `lot_no` 字段**。

---

## 12. WorkOrder（工单）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| project_id | bigint | 是 | FK → Project（CASCADE） |
| code | varchar(64) | 是 | **业务编号**（工单号），项目内唯一，如 `WO-001` |
| bom_id | bigint | 是 | FK → Bom（PROTECT），工单依据的 BOM |
| quantity | numeric(18,4) | 是 | 计划数量 |
| status | varchar(16) | 是 | planned / in_progress / completed / cancelled，默认 planned |
| due_date | date | 否 | 计划完成日 |
| created_by_id | bigint | 否 | FK → User（SET NULL） |
| created_at | timestamptz | 是 | 创建时间 |
| updated_at | timestamptz | 是 | 更新时间 |

---

## 13. PurchaseOrder（采购单）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| project_id | bigint | 是 | FK → Project（CASCADE） |
| po_number | varchar(64) | 是 | **业务编号**（采购单号），项目内唯一，如 `PO-001` |
| supplier_id | bigint | 是 | FK → Supplier（PROTECT） |
| status | varchar(16) | 是 | draft / open / partial / received / closed / cancelled，默认 draft |
| order_date | date | 否 | 下单日 |
| expected_date | date | 否 | 预计到货日（齐套计算用） |
| currency | varchar(8) | 否 | 币种，默认 CNY |
| total_amount | numeric(18,4) | 否 | 总金额 |
| notes | text | 否 | 备注 |
| created_at | timestamptz | 是 | 创建时间 |
| updated_at | timestamptz | 是 | 更新时间 |

> 采购明细（物料、数量、单价）通过 `TraceLink`（`Part → PurchaseOrder`, `ordered_by`）关联，明细数量 / 单价存于 `TraceLink.metadata`。本实体不新增行明细表。

---

## 14. TestCase（测试用例）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| project_id | bigint | 是 | FK → Project（CASCADE） |
| code | varchar(64) | 是 | **业务编号**（用例编号），项目内唯一，如 `TC-001` |
| name | varchar(300) | 是 | 用例名称 |
| description | text | 否 | 描述 |
| test_type | varchar(32) | 否 | electrical / thermal / emc / environmental / functional |
| precondition | text | 否 | 前置条件 |
| expected | text | 否 | 预期结果 |
| status | varchar(16) | 是 | active / deprecated，默认 active |
| created_at | timestamptz | 是 | 创建时间 |
| updated_at | timestamptz | 是 | 更新时间 |

> 与需求的关联通过 `TraceLink`（`Requirement → TestCase`, `verified_by`）表达。

---

## 15. TestRun（测试执行）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| project_id | bigint | 是 | FK → Project（CASCADE） |
| test_case_id | bigint | 是 | FK → TestCase（CASCADE，**层级归属**） |
| run_no | varchar(64) | 是 | **业务编号**，项目内唯一，如 `TR-001`（新增；`/test-runs/` 端点与 `TraceLink` 目标） |
| sample_serial | varchar(100) | 否 | 被测样机 / 批次序列号的冗余快照（权威在 InventoryLot） |
| result | varchar(16) | 是 | pass / fail / blocked / skipped |
| tested_at | timestamptz | 否 | 测试时间 |
| tester_id | bigint | 否 | FK → User（SET NULL） |
| data | json | 否 | 测量数据 |
| notes | text | 否 | 备注 |
| created_at | timestamptz | 是 | 创建时间 |
| updated_at | timestamptz | 是 | 更新时间 |

> 被测批次关系通过 `TraceLink`（`InventoryLot → TestRun`, `tested_by`）表达，不设 `inventory_lot_id` FK。

---

## 16. ECN（工程变更）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| project_id | bigint | 是 | FK → Project（CASCADE） |
| ecn_number | varchar(64) | 是 | **业务编号**（变更单号），项目内唯一，如 `ECN-001` |
| title | varchar(300) | 是 | 变更标题 |
| description | text | 否 | 变更说明 |
| change_type | varchar(32) | 否 | design / material / process / documentation |
| status | varchar(16) | 是 | draft / reviewing / approved / rejected / implemented，默认 draft |
| requested_by_id | bigint | 是 | FK → User（PROTECT），发起人 |
| approved_by_id | bigint | 否 | FK → User（SET NULL），批准人 |
| approved_at | timestamptz | 否 | 批准时间 |
| effective_date | date | 否 | 生效日期 |
| agent_run_id | bigint | 否 | FK → AgentRun（SET NULL），影响分析智能体调用 |
| created_at | timestamptz | 是 | 创建时间 |
| updated_at | timestamptz | 是 | 更新时间 |

---

## 17. ECNImpact（变更影响明细）

> 影响分析的**计算结果明细**：随 ECN 级联删除、可重算。属 PRD §6.1**「计算明细例外」**——可持临时多态引用用于计算与展示；经人工确认后必须另写 `TraceLink`（`ECN → 目标`, `affects`）作为**唯一审计追溯记录**。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键（内部） |
| ecn_id | bigint | 是 | FK → ECN（CASCADE，**层级归属**） |
| affected_type | varchar(32) | 是 | bom_item / inventory_lot / purchase_order / test_case / part |
| affected_id | varchar(64) | 是 | 受影响对象的**业务编号**（多态，R2；非数据库主键） |
| impact_type | varchar(32) | 否 | affected / blocked / replace_required |
| description | text | 否 | 影响说明 |
| created_at | timestamptz | 是 | 创建时间 |

---

## 18. TraceLink（追溯元数据，多态）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| project_id | bigint | 是 | FK → Project（CASCADE） |
| from_type | varchar(32) | 是 | 源实体类型（如 requirement / part） |
| from_id | varchar(64) | 是 | 源实体**业务编号**（R2；非数据库主键） |
| to_type | varchar(32) | 是 | 目标实体类型 |
| to_id | varchar(64) | 是 | 目标实体**业务编号**（R2；非数据库主键） |
| relation_type | varchar(32) | 是 | 关系语义，见 `er_diagram.md` 枚举 |
| source | varchar(16) | 是 | manual / agent / import，默认 manual |
| confidence | numeric(5,4) | 否 | 智能体置信度（0–1） |
| agent_run_id | bigint | 否 | FK → AgentRun（SET NULL），产出该链的智能体调用 |
| confirmed_by_id | bigint | 否 | FK → User（SET NULL），人工确认人 |
| confirmed_at | timestamptz | 否 | 人工确认时间 |
| evidence | json | 否 | 证据引用列表（`SourceRef[]`：`type`/`id`/`locator`/`snippet`），指向文件 / Git 提交 / 业务记录，用于防幻觉核验 |
| metadata | json | 否 | 附加信息（数量、单价、快照等） |
| created_by_id | bigint | 否 | FK → User（SET NULL），创建人（审计留痕） |
| created_at | timestamptz | 是 | 创建时间 |

> 唯一约束：`(project_id, from_type, from_id, to_type, to_id, relation_type)`。未经人工确认的智能体链以 `confirmed_by_id IS NULL` 标识，不进入正式追溯展示。

---

## 19. Document（文件）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| project_id | bigint | 是 | FK → Project（CASCADE） |
| doc_no | varchar(64) | 是 | **业务编号**，项目内唯一，如 `DOC-001`（新增） |
| title | varchar(300) | 是 | 标题 |
| doc_type | varchar(32) | 是 | drawing / prd / sor / email / test_report / other |
| file_path | varchar(500) | 是 | 平台内存储相对路径 |
| source_path | varchar(500) | 否 | 原始文件路径（只读来源） |
| mime_type | varchar(100) | 否 | MIME 类型 |
| size_bytes | bigint | 否 | 文件大小 |
| checksum | varchar(64) | 否 | SHA-256，用于去重与完整性校验 |
| is_readonly | boolean | 是 | 恒为 true（只读约束） |
| uploaded_by_id | bigint | 否 | FK → User（SET NULL） |
| created_at | timestamptz | 是 | 创建时间 |

> 与业务对象的关联通过 `TraceLink` 表达，文件本体的源文件只读、不回写。

---

## 20. GitRepo（Git 仓库）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| project_id | bigint | 是 | FK → Project（CASCADE） |
| name | varchar(200) | 是 | 仓库名，项目内唯一 |
| local_path | varchar(500) | 是 | 本地只读路径 |
| url | varchar(500) | 否 | 远程地址（仅记录，不写操作） |
| default_branch | varchar(100) | 否 | 默认分支 |
| is_readonly | boolean | 是 | 恒为 true（只读约束） |
| created_at | timestamptz | 是 | 创建时间 |
| updated_at | timestamptz | 是 | 更新时间 |

---

## 21. GitCommit（Git 提交）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键 |
| repo_id | bigint | 是 | FK → GitRepo（CASCADE，**层级归属**） |
| project_id | bigint | 是 | FK → Project（CASCADE），冗余便于跨仓库查询 |
| sha | varchar(40) | 是 | **业务编号**（提交 SHA），仓库内唯一 |
| author_name | varchar(100) | 否 | 作者 |
| author_email | varchar(254) | 否 | 作者邮箱 |
| committed_at | timestamptz | 否 | 提交时间 |
| message | text | 否 | 提交信息 |
| branch | varchar(100) | 否 | 分支 |
| created_at | timestamptz | 是 | 采集时间 |

> 与业务对象的关联通过 `TraceLink`（`GitCommit → *`, `evidences`）表达。

---

## 22. AgentRun（智能体调用审计）

> **AgentRun 只对应实际发生的 LLM 调用（R1）**：无 LLM 调用（短路返回 / 纯 DB 查询 / LLM 前的输入校验失败）不产生记录；LLM 已调用但输出非法则记 `status=failed`。字段全集以 `docs/interface_contract.md` §6 与 `schemas/agent_outputs.py` 为唯一权威。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | bigint | 是 | 主键（内部，不对外） |
| project_id | bigint | 是 | FK → Project（CASCADE） |
| agent_name | varchar(32) | 是 | requirement / bom_selection / traceability |
| status | varchar(16) | 是 | failed / needs_review / success / rejected（固定四值，R1；绑定规则见 `interface_contract.md` §6） |
| prompt_id | varchar(100) | 是 | 提示词标识 |
| prompt_version | varchar(32) | 是 | 提示词版本 |
| model | varchar(64) | 是 | 模型标识 |
| temperature | numeric(3,2) | 是 | 采样温度（0.00–2.00） |
| input_json | json | 是 | 调用输入（原始，Django JSONField） |
| input_hash | varchar(64) | 是 | 输入 SHA-256（64 位十六进制），用于复现与去重 |
| output_json | json | 否 | LLM 输出；解析失败时为 null |
| output_schema_valid | boolean | 否 | 输出是否通过 Pydantic schema 校验 |
| reference_check_passed | boolean | 否 | 引用存在性核验是否通过；null=未执行到核验步骤，false=核验失败 |
| invalid_references | json | 否 | 核验失败条目 `[{entity_type, entity_id, reason}]`，reason ∈ not_found / wrong_project / unknown_type / ambiguous |
| references | json | 否 | 引用来源（`SourceRef[]`，业务编号），防幻觉 |
| confirmed_by_id | bigint | 否 | FK → User（SET NULL），确认人（读契约字段 `confirmed_by`） |
| confirmed_at | timestamptz | 否 | 确认时间 |
| error | text | 否 | 失败信息 |
| created_at | timestamptz | 是 | 创建时间 |

---


## 附：类型 → Django ORM 映射

| PostgreSQL | Django 字段 |
| --- | --- |
| bigint（自增） | `BigAutoField` |
| bigint（外键） | `ForeignKey(to=..., on_delete=...)` |
| varchar(n) | `CharField(max_length=n)` |
| text | `TextField()` |
| boolean | `BooleanField()` |
| integer | `IntegerField()` |
| numeric(p,s) | `DecimalField(max_digits=p, decimal_places=s)` |
| timestamptz | `DateTimeField()` |
| date | `DateField()` |
| json | `JSONField()` |

# Threadlink

面向中小机电研发团队的单租户轻量研发追溯平台：以 TraceLink 追溯元数据为主线管理需求、BOM、测试、库存、采购与 ECN，只读关联 Git 与文件，并用可审计的 AI 智能体辅助物料选型与全链路追溯。

## Must（必须做）

1. 单租户登录 + 项目管理。
2. 核心实体：需求、参数、BOM、物料、供应商、库存批次、采购单、测试、ECN、文件、Git 提交、追溯元数据。
3. TraceLink 追溯元数据表，所有关联都走它。
4. Requirement Agent：PRD/SOR/邮件 → 需求卡 → 人工确认 → 写追溯链。
5. BOM/选型 Agent：参数过滤 + 规则评分 + LLM 解释 → 候选料/初版 BOM。
6. Traceability Agent：序列号/批次/样机 → 反查需求、图纸、物料、采购、测试、ECN、Git。
7. Git 与文件只读关联。
8. AgentRun 审计：每次智能体调用记录输入、输出、引用、确认人。

## Won't（明确不做）

- 真实 ERP/MES/供应商 API。
- CAD/EDA 文件深度解析。
- 多租户、复杂 RBAC。
- 自动下单、自动发邮件、自动改 BOM。
- 自主多智能体循环。
- 模型微调。

## 最小数据模型

- 项目与用户：`Project`, `User`
- 物料与供应：`Part`, `PartParam`, `Supplier`, `SupplierPart`
- 需求：`Requirement`, `RequirementParam`
- BOM：`Bom`, `BomItem`
- 库存与采购：`InventoryLot`, `WorkOrder`, `PurchaseOrder`
- 测试：`TestCase`, `TestRun`
- 变更：`ECN`, `ECNImpact`
- 追溯与文档：`TraceLink`, `Document`
- Git：`GitRepo`, `GitCommit`
- 智能体：`AgentRun`, `KnowledgeItem`

## 技术栈

- Django + Django Admin/HTMX
- SQLite/PostgreSQL
- pgvector/Chroma
- OpenAI SDK
- GitPython
- pdfplumber
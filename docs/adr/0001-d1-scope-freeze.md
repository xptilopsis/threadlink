# ADR-0001：D1 范围冻结（Must/Won't、技术栈、TraceLink 中心原则）

| 项 | 内容 |
| --- | --- |
| 状态 | 已接受（Accepted） |
| 日期 | 2026-10-04 |
| 里程碑 | D1（范围冻结） |
| 关联 | `docs/PRD.md` §2/§6 · `README.md` · `docs/tech_stack.md` · `docs/milestone.md` · R3 |

## 背景

D1 需冻结项目范围与技术栈，作为 D2–D14 的基线。若不冻结，后续实现易被「顺手加功能」侵蚀，尤其是多租户、真实外部系统集成、自主智能体循环等高风险方向。

## 决策

### 1. Must（必须做）

- 单租户登录 + 项目管理；
- 核心实体：需求、参数、BOM、物料、供应商、库存批次、采购单、测试、ECN、文件、Git 提交、追溯元数据；
- **TraceLink 追溯元数据表，所有跨域关联都走它**；
- Requirement Agent：PRD/SOR/邮件 → 需求卡 → 人工确认 → 写追溯链；
- BOM/选型 Agent：参数过滤 + 规则评分 + LLM 解释 → 候选料/初版 BOM；
- Traceability Agent：序列号/批次/样机 → 反查需求、图纸、物料、采购、测试、ECN、Git；
- Git 与文件只读关联；
- AgentRun 审计：凡经 LLM 推理的调用记录输入、输出、引用、确认人；**纯数据查询不产生 AgentRun**。

### 2. Won't（明确不做）

- 真实 ERP/MES/供应商 API；
- CAD/EDA 文件深度解析；
- 多租户、复杂 RBAC；
- 自动下单、自动发邮件、自动改 BOM；
- 自主多智能体循环；
- 模型微调。

> 「自动改 BOM」的例外：ECN **生效经人工确认后**的正式 BOM 变更**属于 Must**（R6）；被禁止的是**无人工确认的静默写入**。

### 3. 技术栈冻结

- Django + Django Admin/HTMX；单租户；
- SQLite（演示/测试默认）与 PostgreSQL（正式部署目标）；**golden tests 默认在 SQLite 运行，不依赖 PG/pgvector**（R5）；
- OpenAI SDK（LLM 调用）、GitPython（Git 只读）、pdfplumber（PDF 解析）；
- 向量库/检索（pgvector/Chroma 等）**预留但不纳入 D1–D14**。

### 4. TraceLink 中心原则（R3）

- **TraceLink 是跨域追溯的唯一权威**：跨域、需审计、多对多的追溯关系一律用它承载；
- 层级 / 包含 / 归属 / 计算强依赖用 FK 承载；**FK 不构成追溯声明**；
- `TraceLink`/`ECN`/`Document`/`AgentRun` 等审计相关实体不做物理删除，用状态位留痕。

## 后果

- 正向：范围与技术栈清晰，D2–D14 有稳定基线；TraceLink 中心原则避免追溯语义散落各表。
- 负向 / 成本：单租户与「不做」清单限制了通用性；跨域关系必须经 TraceLink，实现时需统一入口。
- 本 ADR 不写业务逻辑、不做迁移、不改数据库。
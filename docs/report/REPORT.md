# ThreadLink 报告骨架（D13-R2）

> 用途：为最终报告提供**结构 + 引用索引 + 篇幅预算**；每节先给要点（≈1–2 段话素材量），
> 最终成文时按要点展开，正文数字一律回引 `docs/qa/*` 与 `docs/adr/*`，不在此处重复。
> 前置 HEAD：`4d6817d`。

---

## 1. 背景与问题 　（预算 ≈1 段 / 150–250 字）

- 面向中小机电研发团队：需求、BOM、测试、库存、采购、ECN 分散，追溯链断裂。
- 目标：以 **TraceLink** 追溯元数据为主线，把跨域关系收敛到单一边表。
- AI 定位：**可审计的辅助**（选型/追溯/需求提取），**不自动改 BOM、不下单、不发邮件**。
- 引用：`docs/PRD.md`、ADR-0001。

## 2. 范围（Must / Won't 摘要） 　（预算 ≈1 段 + 一张表）

- Must：单租户登录 + 项目；核心实体；**TraceLink 中心**；三 Agent；Git/文件只读；AgentRun 审计。
- Won't：真实 ERP/MES/供应商 API、CAD/EDA 深度解析、多租户/复杂 RBAC、自动写库、多智能体自主循环、微调。
- 引用：`docs/PRD.md`、`README.md`「Must / Won't」、ADR-0001。

## 3. 总体架构 　（预算 ≈1 段 + 图）

- 分层：角色 → Admin+HTMX / 受限 HTTP 端点 → 服务层 → 数据层 + 外部。
- 服务层三类：**确定性计算**（planning / selection）、**写路径**（ecn / confirmation）、**LLM 管道**（agents）。
- 引用：`docs/architecture/README.md` §1（系统总览图）。

## 4. 数据模型与 TraceLink 中心原则 　（预算 ≈1 段 + 图）

- **强结构关系用 FK；跨域追溯用 `TraceLink` 多态边**（`from_id`/`to_id` = 业务编号）。
- 端点 = `EntityType` **13 类白名单**；审计记录（AgentRun/TraceLink）与明细表不作端点。
- 业务编号体系见 `docs/data_dictionary.md` §0.1；唯一约束 = 全元组。
- 引用：`docs/er_diagram.md`（完整 ER）、`docs/architecture/README.md` §2、ADR-0002、ADR-0009。

## 5. 三大 Agent 设计 　（预算 ≈2 段）

- 共用管道：输入 → prompt 装载 → `call_json` → Pydantic → 引用核验 → AgentRun。
- **requirement**：邮件/PRD → 需求卡 → 人工确认写 Requirement + TraceLink。
- **bom_selection**：引擎权威出候选择序，LLM 只写 `rationale`/`summary`/`replaces` 建议。
- **traceability**：链结构 DB 权威，LLM 只写中文 `summary` + `trace_refs`；未命中**短路**（零 LLM / 零 AgentRun）。
- 统一 `output_json` 落冻结 schema（可再解析，D6 教训）。
- 引用：`docs/architecture/README.md` §3、ADR-0012、ADR-0013、`docs/qa/2026-10-05-d5-closeout.md`、`2026-10-05-d6-closeout.md`、`2026-10-06-d7-closeout.md`。

## 6. 关键工程决策（ADR 索引） 　（预算 = 一张 17 行表）

| 编号 | 标题 | 一句话 |
| --- | --- | --- |
| 0001 | D1 范围冻结 | Must/Won't、技术栈、TraceLink 中心原则 |
| 0002 | 空链语义 + 引用核验 + R1 AgentRun 边界 | `found`/`complete` 准正交 + 四值状态 |
| 0003 | User.role 改职能枚举 | 权限档位 → 职能（engineer/procurement/test/quality） |
| 0004 | 批次 1–2 契约修订 | 19 条自检 + 四项开放决策 + R1–R9 硬约束 |
| 0005 | BOM 选型评分 v1 冻结 | 两阶段模型 + 权重/归一化/ tie-break |
| 0006 | D2 模型归属与编号 | app 归属映射 + 业务编号生成策略 |
| 0007 | D2 schema 实现注记 | §6 补录 + 承重字段全量排查 |
| 0008 | LLM 测试分层与 live 策略 | T1–T4 + provider 自适应结构化 + 推理档位 |
| 0009 | 文档摄取路径语义修正 | 「创建≠修改」，Document add 放开、change/delete 禁 |
| 0010 | 人工确认流程 | approve/reject 四值状态机 + 事务/幂等 |
| 0011 | BOM 选型引擎 | 确定性评分口径冻结（`core/selection.py`） |
| 0012 | BOM 选型解释层 | 引擎权威 + LLM 只写解释；`BomItem.substitute_group` 受控扩展 |
| 0013 | 追溯链解释层 | DB 权威链 + LLM summary；未命中短路；**纯审计确认** |
| 0014 | 展开 + 齐套 | BOM 多级展开 / 工单齐套，确定性零 LLM；`ordered_by.metadata.quantity` 承重 |
| 0015 | ECN 影响 + 应用 | `ECNImpact` 权威 + 唯一写路径（补 `affects` 边 + 写回 `BomItem.part`） |
| 0016 | role 写权限 | 轻量 `role → 可写实体集`，仅 Admin 写路径，不引入新权限引擎 |
| 0017 | D12 追溯缺口 | evidence 补录 / 断点 token / depth·direction / confirmed 过滤 |

- 引用：`docs/adr/0001…0017`。

## 7. 测试与验证 　（预算 ≈2 段 + 一张矩阵索引）

- **GT 覆盖**：38/38 覆盖，逐条映射见 `docs/qa/2026-10-07-d12-gt-coverage-matrix.md`。
- **分层**：live（真打）/ transport（HTTP 边界）/ craft（构造）/ fake（离线回放），见 ADR-0008。
- **审计不变量**：四值 + 绑定字段（`tests/test_audit_r3.py`）；权限矩阵（`tests/test_permissions_r3.py`）；异常注入不 500（`tests/test_admin_errors_r3.py`）。
- **非 live 基线**：D12 收口 `232 passed`（D13-R1 后）；`check` 通过；`makemigrations --check` = No changes。
- 引用：`docs/golden_tests.md`（冻原）、`docs/qa/*-closeout.md`、复检记录 `docs/qa/2026-10-04-d1-recheck*.md`。

## 8. 演示 　（预算 ≈1 段）

- 15 分钟 9 段脚本：只读在前 → ECN 应用（倒数第二）→ 决策线（段 9）。
- 生成线 / 决策线分离；决策线固定 runs 6/7/8（`6 approve → 8 reject → 7 保留`）。
- 演示库可确定性重建（`scripts/demo_reset.ps1`）。
- 引用：`docs/demo/RUNBOOK.md`、`docs/qa/2026-10-08-d13-r1-evidence.md`。

## 9. 局限与未来工作 　（预算 ≈1 段 + 台账索引）

- 已知局限：LLM 非确定性（措辞/priority 跨次差异，接受不追）；无快照模型 id（R-3）；自动影响面推导未做。
- 未来工作（v2 / 不做项）见 `docs/DEFERRED.md`。
- 引用：`docs/DEFERRED.md`、ADR-0015「已知局限」、ADR-0008「风险登记」。

## 10. 附录 　（预算 = 三张索引表）

### 10.1 tag 索引

`d1-scope-freeze` / `d2-schema-freeze` / `d3-crud-freeze` / `d4-trace-freeze` / `d5-agent-freeze` /
`d6-selection-freeze` / `d11-e2e-freeze` / `d12-tests-freeze`（D7 `d7-agent-freeze` 未打，见 `docs/qa/2026-10-06-d7-closeout.md`）。

### 10.2 提交链（关键节点）

`…` → `15c733c`（D6-R1 引擎）→ `abc3d75`（D6-R2）→ `72320bf`（D6-R3）→ `e5b94b1`（`d6-selection-freeze`）→
`b590243`（D7-R1）→ `5353d3d`（D7-R2）→ `ef4900f`（D7-R3）→ `56f4c4e`/`61f27c6`/`9b931c1`/`d234eb2`/`ed75e29`（D11）→
`aca115e`…`1f49b21`（D12，`d12-tests-freeze`）→ `6a3f4b2`…`4d6817d`（D13-R1）。

### 10.3 qa 报告索引

`docs/qa/2026-10-04-d1-recheck.md`、`2026-10-04-d1-recheck-incremental.md`、`2026-10-05-d3r2-history-rewrite.md`、
`2026-10-05-d4-closeout.md`、`2026-10-05-d5-closeout.md`、`2026-10-05-d6-closeout.md`、`2026-10-06-d7-closeout.md`、
`2026-10-07-d11-closeout.md`、`2026-10-07-d12-closeout.md`、`2026-10-07-d12-gt-coverage-matrix.md`、
`2026-10-08-d13-r1-evidence.md`。
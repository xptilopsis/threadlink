# ADR-0004：批次 1–2 契约修订记录（自检 19 条 + 四项开放决策 + T2.11 编号统一）

| 项 | 内容 |
| --- | --- |
| 状态 | 已接受（Accepted） |
| 日期 | 2026-10-04 |
| 里程碑 | D1（范围冻结） |
| 关联 | 提交 `9f57f7d` · `docs/data_dictionary.md` §0.1/§1 · `docs/interface_contract.md` · `docs/golden_tests.md` · `docs/PRD.md` · `schemas/agent_outputs.py` · `fixtures/demo_seed.json` · `scripts/validate_seed.py` · ADR-0001/0002/0003/0005 |

## 背景

D1 契约经两类来源修订，均已人工裁决、无需重新论证：

- **来源 A**：上轮两项契约决策（空链语义、引用存在性核验）；
- **来源 B**：developer-test **自检报告 19 条** + **4 项开放决策**。

据此形成全批次硬约束 **R1–R9**，并落地批次 1–2 任务。本 ADR 记录批次 1–2 的修订全貌，作为变更追溯入口；细则以各源文档为准。

## 决策

### 1. 四项开放决策

| # | 决策 | 处置 |
| --- | --- | --- |
| ① | KnowledgeItem / RAG | 列入 PRD §2 非目标，并从契约、数据字典、ER、种子、schemas 全部移除；`docs/tech_stack.md` 的向量库相关行标注「预留，不纳入 D1–D14」但不删行 |
| ② | `User.role` | **修正**：由权限档位三值 `admin/engineer/viewer` 改为**职能枚举** `admin/engineer/procurement/test/quality`（PRD §3 为权威，与 fixtures 取并集）；详见 ADR-0003 |
| ③ | 选型评分口径 | D1 冻结硬过滤清单、加权和公式形态与 v1 权重，由版本化规则文件 `rules/bom_scoring.v1.json` 承载，golden test 锁定排序结果；**修正**：voltage/current/temp/ip 由「评分维度」改判为「硬过滤门槛」，不再参与排序（两阶段口径见批次 3 §C） |
| ④ | 向量库（pgvector/Chroma 等） | 同①：标注预留、不纳入 D1–D14；不得出现「测试必须依赖 PG/pgvector」表述 |

### 2. 批次 1–2 任务与落地

| 任务 | 内容 | 主要落点 |
| --- | --- | --- |
| T2.0 | 新增 `scripts/validate_seed.py` 种子契约校验 | `scripts/validate_seed.py` |
| T2.1 | 移除 KnowledgeItem / RAG | 契约 / 字典 / ER / 技术栈 / 种子 / schemas / README / 依赖 |
| T2.2 / T2.3 | `TraceLink.created_by_id` + `evidence`（`SourceRef[]`） | data_dictionary / interface_contract / schemas |
| T2.4 | `User.role` 冻结为职能枚举 | data_dictionary §1 / PRD §3 / ADR-0003 |
| T2.5 | `BomCandidate.replaces_part_id` 注明业务编号（R2） | schemas / 契约 |
| T2.6 | ECN 影响分析 / 正式应用两阶段措辞（去「自动改 BOM」） | golden_tests §2 / PRD |
| T2.7 | golden tests 运行环境 = SQLite | golden_tests §0 |
| T2.11 | 全实体业务编号统一（`id == 编号字段`，R8）+ R7/R8/R9 + `serial_number` 语义 | data_dictionary §0.1 / fixture / validate_seed |

> 批次 1 另含空链语义落地、AgentRun 字段统一、PRD §6.1 例外句、ECNImpact 例外句（T1.3）、标识约定与 AgentRun 触发边界等（见 ADR-0002 与 `docs/data_dictionary.md` §0.1）。

### 3. 派生硬约束 R1–R9

- **R1** AgentRun 只对应真实 LLM 调用；`status` 四值及 `confirmed_by/at` 绑定规则；
- **R2** 业务编号为唯一对外标识，DB 主键不暴露；多态引用目标须为有业务编号的实体（`EntityType` 白名单 13 项）；
- **R3** TraceLink 为跨域追溯唯一权威；FK 不构成追溯声明；
- **R4** JSON 按 `JSONField` 描述，不写 `jsonb`；
- **R5** golden tests 默认 SQLite，不依赖 PG/pgvector；
- **R6** 人工确认为正式流程；LLM 输出未确认不得写入正式实体；ECN 两阶段；
- **R7** 一个实体一个业务编号字段，以被外部契约承重的取值为准；
- **R8** fixture 条目 `id == 业务编号字段`，`validate_seed` 强制断言；
- **R9** 编号稳定、可读、带类型前缀，解析统一为 `(project_id, entity_type, business_no)`。

### 4. 自检 19 条

`developer-test` 自检报告 **19 条**的整改已按类别并入上表任务与 R1–R9（审计边界、空链语义、引用核验、编号统一、JSONField/SQLite、人工确认两阶段、枚举/角色等）。该 19 条原始清单未随仓库持久化，其**整改结论**以 R1–R9 与上述任务为准。

## 偏差与待确认

- **任务编号**：批次指令提及「T2.9/T2.10」，但批次 1–2 实际交付的任务编号为 **T2.0–T2.7、T2.11**（见提交 `9f57f7d` 消息）。本 ADR 按实际编号记录「T2.9/T2.10」缺失/未使用，作为偏差项上报人工确认。
- **状态语义映射**：`interface_contract` §6 已落地 `failed/needs_review/success/rejected` 四值语义映射与 `confirmed_by/confirmed_at` 绑定规则，经 D1 收尾批逐条核对**确认与 R1 一致**，无需再改。
- **OI-6 处置**：选型评分硬过滤通过者为 **0**（AC-004 不可满足），经 D1 收尾批裁决为「补齐 fixture 关键参数（人工放行修数据）」；评分口径冻结、演算基线与规则状态见 **ADR-0005**。

## 后果

- 正向：批次 1–2 修订可追溯、有明确来源与落点；R1–R9 为后续批次提供硬约束。
- 负向 / 成本：`validate_seed.py` 需随 fixture 演进维护断言；`EntityType` 白名单需与 schemas、validate_seed 三处保持一致。
# D12-R1：全量 GT 覆盖矩阵 + JSON 组缺口盘点（只读）

- **日期**：2026-10-07
- **前置**：HEAD=`ed75e29`（D11 补证提交）、工作区干净
- **性质**：**只读盘点**（不改 `docs/golden_tests.md`、不写测试、不改代码）；本文件即本轮交付物
- **数据源**：`docs/golden_tests.md`（598 行，冻结原文）+ `tests/`（23 个测试文件）

---

## §1 全量 GT 覆盖矩阵

**总条目 38**（BOM 9 / KIT 8 / ECN 6 / JSON 8 / TRACE 7），与 `golden_tests.md` 附录「共 38 条」一致。

| GT | 分组 | 期望摘要（一行） | 实现测试（文件::用例） | 状态 |
| --- | --- | --- | --- | --- |
| GT-BOM-001 | BOM | 顶层 4 行、`depth=0`、`BI-004=2` | `test_planning_r1.py::test_gt_bom_001_top_level` | 有 |
| GT-BOM-002 | BOM | `include_hierarchy` 下 `BI-005` 叶子（`depth=1`/parent=`BI-001`） | `::test_gt_bom_002_leaf` | 有 |
| GT-BOM-003 | BOM | 工单 ×10：`PART-006=20`/`PART-010=120`/`PART-001=10` | `::test_gt_bom_003_work_order_scale` | 有 |
| GT-BOM-004 | BOM | 多路径同 part 汇总 = 8 | `::test_gt_bom_004_multi_path_totals` | 有 |
| GT-BOM-005 | BOM | `obsolete` 抛 `bom_not_releasable`；`draft` 附 warning | `::test_gt_bom_005_status` | 有 |
| GT-BOM-006 | BOM | 停产料行 `risk_flags` 含 `discontinued` | `::test_gt_bom_006_discontinued_flag` | 有 |
| GT-BOM-007 | BOM | 三层 `depth=2`、累计 20 | `::test_gt_bom_007_three_levels` | 有 |
| GT-BOM-008 | BOM | 构造集 80/50/10 排序 | `test_selection_r1.py::test_gt_bom_008_constructed_set` | 有 |
| GT-BOM-009 | BOM | fixture 全表 94.79/87.24/0.00 + 17 排除 | `::test_gt_bom_009_fixture_baseline` | 有 |
| GT-KIT-001 | KIT | 全满足 `shortages=[]`/`ready` | `test_planning_r1.py::test_gt_kit_001_ready` | 有 |
| GT-KIT-002 | KIT | `qty_available=80`、缺口 10；`allocated` 不计 | `::test_gt_kit_002_partial_occupancy` + `::test_gt_kit_002_allocated_excluded` | 有 |
| GT-KIT-003 | KIT | 最晚到货 `2026-03-20`、在途 70；不足/无在途边界 | `::test_gt_kit_003_transit_arrival` + `::test_gt_kit_003_transit_insufficient` | 有 |
| GT-KIT-004 | KIT | 替代可行项 `PART-002` | `::test_gt_kit_004_alternatives` | 有 |
| GT-KIT-005 | KIT | `discontinued` | `::test_gt_kit_005_discontinued_shortage` | 有 |
| GT-KIT-006 | KIT | `long_lead_time` | `::test_gt_kit_006_long_lead_time` | 有 |
| GT-KIT-007 | KIT | 缺料全字段 + `critical_shortage` | `::test_gt_kit_007_full_fields_and_critical` | 有 |
| GT-KIT-008 | KIT | 硬缺料 `latest=null`/`alternatives=[]`/`insufficient` | `::test_gt_kit_008_hard_shortage` + `::test_gt_kit_008_zero_transit_equiv_none` | 有 |
| GT-ECN-001 | ECN | 影响面 5 项 | `test_ecn_r2.py::test_gt_ecn_001_impact_scope` | 有 |
| GT-ECN-002 | ECN | (a) 分析零写；(b) 应用写回 + 边确认 | `::test_gt_ecn_002a_analysis_zero_write` + `::test_gt_ecn_002b_apply` | 有 |
| GT-ECN-003 | ECN | 状态门（`reviewing/draft/rejected` 不生效） | `::test_gt_ecn_003_status_gate` | 有 |
| GT-ECN-004 | ECN | 日期门 + `missing_effective_date` | `::test_gt_ecn_004_missing_effective_date` | 有 |
| GT-ECN-005 | ECN | 唯一约束 + 确认位 + NULL 语义 | `::test_gt_ecn_005_unique_and_confirmed` | 有 |
| GT-ECN-006 | ECN | 重算幂等 | `::test_gt_ecn_006_idempotent` | 有 |
| GT-JSON-001 | JSON | 合法输出通过（`BomSelectionAgentOutput`） | `test_llm_r1.py::test_live_connectivity_and_schema`（**live 最小 schema `Resp`**，非 `BomSelectionAgentOutput`）；**无 `validate_agent_output` 直调** | 部分 |
| GT-JSON-002 | JSON | 非法 JSON → `failed`/`output_schema_valid=false`/`output_json=null`/HTTP 422 | `test_llm_r1.py::test_transport_client_parse`（T2）+ `::test_live_truncation`（T1） | 部分（未断 `output_json=null`/422） |
| GT-JSON-003 | JSON | 缺必填字段 → `ValidationError`（`loc` 指向缺失字段） | `test_llm_r1.py::test_transport_schema_invalid`（T2，**类 `Strict` 缺 `ok`**，非具体模型） | 部分 |
| GT-JSON-004 | JSON | 未知字段（`extra="forbid"`）→ `extra_forbidden` | **无** | 无 |
| GT-JSON-005 | JSON | 幻觉 ID → `reference_check_passed=false`/`invalid_references` | `test_requirement_r2.py::test_verify_not_found/unknown_type/wrong_project/ambiguous` + `test_bom_selection_r2.py::test_pipeline_hallucinated_replaces_fails` + `test_traceability_agent_r1.py::test_pipeline_hallucinated_trace_ref_fails` | 有（较全） |
| GT-JSON-006 | JSON | 数值越界 / 枚举非法 → `ValidationError` | **无** | 无 |
| GT-JSON-007 | JSON | `Param` 取值一致性（6 组规则） | **无** | 无 |
| GT-JSON-008 | JSON | `agent_name` 映射路由 + 非法 `agent_name` 抛出 | **无**（`OUTPUT_MODELS`/`AgentName` 仅间接用于审计一致性回归） | 无 |
| GT-TRACE-001 | TRACE | 完整链路 31/37 + 每节点 `source_refs` 非空 + edge 语义 + `complete/missing=[]` | `test_d4_r3.py::test_demo_chain_complete`（未断 `source_refs`/edge relation 集合；commit 断言为 `e4738a67`，GT 点名 `c6b024f5`） | 部分 |
| GT-TRACE-002 | TRACE | 未确认链（`confirmed_by_id IS NULL`）过滤 | **无** | 无（**未实现**） |
| GT-TRACE-003 | TRACE | 查不到 → 200 + `found=false` 空链 + **零 LLM**/零 AgentRun/无新边 + 边界 | `::test_serial_not_found` + `::test_root_without_links`（边界1）+ `::test_read_only_no_agentrun` | 部分（未断零 LLM mock / `warnings` / 大小写规范化） |
| GT-TRACE-004 | TRACE | 每个 `TraceNode.source_refs` 非空且可核验 | **无** | 无 / **冲突**（见 §3 C1） |
| GT-TRACE-005 | TRACE | 断点写入 `missing`（如 `no_purchase_order`） | `::test_dangling_reference`（token = `unresolved_reference:part:PART-999`） | 部分 / **冲突**（见 §3 C2） |
| GT-TRACE-006 | TRACE | `depth`/`direction` 参数语义（含负值/非法 → 400） | **无** | 无（**未实现**，契约 §3.2 已标注，见 §3 C3） |
| GT-TRACE-007 | TRACE | `query_type="lot"` 批次反查 | **无** | 无 |

**分组计数**：BOM 9 / KIT 8 / ECN 6 / JSON 8 / TRACE 7 = **38**。

---

## §2 JSON 组专项盘点（重点）

冻原文要点：校验入口统一 `validate_agent_output(agent_name, payload)`；`extra="forbid"`；schema 校验与引用存在性核验**两步独立**（OI-2）。

| GT | 判定 | 已覆盖层 / 测试 | 缺口 | 分层建议（ADR-0008 R-2） | 预计用例 |
| --- | --- | --- | --- | --- | --- |
| GT-JSON-001 | **部分** | T1 live（`Resp` 最小模型连通+结构化）；**无** `validate_agent_output` 直调 | 未以 `BomSelectionAgentOutput` 断言"合法 dict → 实例、Decimal 解析、temperature 0.0/2.0" | **T3 craft**（`validate_agent_output` 直调合法 payload） | 1 |
| GT-JSON-002 | **部分** | T2 `test_transport_client_parse`（`ClientParseError`）；T1 `test_live_truncation` | 未断 `output_json=null`、`output_schema_valid=false`、HTTP 422、"合法 JSON 但非对象"边界 | **T1 live**（截断真造，补断言）+ **T2**（非对象 payload） | 1（T1）+1（T2） |
| GT-JSON-003 | **部分** | T2 `test_transport_schema_invalid`（类 `Strict` 缺 `ok`） | 未覆盖具体模型（`RequirementAgentOutput` 缺 `cards`、`BomCandidate` 缺 `lifecycle_status`/`rationale`）；`cards=[]` min_length；`nodes=[]` 的 `found` 不变量 | **T2 transport**（缺字段响应体）+ **T3 craft**（`cards=[]`/`nodes=[]` 不变量） | 2 |
| GT-JSON-004 | **无** | — | `extra="forbid"` 未知字段（`magic_score`/大小写不符）→ `extra_forbidden` | **T3 craft**（格式合法、字段非法 → T3） | 1 |
| GT-JSON-005 | **有** | T3 craft（`verify_*` 4 例）+ 两管道幻觉失败（bom/traceability） | （较全）`type` 不匹配、`confirmed=false` 不触发失败等边界可补 | 维持 T3 | 0–1 |
| GT-JSON-006 | **无** | — | `confidence=1.5`/`temperature=-0.1`/`lifecycle_status="unknown"`/`relation_type="foo"` 越界与非法枚举 | **T3 craft** | 1 |
| GT-JSON-007 | **无** | — | `Param` `model_validator` 6 组规则（`range` 缺 min/max、min>max、`gte/lte` 缺 `value_num`、`eq` 两类） | **T3 craft** | 1 |
| GT-JSON-008 | **无** | — | `validate_agent_output` 对 `requirement`/`bom_selection`/`traceability` 路由 + `unknown_agent` 抛出（不静默回退） | **T3 craft** | 1 |

**JSON 组缺口**：**7 条**（4 条"无"：004/006/007/008；3 条"部分"：001/002/003）；GT-JSON-005 已较全。
**分层建议**：新增 **T3 craft 6 条**（001/004/006/007/008 + 003 的不变量部分）、**T1 live 1 条**（002 断言补强）、**T2 transport 2 条**（002 非对象 + 003 缺字段）→ **预计 8–10 条新用例**，建议落点 `tests/golden/test_agent_output_schema.py`（golden_tests §7 建议文件，当前**不存在**）。
**映射规则（ADR-0008 R-2）复核**：非法 JSON / 截断 → 可 T1 live 真造（GT-JSON-002）；缺必需字段 / 格式合法但 ID 不存在 → T2/T3（live 层不可构造）（GT-JSON-003/004/006/007/008）—— 与本盘点一致。

---

## §3 汇总与冲突条目

### 3.1 汇总

| 状态 | 条数 | 明细 |
| --- | --- | --- |
| **有** | **24** | BOM 9 / KIT 8 / ECN 6 / JSON-005 |
| **部分** | **6** | JSON-001、JSON-002、JSON-003、TRACE-001、TRACE-003、TRACE-005 |
| **无** | **8** | JSON-004、JSON-006、JSON-007、JSON-008、TRACE-002、TRACE-004、TRACE-006、TRACE-007 |
| **合计** | **38** | — |

（其中 TRACE-004/005/006 兼属"冲突"类，见 3.2。）

### 3.2 ⛔ 冲突条目（GT 冻原 vs 实现/数据"期望不一致"，停下汇报）

> 定义：非"未实现/未覆盖"，而是**冻结期望与现存实现或基准数据直接矛盾**。

- **C1 · GT-TRACE-004（每节点 `source_refs` 非空）**
  - GT 要求：`SN-DEMO-001` 链**每个** `TraceNode.source_refs` 非空且可核验。
  - 数据事实：`fixtures/demo_seed.json` 的 `trace_links` **39 行、含 `evidence` 键 0 行**（D7-R2 §0.3 实测）→ D7-R2 的 evidence 聚合回填**无数据可聚合** → 演示链 `source_refs` **全为空**（D7-R2 生产库冒烟：0/31 非空）。
  - 且 `docs/interface_contract.md` §3.2 的**契约示例**本身含空 `source_refs`（如 `BOM-001` 节点 `source_refs: []`）——与 GT「每节点非空」亦不一致。
  - → **GT 期望无法在现基准数据下满足**（需裁决：补 fixture evidence / 修订 GT / 明确"非空"仅适用于证据链）。

- **C2 · GT-TRACE-005（断点 token `no_purchase_order`）**
  - GT + 契约 §2.5 L91 期望：链路断点写入 `missing`（如 `"no_purchase_order"`、`"no_test_run"`）。
  - 实现事实：`traceability/chain.py` 的断点 token = `unresolved_reference:{entity_type}:{business_no}`（D4 扩展词汇，chain.py L13/L39 自述"D4 扩展词汇，D7/D12 对账"）；测试 `test_dangling_reference` 断言的是该扩展 token。
  - → **token 词汇不一致**（GT 的 `no_purchase_order`/`no_test_run` 未实现，实际为 `unresolved_reference:*`）。

- **C3 · GT-TRACE-006（`depth`/`direction` 参数语义）**
  - GT 要求：`depth=0/2`、`direction=forward/backward` 生效；`depth` 负值 / `direction` 非法 → `400`。
  - 实现/契约事实：`chain.py` **无 `depth`/`direction` 参数**（固定 `MAX_DEPTH=20` 全链）；契约 §3.2 L96-97 明确 v1「**暂未实现——服务端忽略这两个参数、始终返回全链**」；D4 收口报告延后项 ⑥ 已裁决「**不在 D4 补实现**，登记 D7 统一定义与实现」，但 **D7（R1–R3）亦未实现**。
  - → **GT 冻结要求与契约 v1 现状不一致**，且 D4 登记的 D7 实现**未兑现**。

### 3.3 R2 工作项清单（D12-R2 缺口补齐建议）

| # | 工作项 | 归属 | 类型 |
| --- | --- | --- | --- |
| 1 | 新建 `tests/golden/test_agent_output_schema.py`：JSON-001/004/006/007/008 的 `validate_agent_output` 直调（T3）+ JSON-003 不变量（T3） | D12-R2 | 补测（无冲突） |
| 2 | JSON-002 补 T1 live 断言（`output_json=null`/`output_schema_valid=false`/HTTP 422）+ T2 非对象 payload | D12-R2 | 补测 |
| 3 | JSON-003 补 T2 具体模型缺字段（`RequirementAgentOutput`/`BomCandidate`） | D12-R2 | 补测 |
| 4 | TRACE-002 未确认链过滤（`confirmed_by_id IS NULL`）：确认是否需实现 + 补测 | **待裁决**（C? ） | 实现/裁决 |
| 5 | TRACE-004：`source_refs` 非空语义（C1） | **待裁决** | 冲突 |
| 6 | TRACE-005：`missing` token 词汇（C2） | **待裁决** | 冲突 |
| 7 | TRACE-006：`depth`/`direction` 实现与 `400` 语义（C3） | **待裁决** | 冲突 |
| 8 | TRACE-007：`query_type="lot"` 批次反查用例 | D12-R2 | 补测 |
| 9 | TRACE-001/003 断言补强（`source_refs`/edge relation 集合/零 LLM mock/`warnings`/大小写规范化） | D12-R2 | 补测 |

> 说明：GT-BOM-001…009、GT-KIT-001…008、GT-ECN-001…006 **全部"有"覆盖**（24 条中的 23 条），无缺口；JSON/TRACE 为缺口集中区。

---

## 附：盘点方法与边界声明

- **只读**：本轮不改 `docs/golden_tests.md`、不改代码/测试；仅新增本文件。
- **映射口径**：GT → 实现测试以"显式 GT 命名用例"优先，辅以关键字核验（`validate_agent_output`/`extra_forbid`/`confidence`/`Param`/`depth`/`direction`/`query_type`/`confirmed_by_id`）。
- **冲突判定**：仅当"冻结期望与实现/基准数据直接矛盾"判冲突；"未实现/未覆盖"判缺口（§3.3 工作项 1/2/3/8/9）。
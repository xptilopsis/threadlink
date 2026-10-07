# D12 全量 GT 覆盖矩阵（终稿 · D12-R3 定稿）

- **日期**：2026-10-07
- **前身**：D12-R1 只读盘点初稿（HEAD=`ed75e29`）；本稿为 **D12-R3 定稿**（HEAD 见收口报告）
- **数据源**：`docs/golden_tests.md`（冻原文）+ `tests/`（现有测试套件）
- **结论**：**38/38「有」**（BOM 9 / KIT 8 / ECN 6 / JSON 8 / TRACE 7）；R1 盘出的 3 条冲突（C1/C2/C3）已于 D12-R2/R3 处置，1 条默认语义偏差登记 ADR-0017。

---

## §1 全量 GT 覆盖矩阵（终稿）

**总条目 38**（BOM 9 / KIT 8 / ECN 6 / JSON 8 / TRACE 7），与 `golden_tests.md` 附录一致。

| GT | 分组 | 期望摘要（一行） | 实现测试（文件::用例） | 状态 |
| --- | --- | --- | --- | --- |
| GT-BOM-001 | BOM | 顶层 4 行、`depth=0`、`BI-004=2` | `test_planning_r1.py::test_gt_bom_001_top_level` | 有 |
| GT-BOM-002 | BOM | `include_hierarchy` 下 `BI-005` 叶子 | `::test_gt_bom_002_leaf` | 有 |
| GT-BOM-003 | BOM | 工单 ×10：`PART-006=20`/`PART-010=120`/`PART-001=10` | `::test_gt_bom_003_work_order_scale` | 有 |
| GT-BOM-004 | BOM | 多路径同 part 汇总 = 8 | `::test_gt_bom_004_multi_path_totals` | 有 |
| GT-BOM-005 | BOM | `obsolete` 抛 `bom_not_releasable`；`draft` warning | `::test_gt_bom_005_status` | 有 |
| GT-BOM-006 | BOM | 停产料 `risk_flags` 含 `discontinued` | `::test_gt_bom_006_discontinued_flag` | 有 |
| GT-BOM-007 | BOM | 三层 `depth=2`、累计 20 | `::test_gt_bom_007_three_levels` | 有 |
| GT-BOM-008 | BOM | 构造集 80/50/10 排序 | `test_selection_r1.py::test_gt_bom_008_constructed_set` | 有 |
| GT-BOM-009 | BOM | fixture 全表 94.79/87.24/0.00 + 17 排除 | `::test_gt_bom_009_fixture_baseline` | 有 |
| GT-KIT-001 | KIT | 全满足 `shortages=[]`/`ready` | `test_planning_r1.py::test_gt_kit_001_ready` | 有 |
| GT-KIT-002 | KIT | `qty_available=80`、缺口 10；`allocated` 不计 | `::test_gt_kit_002_partial_occupancy` + `::test_gt_kit_002_allocated_excluded` | 有 |
| GT-KIT-003 | KIT | 最晚到货 `2026-03-20`、在途 70；不足/无在途 | `::test_gt_kit_003_transit_arrival` + `::test_gt_kit_003_transit_insufficient` | 有 |
| GT-KIT-004 | KIT | 替代可行项 `PART-002` | `::test_gt_kit_004_alternatives` | 有 |
| GT-KIT-005 | KIT | `discontinued` | `::test_gt_kit_005_discontinued_shortage` | 有 |
| GT-KIT-006 | KIT | `long_lead_time` | `::test_gt_kit_006_long_lead_time` | 有 |
| GT-KIT-007 | KIT | 缺料全字段 + `critical_shortage` | `::test_gt_kit_007_full_fields_and_critical` | 有 |
| GT-KIT-008 | KIT | 硬缺料 `latest=null`/`alternatives=[]`/`insufficient` | `::test_gt_kit_008_hard_shortage` + `::test_gt_kit_008_zero_transit_equiv_none` | 有 |
| GT-ECN-001 | ECN | 影响面 5 项 | `test_ecn_r2.py::test_gt_ecn_001_impact_scope` | 有 |
| GT-ECN-002 | ECN | (a) 分析零写；(b) 应用写回 + 边确认 | `::test_gt_ecn_002a_analysis_zero_write` + `::test_gt_ecn_002b_apply` | 有 |
| GT-ECN-003 | ECN | 状态门 | `::test_gt_ecn_003_status_gate` | 有 |
| GT-ECN-004 | ECN | 日期门 + `missing_effective_date` | `::test_gt_ecn_004_missing_effective_date` | 有 |
| GT-ECN-005 | ECN | 唯一约束 + 确认位 + NULL 语义 | `::test_gt_ecn_005_unique_and_confirmed` | 有 |
| GT-ECN-006 | ECN | 重算幂等 | `::test_gt_ecn_006_idempotent` | 有 |
| GT-JSON-001 | JSON | 合法输出通过（`BomSelectionAgentOutput`；`Decimal`；`Decimal` 解析） | `tests/golden/test_agent_output_schema.py::test_json_001_valid_passes`（T3） | 有 |
| GT-JSON-002 | JSON | 非法 JSON → `failed`/`output_schema_valid=false` | `::test_json_002_invalid_payload_fails`（T3）+ `test_llm_r1.py::test_transport_client_parse`（T2）+ `::test_live_truncation`（T1，补强 `output_schema_valid is None` + 四值绑定） | 有 |
| GT-JSON-003 | JSON | 缺必填字段 → `ValidationError` | `::test_json_003_missing_required`（T3，`RequirementAgentOutput` 缺 `cards`/`cards=[]`、`BomCandidate` 缺 `lifecycle_status`） | 有 |
| GT-JSON-004 | JSON | 未知字段（`extra="forbid"`）→ `extra_forbidden` | `::test_json_004_extra_forbidden`（T3） | 有 |
| GT-JSON-005 | JSON | 幻觉 ID → `reference_check_passed=false`/`invalid_references` | `test_requirement_r2.py::test_verify_*` + `test_bom_selection_r2.py::test_pipeline_hallucinated_replaces_fails` + `test_traceability_agent_r1.py::test_pipeline_hallucinated_trace_ref_fails` | 有 |
| GT-JSON-006 | JSON | 数值越界 / 枚举非法 → `ValidationError` | `::test_json_006_bounds_and_enum`（T3，`score`/`lifecycle_status`/`relation_type`/`temperature`） | 有 |
| GT-JSON-007 | JSON | `Param` 取值一致性（6 组规则） | `::test_json_007_param_consistency`（T3） | 有 |
| GT-JSON-008 | JSON | `agent_name` 映射路由 + 非法 `agent_name` 抛出 | `::test_json_008_agent_name_routing`（T3） | 有 |
| GT-TRACE-001 | TRACE | 完整链路 31/37 + edge 语义 + `complete/missing=[]` | `test_d4_r3.py::test_demo_chain_complete` + `tests/golden/test_trace_query.py::test_trace_001_edge_relations_and_refs`（edge relation 集合 + `source_refs` 非空） | 有 |
| GT-TRACE-002 | TRACE | 未确认链（`confirmed_by_id IS NULL`）过滤 | `::test_trace_002_unconfirmed_excluded_confirmed_included`（ORM 构造未确认边 → 排除；确认后 → 纳入） | 有 |
| GT-TRACE-003 | TRACE | 查不到 → 200 + `found=false` 空链 + 零 LLM/零 AgentRun + 边界 | `test_d4_r3.py::test_serial_not_found` + `::test_root_without_links`（边界1）+ `::test_read_only_no_agentrun` + `::test_trace_003_zero_llm_and_warnings`（零 LLM mock + `warnings`）+ `::test_trace_003_normalization_variants_hit_same_chain` / `::test_trace_003_normalization_not_found_unchanged`（边界2 规范化） | 有 |
| GT-TRACE-004 | TRACE | 每个 `TraceNode.source_refs` 非空且可核验 | `::test_trace_001_edge_relations_and_refs`（全节点/边非空）+ `test_traceability_agent_r2.py::test_source_refs_aggregate_from_fixtures_evidence` | 有（C1 已处置） |
| GT-TRACE-005 | TRACE | 断点写入 `missing`（`no_purchase_order`/`no_test_run`） | `::test_trace_005_no_purchase_order_and_no_test_run`（关系缺失 → 两 token）+ `test_d4_r3.py::test_dangling_reference`（dangling → `unresolved_reference:*` 独立类别） | 有（C2 已处置） |
| GT-TRACE-006 | TRACE | `depth`/`direction` 参数语义（含负值/非法 → 400） | `::test_trace_006_depth_truncation` + `::test_trace_006_directed_variants` + `::test_trace_006_forward_with_depth` + `::test_trace_006_view_param_validation` | 有（C3 已处置；默认偏差见 §3） |
| GT-TRACE-007 | TRACE | `query_type="lot"` 批次反查 | `::test_trace_007_lot_query` | 有 |

**分组计数**：BOM 9 / KIT 8 / ECN 6 / JSON 8 / TRACE 7 = **38**；**状态：38/38「有」**。

---

## §2 JSON 组（终稿：8/8「有」）

| GT | 状态 | 落点（分层） |
| --- | --- | --- |
| GT-JSON-001 | 有 | `tests/golden/test_agent_output_schema.py::test_json_001_valid_passes`（T3） |
| GT-JSON-002 | 有 | `::test_json_002_invalid_payload_fails`（T3）+ T2 `test_transport_client_parse` + T1 `test_live_truncation`（补强断言） |
| GT-JSON-003 | 有 | `::test_json_003_missing_required`（T3） |
| GT-JSON-004 | 有 | `::test_json_004_extra_forbidden`（T3；`_StrictModel extra="forbid"` 已由全部输出类继承 → **无需收紧 schemas**） |
| GT-JSON-005 | 有 | `verify_*` + 两管道幻觉失败（T3） |
| GT-JSON-006 | 有 | `::test_json_006_bounds_and_enum`（T3） |
| GT-JSON-007 | 有 | `::test_json_007_param_consistency`（T3） |
| GT-JSON-008 | 有 | `::test_json_008_agent_name_routing`（T3） |

**映射规则（ADR-0008 R-2）复核**：非法 JSON / 截断 → T1 live 真造（`test_live_truncation`）；缺必需字段 / 格式合法但字段非法 / ID 不存在 → T2/T3（`test_agent_output_schema.py`）——一致。

---

## §3 汇总与冲突处置（终稿）

### 3.1 汇总

| 状态 | 条数 |
| --- | --- |
| **有** | **38** |
| 部分 / 无 | 0 / 0 |

（D12-R1 初稿：有 24 / 部分 6 / 无 8；D12-R2/R3 补齐后 38/38。）

### 3.2 冲突条目处置（R1 的 C1/C2/C3 + TRACE-002）

- **C1 · GT-TRACE-004（每节点 `source_refs` 非空）→ 已处置**：`fixtures/demo_seed.json` 39 条 `trace_links` 补 `evidence`（**DOC-001×16 / DOC-002×23**，谓词=端点含 `requirement`→DOC-001 否则 DOC-002）；`load_demo_seed` 补 `evidence` 映射；`chain.py` 节点（含根）与边 `source_refs` = 关联 `evidence` 聚合去重。契约 §3.2 示例刷新为含 `source_refs`。见 ADR-0017 §C1。
- **C2 · GT-TRACE-005（断点 token `no_purchase_order`）→ 已处置**：`missing` 改用 GT 字面 `no_purchase_order` / `no_test_run`（**关系缺失**触发：根批次无 `sourced_from` / `tested_by` 出边）；dangling（边在、端点不可解析）保留 `unresolved_reference:*` **独立类别**。见 ADR-0017 §C2。
- **C3 · GT-TRACE-006（`depth`/`direction`）→ 已处置（含 1 条默认偏差登记）**：`depth` 完整实现（`0`=全链；`N>0`=≤N 跳，确裁边 → `complete=false`+`depth_truncated`）；`direction` 显式 `forward`（沿 `from→to`）/`backward`（逆向）按方向过滤；非法/负值 → 400。
  - **默认语义偏差（登记，不回问）**：GT-006 字面默认 `direction = backward`；若按字面设置默认，`/trace/serial/SN-DEMO-001/` 默认链将从 **31/37** 缩水 → 违反「默认不漂移」硬约束。**默认保持双向（全链，31/37）**，`direction` 仅显式生效。见 ADR-0017 §D12-R3-1。
- **TRACE-002（未确认链过滤）→ 已实现**：`chain.py` 仅 `confirmed_by` 非空边入链；fixtures 39 条 `confirmed_by_id` 全非空 → 默认链零漂移；构造测试锁定（排除/纳入）。见 ADR-0017 §TRACE-002。

### 3.3 剩余缺口与去向（D13/D14）

| # | 剩余项 | 去向 | 说明 |
| --- | --- | --- | --- |
| 1 | `agents/traceability.py` 的 run 入口**未做输入规范化** | **D13/D14** | `agents/` 属 D12 禁改边界；规范化只在 `traceability/views.py` 查询入口实施（GT-TRACE-003 边界2 面向 `/trace/serial/`）。 |
| 2 | `direction` 默认语义与 GT-006 字面不一致 | **登记**（ADR-0017） | 已按「31/37 优先」处置并记录；GT 若修订再对齐。 |
| 3 | `replaces`「在列」硬执行 / ECN 自动推导影响面 | **v2** | 承接 D6/D7/D11 延后台账。 |

---

## §4 定稿声明

- **本轮（D12-R3）**新增/更新：`traceability/views.py`（输入规范化）、`docs/interface_contract.md` §3.2（`direction` 默认双向 + 输入规范化注记）、`docs/adr/0017`（D12-R3 增补）、`tests/golden/test_trace_query.py`（`forward`+`depth` 组合、规范化变体）。
- **门槛**：`pytest -q -m "not live"` 全绿（**224 passed / 5 deselected**）；`manage.py check` ✓；`makemigrations --check` = No changes；`validate_seed` OK。
- 本矩阵为 **GT 覆盖终稿**；`docs/golden_tests.md` 冻原本轮未改。
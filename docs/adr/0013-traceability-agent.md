# ADR-0013：追溯链解释层（D7-R1）

| 项 | 内容 |
| --- | --- |
| 状态 | 已接受（Accepted） |
| 日期 | 2026-10-06 |
| 里程碑 | D7-R1（契约核对 + `FailureReason` 微扩展 + Traceability Agent 管道 + 入口 + prompts） |
| 关联 | `traceability/chain.py`（DB 权威链，D4-R3 冻结） · `schemas/agent_outputs.TraceabilityAgentOutput` / `TraceNode` / `TraceEdge` / `TraceRef` / `FailureReason` · `docs/interface_contract.md` §4.3 · `docs/golden_tests.md` GT-TRACE-003 · `agents/traceability.py` · `agents/verification.py` · `prompts/traceability_agent/v1/` |

## 背景

D4-R3 已交付**纯 DB** 追溯链构建器 `build_trace_chain`（契约 §3.1 / §3.2）。D7-R1 引入 LLM
**解释层**：链结构必须由 DB 权威派生，LLM 仅产中文 `summary` 与 `trace_refs`（**建议**，须核验）。
同时闭合 D4-R1 登记项②（`FailureReason` 缺 `ambiguous`）。

## 决策

### 1. 字段权属（DB 权威 vs LLM 生成）

| `TraceabilityAgentOutput` 字段 | 权属 | 来源 |
| --- | --- | --- |
| `root` / `query_type` / `found` / `complete` | **DB 权威** | `build_trace_chain` |
| `nodes` / `edges` / `missing` | **DB 权威** | `build_trace_chain`（BFS + TraceLink 中心原则） |
| `summary` | **LLM 生成** | 中文链摘要 |
| `trace_refs` | **LLM 建议** | 见 §3 |
| `warnings` | DB 权威 | `未建立追溯链` 镜像 |

**硬约束**：LLM 输出（`summary` / `trace_refs`）经**合并**后才组装 `TraceabilityAgentOutput`，
并**再跑一次 Pydantic 校验**——链结构**不经 LLM 往返**。

### 2. 未命中短路边界（对应 GT-TRACE-003）

- 解析 `InventoryLot`（project 域，`serial_number` 统一承载序列号 / 批次号）：
  - **未命中** → `found=false` 负载（`missing=["serial_not_found"]`、`warnings=["serial_not_found"]`）；
    **不调用 LLM、不创建 AgentRun、不写任何行**；HTTP **200**（合法业务结果，**严禁记 `failed`**）。
  - **多命中** → `AmbiguousReferenceError`（fail-loud，端点映射 409）。
  - **命中** → 进入 LLM 管道。

### 3. `trace_refs` 口径

- prompt **限定** LLM 仅可引用「链上编号清单」（`{allowed_ids}`）；
- 管道对 `trace_refs` 的每个端点（`from` / `to`）做**存在性核验**（复用 `agents/verification.verify_references`）；
- 清单外**自由文本**（无 `type` / `id`）不入结构字段；非法枚举的引用建议（未知 `relation_type` /
  `from_type`）**丢弃单条**，不阻断整链；
- `trace_refs` 为**建议**：本轮不落 `TraceLink`（R2 定义确认 / 落档语义）。

### 4. 核验范围与两阶段 AgentRun

- 核验对象 = `trace_refs` 全部端点；失败 → `reference_check_passed=False`、`status=failed`、
  `invalid_references` 落库（不进人工确认队列）；通过 → `reference_check_passed=True`、`needs_review`。
- `call_json` 落**一行**并回传 `CallResult.agent_run`；核验以 `filter(pk).update(...)` 更新**同一行**
  ——**恰好 +1**。`fake` 后端（`agent_run is None`）**不落库、不核验更新**。
- **`output_json` 落合并后的 `TraceabilityAgentOutput` 全文**（成功与失败路径同）——落实 D6 教训
  （「落库 `output_json` 必须可按冻结 schema 反序列化」）。

### 5. `prompt_id` / `prompt_version`

照契约 §4.3：**`prompt.traceability.chain` / `v1`**（`agents/traceability.py` 常量）。

### 6. `FailureReason += "ambiguous"`（受控微扩展）

- **证据先行**：扩展前构造 `InvalidReference(reason="ambiguous")` → Pydantic 校验失败
  （`Input should be 'not_found', 'wrong_project' or 'unknown_type'`）；
- `schemas/agent_outputs.FailureReason` 增 `AMBIGUOUS = "ambiguous"`；
- 消费方：`agents/verification.py` 早已产出该值（`AMBIGUOUS_REASON`，D4-R1 登记项② / D5 遗留）；
- **round-trip**：含 `ambiguous` 的 `invalid_references` 可被 `AgentRunRead` 完整校验通过（测试固化）。

### 7. 派发（本轮不改）

`AgentRunAdmin._handle` 的 `traceability` 分支**留 R2**（approve/reject 语义 + 落档）；
本轮 D6 既有「未知 agent_name 跳过」行为不变（`test_dispatch_unknown_agent_skipped` 仍绿）。

## 后果

- 链结构不可被模型改写（合并后二次 Pydantic 校验兜底）；未命中零 LLM / 零 AgentRun（GT-TRACE-003）。
- `ambiguous` 枚举缺口闭合；`invalid_references` 语义与解析层一致。
- 留痕：字段权属、短路边界、`trace_refs` 口径、核验范围、两阶段写、prompt 取值、受控扩展均固化本 ADR。

## traceability 确认语义（v1，D7-R2 裁决：纯审计确认）

**裁决（2026-10-06）**：`traceability` 的 `approve` = **纯审计确认**——仅同行 `update(status="success", confirmed_by, confirmed_at)`，**不写任何实体 / `TraceLink`**。

**四条理由：**

1. **链结构为 DB 权威派生**：`nodes` / `edges` 的数据源即已有 `TraceLink` 与实体解析结果，`approve` 无「新实体」可写；重写派生数据无意义。
2. **LLM 只产文案与建议**：`summary` 是中文文案（非实体），`trace_refs` 是**引用建议**（R1 已定「仅建议」）；建议落库为 `TraceLink` 的语义在契约中**无明文**。
3. **实测建议常为空**：`live` 取证（run 13）`trace_refs=[]`；若改走「`trace_refs` → `TraceLink`」通常无内容可写，收益不足却引入未裁决的写路径。
4. **通用规则不等于专属定义**：§6「写入规则」规则 5「输出落库（实体 + TraceLink）」是**通用表述**，契约**无 traceability 专属写入定义**；据 §8「未经确认的候选不得进入正式数据与生效追溯链」原则，纯审计确认是**无歧义**实现，避免为无明文语义自造实体写入。

## D7 台账（R1 登记）

| 项 | 归属 | 说明 |
| --- | --- | --- |
| 消费方文档同步 | D13 / 文档轮 | `docs/interface_contract.md`（L143/L244/L288）与 `docs/data_dictionary.md`（L504）的 `reason` 枚举仍列 `not_found\|wrong_project\|unknown_type`，**缺 `ambiguous`**；本轮边界不含这两个文档，**仅报告不改**。 |
| `traceability` 派发 | D7-R2 | approve/reject 语义 + `rejected → human-rejected` 落档。 |
| `TraceNode.source_refs` 回填 | D7-R2 | evidence 规则（D4 登记项①关账）。 |
| `replaces` 在列约束 / 重复边语义 | D7-R3 | 集成缓冲评估。 |
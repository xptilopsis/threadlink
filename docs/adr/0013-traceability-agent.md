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

## D7-R2 增补

### 1. 派发矩阵（`AgentRunAdmin._handle`，`agents/admin.py`）

| agent_name | approve | reject |
| --- | --- | --- |
| `requirement` | 现有 confirmation 流程（写 Requirement + RequirementParam + TraceLink） | 通用 rejected（不写实体） |
| `bom_selection` | `approve_bom_selection`（draft Bom + BomItem + replaces TraceLink） | 通用 rejected（不写实体） |
| `traceability` | **`approve_traceability`（纯审计确认，零实体写入）** | 通用 rejected（不写实体） |
| 未知 | 跳过 + 计数 | 跳过 + 计数 |

### 2. human-rejected 落档（D5 约定关账）

- `settings.FAILURES_ROOT = BASE_DIR / "prompts"`。
- `reject` **事务提交后** best-effort 写
  `<FAILURES_ROOT>/<agent_dir>/v1/failures/<YYYY-MM-DD>-human-rejected-<run_id>.md`
  （`agent_dir`：`requirement`→`requirement_agent` / `bom_selection`→`bom_selection_agent` / `traceability`→`traceability_agent`）。
- 内容：元数据块（run id / agent_name / prompt_id / prompt_version / model / 时间 / 来源=human-rejected）+ `output_json` 摘要
  （`summary` 优先，卡片 / 候选 / 节点兜底；超 2000 字符截断并注明）。
- **best-effort 边界**：写失败仅 `logging.warning`，**不阻塞、不回滚** reject；同 run 覆盖。

### 3. `source_refs` 回填（`traceability/chain.py`，D4 登记项①关账）

- 节点 `source_refs` = **全部关联** `TraceLink` 的 `evidence` 聚合去重；**根节点恒为 `[]`**。
- 边 `source_refs` = 归纳该边的 `TraceLink` 的 `evidence` 聚合去重。
- 聚合按 `TraceLink.pk` 升序、去重稳定（键 = `json.dumps(evidence, sort_keys=True)`）→ 两次 build **逐字节一致**。
- 无 evidence → `[]`（与回填前兼容；fixtures `trace_links` 0/39 有 evidence → 演示链仍全空）。

### 4. `.type/.id` 与 `TraceRef.from_/to_` 薄适配（长期设计）

`agents.verification.verify_references` 面向**来源引用**（`SourceRef`：`.type`/`.id`），`TraceRef` 面向**链引用**
（`from_type`/`from_id`/`to_type`/`to_id`）——两者是不同结构。**不为统一而改冻结接口**；管道在核验前做薄适配
（把 `TraceRef` 两端转 `{type, id}`）。D7-R1 裁决接受为长期设计。

### 5. `FailureReason` 文档同步

`docs/interface_contract.md`（§6 写入规则 L143 / AgentRun 契约 L244 / §7 L288）与 `docs/data_dictionary.md`（L504）
的 `reason` 枚举已补 `ambiguous`（提交 `84c5268`），与 `schemas.agent_outputs.FailureReason` 一致。

## D7-R3 增补（集成缓冲 + 收口）

### 1. `prompts/traceability_agent/v1` 冻结（blob 口径）

| 文件 | sha256（`git cat-file blob HEAD:<path>`） |
| --- | --- |
| `system.md` | `b56e061ca2aeef73daa7b26deb29a2629f38d274484863efc83bea115ef0b241` |
| `user_template.md` | `84962e3df0e136da249a41e48e9274447e571e4ec6c4bc88745001c646efe107` |
| `schema.json` | `b8ff9b4088ab7a95422b5971581f45419d504c699d0899c4080fddee4599a71a` |

- **策略**（同 D5/D6）：v1 **不可改**，调优走 **v2** 新目录 + `prompt_version` 升级。
- **非确定性声明**：跨次措辞差异**接受、不追**；live 断言只锁值域/字段/计数，不锁逐字文本。
- 基准为**仓库 blob**（工作树因 `core.autocrlf` 呈 CRLF；工作树值仅作收口报告附录对照）。
- `prompts/traceability_agent/v1/failures/` 为**失败样例沉淀目录**（不纳入冻结，可增）。

### 2. `TraceLink` 重复边语义（v1 定稿，无代码）

- **唯一性** = `(project, from_type, from_id, to_type, to_id, relation_type)` **全元组**。
- **现库约束原文**（`traceability/models.py::TraceLink.Meta`）：
  `UniqueConstraint(fields=["project", "from_type", "from_id", "to_type", "to_id", "relation_type"], name="uq_tracelink_edge")`
  ——与定稿**逐字一致**。
- **同元组二次写入** = **DB 层拒绝**（`IntegrityError`）。
- **approve 流程** = **写入前同元组去重跳过**（`agents/bom_selection.py::approve_bom_selection`：先 `filter(同元组).exists()`，存在即跳过、不新建）。
- **不做跨 run 的确认合并**：同一元组只保留一条 `TraceLink`；二次 approve 不因新 run 更新既有边的 `confirmed_by`。

### 3. 集成缓冲评估：`replaces`「仅限排除清单内」硬执行 → **延至 v2**

- **现状（v1）**：`replaces_part_id` 由 prompt 约束 LLM 从「被排除清单」选取；管道仅做**存在性核验**（幻觉编号 → `failed`）；**"在列"未硬执行**。
- **评估见收口报告 §1**（成本/收益/风险三行）。**结论：v1 维持 prompt 约束 + 存在性核验，硬执行延至 v2。**

## D7 台账（R1 登记）

| 项 | 归属 | 说明 |
| --- | --- | --- |
| 消费方文档同步 | D13 / 文档轮 | `docs/interface_contract.md`（L143/L244/L288）与 `docs/data_dictionary.md`（L504）的 `reason` 枚举仍列 `not_found\|wrong_project\|unknown_type`，**缺 `ambiguous`**；本轮边界不含这两个文档，**仅报告不改**。 |
| `traceability` 派发 | D7-R2 | approve/reject 语义 + `rejected → human-rejected` 落档。 |
| `TraceNode.source_refs` 回填 | D7-R2 | evidence 规则（D4 登记项①关账）。 |
| `replaces` 在列约束 / 重复边语义 | D7-R3 | 集成缓冲评估。 |
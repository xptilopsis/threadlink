# ThreadLink 接口契约（Interface Contract）

> 范围：HTTP 接口契约 + 智能体输出契约。**本文档只定义契约，不含任何 view / service 实现**。
> Pydantic 模型定义见 `schemas/agent_outputs.py`。

---

## 1. 通用约定

- **传输**：JSON，UTF-8；请求 `Content-Type: application/json`。
- **金额**：字符串（如 `"12.50"`），对应模型中的 `Decimal`。
- **时间**：ISO8601（如 `2026-03-05T10:30:00+08:00`）。
- **ID**：稳定字符串编号（如 `REQ-001`、`PART-001`、`PO-001`）。
- **认证**：Django session 登录；写操作需同一单租户已登录用户。
- **只读约束**：Git 与文件接口**只提供读取**，不存在任何写回仓库 / 源文件的路径。
- **人工确认**：所有智能体产出均为**候选**，必须经人工确认（`confirmed_by` / `confirmed_at`）后方可写入正式实体与 TraceLink。
- **分页**：集合端点支持 `?page=`、`?page_size=`，响应含 `count` / `next` / `previous` / `results`。

集合端点统一响应结构：

```json
{ "count": 20, "next": null, "previous": null, "results": [] }
```

---

## 2. URL 契约总表

| 方法 | 路径 | 用途 | 请求要点 | 响应要点 |
| --- | --- | --- | --- | --- |
| GET / POST | `/projects/` | 项目列表 / 新建 | `{code, name, description, status}` | `ProjectRead` / 分页 |
| GET / PATCH / DELETE | `/projects/<id>/` | 详情 / 更新 / 删除 | PATCH 部分字段 | `ProjectRead` |
| GET / POST | `/requirements/` | 需求列表 / 新建 | `{code, title, content, source_type, status, params[], confirmed_by?}` | `RequirementRead` / 分页 |
| GET / PATCH / DELETE | `/requirements/<id>/` | 详情 / 更新 / 删除 | PATCH 部分字段 | `RequirementRead` |
| GET / POST | `/parts/` | 物料列表 / 新建 | `{part_number, name, lifecycle_status, params[]}` | `PartRead` / 分页 |
| GET / PATCH / DELETE | `/parts/<id>/` | 详情 / 更新 / 删除 | PATCH 部分字段 | `PartRead` |
| GET / POST | `/suppliers/` | 供应商列表 / 新建 | `{code, name, contact_name, email, status}` | `SupplierRead` / 分页 |
| GET / PATCH / DELETE | `/suppliers/<id>/` | 详情 / 更新 / 删除 | PATCH 部分字段 | `SupplierRead` |
| GET / POST | `/boms/` | BOM 列表 / 新建 | `{name, version, status, items[]}` | `BomRead`（含 items 层级） |
| GET / PATCH / DELETE | `/boms/<id>/` | 详情 / 更新 / 删除 | PATCH 部分字段 | `BomRead` |
| GET / POST | `/inventory-lots/` | 库存批次列表 / 新建 | `{part_id, serial_type, serial_number, quantity}` | `InventoryLotRead` / 分页 |
| GET / PATCH / DELETE | `/inventory-lots/<id>/` | 详情 / 更新 / 删除 | PATCH 部分字段 | `InventoryLotRead` |
| GET / POST | `/purchase-orders/` | 采购单列表 / 新建 | `{po_number, supplier_id, status, expected_date, total_amount}` | `PurchaseOrderRead` |
| GET / PATCH / DELETE | `/purchase-orders/<id>/` | 详情 / 更新 / 删除 | PATCH 部分字段 | `PurchaseOrderRead` |
| GET / POST | `/test-cases/` | 测试用例列表 / 新建 | `{code, name, test_type, expected}` | `TestCaseRead` / 分页 |
| GET / PATCH / DELETE | `/test-cases/<id>/` | 详情 / 更新 / 删除 | PATCH 部分字段 | `TestCaseRead` |
| GET / POST | `/test-runs/` | 测试执行列表 / 新建 | `{test_case_id, sample_serial, result, tested_at}` | `TestRunRead` / 分页 |
| GET / PATCH / DELETE | `/test-runs/<id>/` | 详情 / 更新 / 删除 | PATCH 部分字段 | `TestRunRead` |
| GET / POST | `/ecns/` | ECN 列表 / 新建 | `{ecn_number, title, change_type, status}` | `EcnRead` / 分页 |
| GET / PATCH / DELETE | `/ecns/<id>/` | 详情 / 更新 / 删除 | PATCH 部分字段 | `EcnRead` |
| GET / POST | `/trace-links/` | 追溯元数据列表 / 新建 | `TraceRef` 字段 | `TraceLinkRead` / 分页 |
| GET / PATCH / DELETE | `/trace-links/<id>/` | 详情 / 更新 / 删除 | PATCH 部分字段 | `TraceLinkRead` |
| GET | `/trace/serial/<sn>/` | 按序列号反查完整追溯链 | 路径参数 `sn` | `TraceabilityAgentOutput`（见 §3） |
| POST | `/agents/requirement/run/` | 运行需求智能体 | `RequirementRunRequest` | `{agent_run, output}`（见 §4.1） |
| POST | `/agents/bom-selection/run/` | 运行 BOM/选型智能体 | `BomSelectionRunRequest` | `{agent_run, output}`（见 §4.2） |
| POST | `/agents/traceability/run/` | 运行追溯智能体 | `TraceabilityRunRequest` | `{agent_run, output}`（见 §4.3） |
| GET | `/agent-runs/` | AgentRun 审计列表 | `?agent_name=&status=&page=` | `AgentRunRead` 分页 |
| GET | `/agent-runs/<id>/` | AgentRun 详情 | 路径参数 `id` | `AgentRunRead` |

**说明**：集合端点的 POST 写入正式实体时，若该实体由智能体候选产生，请求体必须携带 `confirmed_by`；缺失时接口应拒绝写入（人工确认为必备环节）。

---

## 3. 追溯查询端点

### 3.1 空链语义（`found` / `complete` / `missing`）

`TraceabilityAgentOutput` 用两个**准正交**布尔字段表达结果（`found=false` 时 `complete` 必为 `false`）：

- `found`：**查询根实体（序列号 / 批次号）是否存在**，与"链上是否有节点"无关。
- `complete`：**链路是否完整**，与 `missing` 满足**双向强制** `complete ⇔ missing=[]`（`missing=[]` 时必为 `true`；`missing` 非空时必为 `false`；`found=false` 时必为 `false`）。
- `missing`：导致链不完整的原因列表（**机器 token**，如 `serial_not_found` / `no_trace_links`），必有值；`warnings` 为人类可读补充（可含原因镜像），**不作机器判定依据**。

强制不变量（由 `@model_validator` 保证）：

- `found=false ⟺ nodes=[]`；`found=true` 时 `nodes` 至少包含根节点本身。
- `found=false ⇒ complete=false`；`complete=true ⟺ missing=[]`（**双向**，`complete=false ∧ missing=[]` 非法）。

响应契约：

| 情形 | found | complete | nodes | missing / warnings | HTTP | 调用 LLM | 产生 AgentRun |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 根实体不存在 | false | false | `[]` | `missing=["serial_not_found"]`，`warnings` 含 `"serial_not_found"` | 200 | 否 | 无 |
| 根存在但无任何 TraceLink | true | false | 含根节点 | `missing=["no_trace_links"]`，`warnings` 含 `"未建立追溯链"`（人类可读镜像） | 200 | 否 | 无 |
| 链路完整 | true | true | 全链 | `missing=[]` | 200 | 可选 | 可选 |
| 链路有断点 | true | false | 已存在节点 | `missing=[...]` | 200 | 可选 | 可选 |

- **`found=false` 是合法业务结果（HTTP 200），严禁记 `failed`**；此时先查库判定、未命中直接短路、**不调用 LLM**，按 R1 **不产生 AgentRun**。
- **`root` 语义**：查询输入的回显（序列号 / 批次号原文），仅用于审计，**不代表命中**；`found=false` 时仍必须回显。

### 3.2 GET `/trace/serial/<sn>/`

按样机/物料序列号反查完整追溯链：**需求 → BOM → 物料批次 → 采购单 → 测试 → ECN → Git 提交**。

- **路径参数**：`sn` — 序列号，如 `SN-DEMO-001`。
- **查询参数**（可选）：`depth`（默认 0 = 全链路）、`direction`（默认 **双向（全链）**；显式 `forward` / `backward` 按方向过滤）。
- **实现（DB 版，D12-R2/R3）**：`depth` / `direction` **已实现**——`depth=0`（缺省）= 全链；`depth=N>0` = 距根 ≤N 跳（**确裁边**时 `complete=false` 且 `missing` 增 `depth_truncated`）；`direction` **缺省 = 双向（全链，`31/37` 不漂移）**，显式 `forward`（沿 `from→to` 顺向可达）/ `backward`（逆向可达）自 root BFS 按方向过滤（与 GT-006 字面「默认 `backward`」的偏差见 ADR-0017）；非法/负值 `depth`、非枚举 `direction` → HTTP `400`。
- **输入规范化（D12-R3，GT-TRACE-003 边界2）**：`sn` 去首尾空白 + **大小写不敏感匹配**（`serial_number__iexact`）；**命中后以库中规范编号建链并回显 `root`**（`resolve_entity` 大小写敏感），未命中时 `root` = `strip` 原文；存储 / 唯一性 / 多命中守卫口径不变。
- **响应**：`TraceabilityAgentOutput`（`schemas/agent_outputs.py`），语义见 §3.1。
- **执行顺序**：先查库判定 `found`；`found=false` 时直接短路返回、不调用 LLM；仅 `found=true` 时可由 LLM 生成自然语言说明。
- **要点**：每个 `TraceNode` 必须带 `source_refs`（引用来源，用于防幻觉）；链路缺失环节写入 `missing` 并置 `complete=false`。
- **AgentRun 边界（R1）**：纯 DB 查询（含 `found=false` 短路）**不产生 AgentRun**；仅当经 `/agents/traceability/run/` 触发 LLM 推理时才记录 AgentRun。

响应示例（节选）：

```json
{
  "agent_name": "traceability",
  "root": "SN-DEMO-001",
  "query_type": "serial",
  "found": true,
  "complete": true,
  "nodes": [
    {"node_type": "requirement", "node_id": "REQ-001", "label": "输入电压与额定电流", "depth": 0, "source_refs": [{"type": "document", "id": "DOC-001"}], "confirmed": true},
    {"node_type": "bom", "node_id": "BOM-001", "label": "工业网关主 BOM", "relation_type": "implemented_by", "depth": 1, "source_refs": [{"type": "document", "id": "DOC-001"}], "confirmed": true}
  ],
  "edges": [
    {"from_node_id": "REQ-001", "to_node_id": "BOM-001", "relation_type": "implemented_by", "confidence": null, "source_refs": [{"type": "document", "id": "DOC-001"}]}
  ],
  "missing": [],
  "trace_refs": [],
  "warnings": []
}
```

---

## 4. 智能体运行端点

所有智能体端点的**统一响应结构**：

```json
{ "agent_run": { "…AgentRunRead…" }, "output": { "…对应 AgentOutput…" } }
```

**AgentRun 触发边界（R1，权威）**：AgentRun **只对应实际发生的 LLM 调用**。

- 无 LLM 调用 = 无 AgentRun：包括短路返回、纯 DB 查询、调用 LLM 前的输入校验失败。
- LLM 已调用但输出非法（结构校验失败或引用核验失败）= 记 AgentRun，`status="failed"`。
- `status` 枚举固定为 `failed | needs_review | success | rejected`，无其他取值（见 §6 绑定规则）。

**统一失败语义**：LLM 输出无法通过 Pydantic 校验时，端点返回已落库的 `AgentRunRead`，其中 `status="failed"`、`output_schema_valid=false`、`output_json=null`、`error` 为校验错误摘要；HTTP 状态码为 `422`。

**引用存在性核验（独立步骤，D2）**：Pydantic 仅做结构校验，**无法拦截幻觉 ID**。schema 校验通过后，业务层必须执行引用存在性核验：每个结构化引用 `(entity_type, entity_id)` 必须 (a) `entity_type` 在实体类型白名单（`EntityType`）内，(b) 实体存在，(c) 属于同一 `project_id`；`entity_id` 为业务编号（R2）。核验失败时 `AgentRun.status="failed"`、`reference_check_passed=false`，失败条目写入 `invalid_references`（元素含 `entity_type` / `entity_id` / `reason ∈ {not_found|wrong_project|unknown_type|ambiguous}`），输出保留于 `output_json` 供调试并沉淀到 `prompts/<agent>/v1/failures/`，**不进入人工确认队列**；HTTP `422`。自由文本引用（页码 / 章节号 / 文件名片段）不做核验。

### 4.1 POST `/agents/requirement/run/`

- **请求**：

```json
{
  "project_id": "PROJ-001",
  "document_id": "DOC-001",
  "content": null,
  "source_type": "email",
  "prompt_id": "prompt.requirement.extract",
  "prompt_version": "v1",
  "model": "gpt-4o-mini",
  "temperature": 0.0
}
```

  - `document_id` 与 `content` 二选一；`source_type` ∈ `prd|sor|email|manual`。
- **成功响应**：`agent_run`（`AgentRunRead`）+ `output`（`RequirementAgentOutput`，含 ≥1 张 `RequirementCard`）。
- **人工确认**：返回的 `RequirementCard.confirmed=false`；确认后经 `/requirements/` 写入正式需求并生成 `TraceRef` → TraceLink。

### 4.2 POST `/agents/bom-selection/run/`

- **请求**：

```json
{
  "project_id": "PROJ-001",
  "constraints": [
    {"name": "input_voltage", "operator": "range", "value_min": "9", "value_max": "36", "unit": "V", "is_mandatory": true},
    {"name": "rated_current", "operator": "gte", "value_num": "5", "unit": "A", "is_mandatory": true},
    {"name": "operating_temp", "operator": "range", "value_min": "-40", "value_max": "85", "unit": "C", "is_mandatory": true},
    {"name": "ip_rating", "operator": "eq", "value_text": "IP65", "is_mandatory": true},
    {"name": "bom_cost", "operator": "lte", "value_num": "800", "unit": "CNY", "is_mandatory": true}
  ],
  "requirement_id": "REQ-001",
  "prompt_id": "prompt.bom.selection",
  "prompt_version": "v1",
  "model": "gpt-4o-mini",
  "temperature": 0.2
}
```

- **成功响应**：`AgentRunRead` + `BomSelectionAgentOutput`。
- **要点**：每个 `BomCandidate` 必须含 `lifecycle_status`（停产语义）、`lead_time_days`、`unit_price`、`rationale`（替代理由）与 `source_refs`。`replaces_part_id` 为**被替代物料的业务编号**（`Part.part_number`，R2），非数据库主键。

### 4.3 POST `/agents/traceability/run/`

- **请求**：

```json
{
  "project_id": "PROJ-001",
  "serial_number": "SN-DEMO-001",
  "query_type": "serial",
  "prompt_id": "prompt.traceability.chain",
  "prompt_version": "v1",
  "model": "gpt-4o-mini",
  "temperature": 0.0
}
```

- **成功响应**：`AgentRunRead` + `TraceabilityAgentOutput`。
- **要点**：链路节点必须带引用；`ECN` 影响可复用 `ecn_impacts` / TraceLink。序列号不存在时先短路（`found=false`，不调用 LLM），按 R1 **不产生 AgentRun**（空结果是合法业务结果，严禁记 `failed`）。`found` / `complete` / `root` 语义见 §3.1。

---

## 5. AgentRun 审计端点

### GET `/agent-runs/`

- **查询参数**：`agent_name`（`requirement|bom_selection|traceability`）、`status`（`failed|needs_review|success|rejected`）、`page`、`page_size`。**人工确认队列 = `?status=needs_review` 的查询**。
- **响应**：`AgentRunRead` 分页列表，按 `created_at` 倒序。

### GET `/agent-runs/<id>/`

- **响应**：单条 `AgentRunRead`。

---

## 6. AgentRun 审计契约（字段必须齐全）

**AgentRun 只对应实际发生的 LLM 调用（R1）**：无 LLM 调用（短路返回 / 纯 DB 查询 / LLM 前的输入校验失败）**不产生 AgentRun**；LLM 已调用但输出非法则产生 `status="failed"` 的记录。

每次**实际发生的 LLM 调用**必须落一条 AgentRun 记录，字段如下（对应 `AgentRunRead`）：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | AgentRun 标识 |
| `agent_name` | enum | 是 | `requirement` / `bom_selection` / `traceability` |
| `prompt_id` | string | 是 | 提示词标识 |
| `prompt_version` | string | 是 | 提示词版本 |
| `model` | string | 是 | 模型标识 |
| `temperature` | float | 是 | 采样温度，`0.0 ~ 2.0` |
| `input_json` | object | 是 | 调用输入（原始） |
| `input_hash` | string | 是 | 输入 SHA-256（64 位十六进制），用于复现与去重 |
| `output_json` | object \| null | 否 | LLM 输出；解析失败时为 null |
| `output_schema_valid` | bool | 是 | 输出是否通过 Pydantic 校验 |
| `reference_check_passed` | bool \| null | 否 | 引用存在性核验是否通过；`null`=未执行到核验步骤，`false`=核验失败 |
| `invalid_references` | array | 否 | 核验失败条目 `{entity_type, entity_id, reason}`；`reason ∈ not_found\|wrong_project\|unknown_type\|ambiguous` |
| `references` | array | 是 | 引用来源（`SourceRef[]`），防幻觉 |
| `status` | enum | 是 | `failed` / `needs_review` / `success` / `rejected`（固定四值，R1） |
| `error` | string \| null | 否 | 失败信息（含校验错误摘要） |
| `confirmed_by` | string \| null | 否 | 人工确认人（DB 列 `confirmed_by_id`） |
| `confirmed_at` | datetime \| null | 否 | 人工确认时间 |
| `created_at` | datetime | 是 | 创建时间 |

> **status 语义映射（四值，R1）**：
> - `failed`：机器侧失败（LLM 调用失败 / 结构校验失败 / 引用核验失败），**终态**，不进入人工确认队列。
> - `needs_review`：两步校验通过、等待人工处置；**人工确认队列 = `status=needs_review` 的查询**。
> - `success`：人工确认通过，输出已落库（实体 + TraceLink）。
> - `rejected`：人工拒绝，不落库；运行记录保留供审计与迭代（人工拒绝是最高质量负样本，沉淀到 `prompts/<agent>/v1/failures/`）。
>
> **绑定规则**：`success` / `rejected` ⇒ `confirmed_by`、`confirmed_at` **必填**；`failed` / `needs_review` ⇒ 二者**必须为 NULL**。无 LLM 调用不产生记录（R1）。
>
> **D5 遗留（D1 不增字段）**：若允许「人工修改后确认」，人工修改的最终版本如何留痕待 D5 评估（建议 `confirmed_output_json`），D1 不做决定。

**写入规则（R1）**：

0. 无 LLM 调用（短路返回 / 纯 DB 查询 / LLM 前的输入校验失败）→ **不产生 AgentRun**。
1. LLM 调用发生即落记录：`input_json`、`input_hash`、`prompt_id`、`prompt_version`、`model`、`temperature`，初始 `confirmed_by` / `confirmed_at` 为 NULL。
2. 通过 schema 校验 → `output_schema_valid=true`；随即执行**引用存在性核验**（独立步骤）。
3. 引用核验通过（`reference_check_passed=true`）→ 进入人工确认队列，`status="needs_review"`（`confirmed_by` / `confirmed_at` 保持 NULL）。
4. 输出未通过 schema 校验（`output_schema_valid=false`），或核验失败（`reference_check_passed=false`，`invalid_references` 落库），或调用异常 → `status="failed"`，`error` 记录原因，`confirmed_by` / `confirmed_at` 保持 NULL；`output_json` 保留供调试；**不进入人工确认队列**。
5. 人工确认通过 → `status="success"`，更新 `confirmed_by` / `confirmed_at`（必填）；输出落库（实体 + TraceLink）。
6. 人工拒绝 → `status="rejected"`，更新 `confirmed_by` / `confirmed_at`（必填）；**不落库**正式实体与 TraceLink，运行记录保留供审计与迭代。
7. **空结果（`found=false` 的追溯查询）不调用 LLM，因此不产生 AgentRun**。

> **traceability 确认语义（v1）**：`traceability` 的链结构为 **DB 权威派生**（数据源即已有 `TraceLink`），LLM 仅补 `summary`（`trace_refs` 为建议）。故其 `approve` 为**纯审计确认**——仅将 `AgentRun` 置 `status="success"` 并写 `confirmed_by` / `confirmed_at`，**不写任何实体 / `TraceLink`**（规则 5 的「输出落库」对 traceability 无对应新实体）；`reject` 同规则 6（不落库）并落 human-rejected 失败样例。裁决依据见 ADR-0013。

---

## 7. 输出校验与失败语义

- **唯一校验入口**：`schemas.agent_outputs.validate_agent_output(agent_name, payload)`。
- **规则**：所有 LLM 输出必须能被对应 Pydantic 模型校验，禁止直接落库未经校验的原始文本。
- **映射**：

| agent_name | 输出模型 |
| --- | --- |
| `requirement` | `RequirementAgentOutput` |
| `bom_selection` | `BomSelectionAgentOutput` |
| `traceability` | `TraceabilityAgentOutput` |

- **校验分两步**：①`schema 校验`（本表模型）；②`引用存在性核验`（独立步骤，D2）。schema 通过不代表数据可信——`SourceRef.id` / `recommended_part_id` / `TraceNode.node_id` 等引用必须真实存在、类型匹配且同属一个 `project_id`；Pydantic 无法拦截幻觉 ID。
- **失败处理**：捕获 `pydantic.ValidationError`，将 `AgentRun.status` 置为 `failed`、`output_schema_valid=false`、`error=str(exc)`，HTTP 返回 `422`。引用核验失败时置 `status="failed"`、`reference_check_passed=false`、`invalid_references` 落库（`reason ∈ {not_found|wrong_project|unknown_type|ambiguous}`），同样返回 `422`；失败样本沉淀到 `prompts/<agent>/v1/failures/`。前端应展示该 AgentRun 以便排查，而非静默丢弃。

---

## 8. 人工确认契约

人工确认是**正式流程**，不是异常分支：

1. 智能体产出候选（需求卡 / 候选料 / 追溯节点），字段 `confirmed=false`，`confirmed_by` / `confirmed_at` 为空。
2. 用户逐项确认（采纳 / 编辑后采纳 / 拒绝）。
3. 采纳项写入正式实体，并生成带 `confirmed_by`、`confirmed_at` 的 `TraceLink`。
4. 对应 AgentRun 记录 `confirmed_by` / `confirmed_at`（可由用户级或对象级确认触发）。
5. **未经确认的候选不得进入正式数据与生效追溯链**（`TraceLink.confirmed_by IS NULL` 视为未生效）。

所有输出模型（`RequirementCard`、`BomCandidate`、`TraceNode`、`TraceRef`）均包含人工确认字段。

---

## 9. 状态码与错误体

| 状态码 | 含义 |
| --- | --- |
| 200 | 查询 / 更新成功 |
| 201 | 创建成功 |
| 400 | 请求参数不合法 |
| 401 | 未登录 |
| 403 | 无权限 / 违反只读约束 |
| 404 | 资源不存在 |
| 409 | 冲突（如重复编号、`input_hash` 重复提交） |
| 422 | 智能体输出未通过 schema 校验（对应 AgentRun `failed`） |

错误体统一格式：

```json
{ "error": { "code": "validation_error", "message": "…", "details": {} } }
```

---

## 10. 只读约束

- `/parts/`、`/boms/` 等业务端点不提供 Git / 文件**写回**能力。
- 任何接口不得修改本地仓库或源文件；Git 相关读取仅限 `log` / `show` / `diff` / `ls-tree`。
- 违反只读约束的请求一律返回 `403`。

---

## 11. 与 schemas 的映射

| 契约概念 | 模型（`schemas/agent_outputs.py`） |
| --- | --- |
| 引用来源 | `SourceRef` |
| 追溯关系候选 | `TraceRef` |
| 参数 | `Param` |
| 需求卡 / 需求智能体输出 | `RequirementCard` / `RequirementAgentOutput` |
| 候选物料 / 选型智能体输出 | `BomCandidate` / `BomSelectionAgentOutput` |
| 追溯节点 / 边 / 追溯智能体输出 | `TraceNode` / `TraceEdge` / `TraceabilityAgentOutput` |
| 智能体调用创建 / 读取 | `AgentRunCreate` / `AgentRunRead` |
| 统一校验入口 | `validate_agent_output` |
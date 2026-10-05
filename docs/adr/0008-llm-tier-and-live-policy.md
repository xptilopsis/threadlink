# ADR-0008：LLM 测试分层与 live 策略（D5）

| 项 | 内容 |
| --- | --- |
| 状态 | 已接受（Accepted） |
| 日期 | 2026-10-05 |
| 里程碑 | D5（LLM 客户端层 + Requirement Agent + AgentRun 落库） |
| 关联 | `agents/llm.py` · `schemas/agent_outputs.py` · `docs/interface_contract.md` §6 · `scripts/llm_preflight.py` |

## 背景

D1–D4 约束「不调用真实 OpenAI」；**D5 起默认真实调用 LLM（live 默认执行）**，需要明确的测试分层与运行策略。同时执行环境（本沙箱）对 LLM 出网整体受限，须把「live 取证」与「结构层验证」显式分离。

## 决策

### 1. 测试分层（Tier）

| 层 | 标记 | 内容 | 默认 |
| --- | --- | --- | --- |
| T1 live | `@pytest.mark.live` | 一切模型交互：连通、结构化输出、截断、引用核验失败、端到端 | **默认执行（真打）** |
| T2 transport | `@pytest.mark.transport` | API 形态无法真造时（缺必需字段 / 返回体异常）；mock 在 HTTP 客户端边界，测我方解析/校验代码 | 默认执行 |
| T3 craft | 无标记 | 我方校验逻辑单测（引用核验器、四值绑定、链不变量、canonical hash、错误分类映射） | 默认执行 |
| T4 offline | `LLM_BACKEND=fake` | 断网开发逃生口：从 `tests/fixtures/llm_fake/<prompt_id>.json` 回放 | pytest 默认不使用 |

### 2. live 默认

`pytest -q` 默认包含 T1/T2/T3（`addopts` 不加过滤）。断网/无 key 环境用 `pytest -q -m "not live"` 逃生（仅跳过 T1）。

### 3. fail-loud

配置缺失（`OPENAI_API_KEY` / `OPENAI_MODEL`） → `LLMConfigError`，报错文案含变量名，**不 skip、不落 AgentRun**（R1 边界：只有实际发起调用才产生 AgentRun）。截断 / 拒绝 / 结构非法 / 非 JSON 均归类并抛明确异常，不静默降级。

### 4. provider 自适应结构化模式（**对原「json_schema 双保险」决策的修订**）

原意向为无条件使用 `json_schema`(strict) 结构化输出。实测不同 provider（如 DeepSeek 兼容端点）对 `response_format=json_schema` 支持不一，故修订为：

- `LLM_STRUCTURED_MODE=auto`（默认）：先按 `json_schema`(strict) 发起；若端点返回「不支持该参数」类错误 → **自动降级 `json_object` 重发一次**，并记录**实际使用**的模式（`structured_mode`）；
- 显式配置 `json_schema` / `json_object` 时直接使用，不做降级。

**Pydantic 权威**：无论哪种模式，最终以 `schema_model.model_validate` 通过为唯一成功判据（跨字段不变量在最外层执行）；`json_object` 仅提高模型遵循 JSON 的概率，不放松校验。

### 5. 模型快照固定

`OPENAI_MODEL` 应填**带日期快照 id**（OpenAI 系）以保证可复现；DeepSeek 等无快照 id 的 provider 见 R-3。

### 6. 成本护栏

- 默认 `max_tokens` 保守、`temperature=0`；
- `LLM_TIMEOUT` / `LLM_MAX_RETRIES=2` 限制重试与等待；
- live 套件用**极小 schema + 极短输入**，截断用例 `max_tokens=8`；
- 每次调用落 `AgentRun`（含 `input_hash`）便于用量核对与去重。

### 7. 风险登记

- **R-1 复检可复现性**：独立复检方所在环境可能无 key/网络，无法重跑 live。**协议**：执行侧提交 live 运行证据（pytest 输出 + AgentRun 行快照 + 用量），复检侧验证结构层与 T2/T3；报告须标注「live 未由复检方执行」。
- **R-2 边界用例迁移**：非法 JSON / 缺字段属 API 返回体异常，落 **T2 transport**（而非 live）；D12 验收语言据此备注。
- **R-3 DeepSeek 无快照 id**：DeepSeek 等 provider 不提供日期快照模型 id，跨时点可复现性弱于 OpenAI 快照；演示以「单机可复现 + 记录实际 model id」为准（`AgentRun.model` 记录实际值）。

## 补充（2026-10-05）：provider 适配与推理档位

### json_schema → json_object 降级（已实证）

本机 live 取证（DeepSeek 兼容端点）观测到：`response_format={"type":"json_schema"}` 不被支持，客户端**自动降级 `json_object` 重发一次**，`structured_mode` 记录实际模式 `json_object` —— 降级策略**真实生效**。最终仍以 Pydantic 校验（`model_validate`）为唯一成功判据。

### extra_body 配置注入（通用，无代码特判）

新增 `LLM_EXTRA_BODY`（JSON 字符串）→ 经 OpenAI SDK `extra_body=` 透传；**不在代码中写死任何 provider 特判**，切回 OpenAI 只需置空。`agents/llm.py` 的 `fake` 后端忽略该参数。

### 推理档位探测（本机人工，沙箱无出网）

思考模型（reasoning model）把 reasoning tokens 计入 `max_tokens`：本机预检观测 `max_tokens=32` 时 `reasoning_tokens=32`、`content=''`、`finish_reason=length`，导致连通冒烟假失败。探测命令：

```cmd
python scripts\llm_preflight.py --probe-reasoning
```

三组：基线 / `thinking={"type":"enabled"}` + `reasoning_effort="low"` / `thinking={"type":"disabled"}`；成功标准 = **reasoning_tokens 趋零且 content 非空**。

### 生产推荐配置（2026-10-05 本机探测定稿）

本机对 DeepSeek 端点实测三组（`max_tokens=512`）：

| 组 | `thinking` / `reasoning_effort` | `reasoning_tokens` | `content` |
| --- | --- | --- | --- |
| baseline | （不传） | 41 | `{"ok": true}` |
| enabled+low | `thinking.type=enabled` + `reasoning_effort=low` | 14 | `{"ok": true}` |
| **disabled（定稿）** | `thinking.type=disabled` | **None** | `{"ok": true}` |

**定稿推荐**：`LLM_EXTRA_BODY={"thinking": {"type": "disabled"}}`（等价 `{"reasoning_effort": "none"}`）；已写入 `.env.example` 与 README。
**官方文档合法值**：`thinking.type ∈ {enabled, disabled}`（默认 `enabled`）；`reasoning_effort ∈ {none, low, high, max}`（`none` 禁用思考、`low/high/max` 启用，默认 `high`；兼容映射 `minimal→low`、`medium/xhigh→high`）。
**另据文档**：`response_format.type` 仅 `{text, json_object}`（**不支持 `json_schema`**），实证本 ADR 的 `json_schema→json_object` 自动降级为必需能力；`max_tokens` 未设时默认非思考 8K / 思考 64K。

### preflight 与测试口径

- `scripts/llm_preflight.py`：加载生产配置（含 `extra_body`）、**断言 `content` 非空**、打印 `reasoning_tokens`（杜绝此前「content 空仍报 OK」的假通过）。
- `tests/test_llm_r1.py` live connectivity：`max_tokens=512` 仅作防御性余量，**根因按配置消除**（不再依赖"预算够大"）。

## 后果

- 正向：live 为默认，真实行为可被持续验证；T2/T3 让无网环境仍可验证解析/校验代码；provider 自适应避免绑定单一端点能力。
- 成本：live 需 key 与出网，CI/沙箱默认不可跑，须以 `-m "not live"` 迭代并依赖本机取证（R-1）。
- 留痕：Tier 定义、结构化模式降级策略、Pydantic 权威、三项风险均固化于本 ADR。
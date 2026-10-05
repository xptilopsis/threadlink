# Live 失败样例：`max_tokens` 截断（D5 收口 §4）

> **来源：真实 live 调用**（生产库，非 craft 复现）——`agents/llm.py::call_json` 对 `RequirementAgentOutput` 以 `max_tokens=8` 直调，触发 `finish_reason=length`。
> 自然来源说明：`tests/test_llm_r1.py::test_live_truncation` 每次 `-m live` 真打都会产生同类 failed 行；本条为该机制在收口轮 §3.3 的显式复现。

| 项 | 值 |
| --- | --- |
| 日期 | 2026-10-05 |
| AgentRun id | **12** |
| agent_name | requirement |
| status | **failed** |
| model | deepseek-flash |
| temperature | 0.00 |
| structured_mode | json_object |
| error_type | **truncation** |
| created_at | 2026-10-05 05:33:59.229039+00:00 |

**error**：`输出被 max_tokens 截断（finish_reason=length）`

**output_json 全文**：
```json
{"error_type": "truncation", "error": "输出被 max_tokens 截断（finish_reason=length）", "raw": "{\"agent_name\":\"requirement\",\"summary", "structured_mode": "json_object"}
```

**元数据补充**：
- `usage`：截断异常路径未记录（`output_json` 不含 usage；失败落库字段集固定为 `error_type`/`error`/`raw`/`structured_mode`）。
- `raw` 为被截断的响应片段（前 500 字符上限），可见模型已开始输出合法 JSON 前缀即被 `max_tokens=8` 截断——与 `structured_mode=json_object`（provider 自适应降级后的实际模式）一致。

## 分层说明（live 证据纪律）
- 本条为 **live 真实失败负载**（T1），与 D5-R2 沙箱 craft 复现版 `2026-10-05-reference-check-failed.json` 分属不同层。
- **human-rejected 样例落档**（拒绝时输出沉淀到 `prompts/*/failures/`，`human-rejected` 标注）按 `interface_contract` 约定 **D7 实现，本轮不做**。
# ADR-0009：文档摄取路径语义修正（D5-R2）

| 项 | 内容 |
| --- | --- |
| 状态 | 已接受（Accepted） |
| 日期 | 2026-10-05 |
| 里程碑 | D5-R2（Requirement Agent 全链） |
| 关联 | `docs/PRD.md` AC-008（§7.7） · `docs/data_dictionary.md` §19 Document · `core/admin.py` · `config/settings.py` · `tests/test_d4_r2.py` · `docs/qa/2026-10-05-d4-closeout.md` |

## 背景与冲突

`docs/PRD.md` AC-008（只读约束）原文要求：对 Git / 文件端点执行写方法 → `403`/`404`，且目标文件 mtime 与仓库 commit 无变化。D4-R2 据此把 `Document` 纳入全只读 Admin（`has_add/change/delete_permission=False`，`add → 403`）。

但 D5-R2（Requirement Agent 全链）需要**验收邮件/文档入库**路径（Must #4「文件」摄取：上传客户邮件 → 生成需求卡）。二者字面冲突：若 Document 一律禁 `add`，则无摄取入口。

同一冻结集内的这一矛盾须显式定死，而非绕开。

## 判定

- **「创建 ≠ 修改」**：AC-008 的「写方法」约束针对**既有工件**（Git 仓库、既有文档内容）的修改/删除；**创建新 `Document` + 平台内新增文件**属取证/摄取路径，不属 AC-008 范围。
- **`is_readonly=true` 语义 = 创建后不可变**：入库时写入 `file_path` / `checksum` / `size_bytes` 并置 `is_readonly=True`；此后 `change/delete` 一律 `403`，磁盘文件内容与 mtime 不被任何路径改写。
- **D4-R2 「Document 全禁」为对 AC-008 的过度适用**，现予修正；`GitRepo` / `GitCommit` **维持全只读不变**。

## 清单（本次变更）

- **admin（`core/admin.py`）**：`DocumentAdmin` 从 `ReadOnlyModelAdmin` 拆出——`has_add_permission=True`、`has_change_permission=False`、`has_delete_permission=False`、`has_view_permission=True`；新增 `DocumentAdminForm`（表单级 `upload` 文件字段，非模型字段）；`save_model` 将文件写 `documents/uploads/<timestamp>-<safe_name>`（`get_valid_filename` sanitize），设 `file_path`（BASE_DIR 相对）、`checksum`（真实 SHA-256）、`size_bytes`、`is_readonly=True`、`mime_type`。`GitRepo` / `GitCommit` 不动。
- **settings（`config/settings.py`）**：新增 `DOCUMENTS_ROOT` 常量与模块级 `resolve_doc_path(file_path)`（`(BASE_DIR/file_path).resolve()`，`relative_to(BASE_DIR)` 防目录穿越）。注：函数在 settings **模块**上，须 `from config.settings import resolve_doc_path`（不在 `django.conf.settings` 对象上）。
- **测试（`tests/test_d4_r2.py`）**：原 `document add → 403` 断言改为——`document add` 表单 `GET 200`；`POST` 小文件 → 创建成功、`file_path` 在 `uploads/`、`checksum == 磁盘 SHA-256`、`is_readonly=True`；新建文档 `change/delete POST → 403` 且磁盘文件 mtime/内容不变；`GitRepo`/`GitCommit` `add → 403` 保持。
- **文案**：`docs/PRD.md` AC-008 加 v1 解释性标注（标注不改声明，沿用 D4 §3.2 先例）。

## 影响

- 演示摄取路径可用：上传邮件 → `Document`（只读）→ Requirement Agent 读取正文生成需求卡。
- 既有工件仍受 AC-008 保护；Git 三实体只读语义不变。
- 演示链（D13）文档实体化时，DOC-001/002 种子文件（真实 LF + SHA-256 `checksum`）已在仓库内。
## 管道设计（D5-R2 主体）

**Requirement Agent 全链（`agents/requirement.py::run_requirement_agent`）：**

1. 读 `Document` 正文（`resolve_doc_path`；`.pdf` 经 pdfplumber，缺依赖则报错登记延后）；
2. `agents/prompts.py::load` 装载 system/user_template（`prompt_id → prompts/requirement_agent/<version>/` 映射，文件缺失 fail-loud）；渲染注入文档编号 + 正文；
3. `agents/llm.py::call_json(RequirementAgentOutput, ...)`（provider 自适应结构化；`prompt_id=prompt.requirement.extract`、`prompt_version=v1`）；
4. **引用核验**（`agents/verification.py`）→ **同一 AgentRun 行**更新。

**两阶段 AgentRun 写（事务边界）：** `call_json` 内 `AgentRun.objects.create(...)` 落**一行**（成功 `needs_review` / 失败 `failed`），并经 `CallResult.agent_run` 回传（**最小接口改动**）；核验在管道内以 `AgentRun.objects.filter(pk=...).update(...)` 更新**同一行**（不新增）——**一次运行 AgentRun 恰好 +1**（测试直接断言计数）。`call_json` 自身失败已落 `failed` 行，管道**不重复写**。

**核验器接口与 `ambiguous` 口径：** `verify_references(project_id, refs) -> list[InvalidRef]`；白名单 = `EntityType`（schemas）；复用 `traceability.services.resolve_entity` 做同 project 校验；`reason ∈ {not_found, wrong_project, unknown_type}`（`FailureReason`）；「存在但属其它 project」判 `wrong_project`（resolve 未命中后回查是否存在同编号实体）；解析器 `AmbiguousReferenceError` → 捕获记 `reason="ambiguous"`（**D4 延后项 ②：D7 对账枚举**）；自由文本引用不核验。

**source_refs 策略：** LLM 被要求为每卡输出结构化引用（`{"type": "<ReferenceType>", "id": "<业务编号>"}`）；系统在核验前**附加源文档引用作底**（`{"type": "document", "id": doc_no}`）；两类都过同一核验器。核验通过 → `reference_check_passed=True`（`status` 保持 `needs_review`）；失败 → `False` + `status=failed` + `invalid_references` 落库、**不进队列**。

**prompt 约束：** `system.md` 明确**中文输出**、`priority ∈ {low, medium, high}`、`source_refs` 形状、禁止编造业务编号。`schema.json` 为**参考件**，权威 = `schemas/agent_outputs.py`（Pydantic 派生）。

**入口与队列：** `DocumentAdmin` action「运行 Requirement Agent」（选中触发，消息 N 张卡片进入待确认 / 失败摘要）+ 契约端点 `POST /agents/requirement/run/`（`@login_required`，请求 `project_id`/`document_id`/…，响应 `{agent_run, output}`）——两者共用 `run_requirement_agent`。`AgentRunAdmin` 只读队列（list + `agent_name`/`status` 过滤、detail 全字段只读 + `output_summary`）；**确认/拒绝动作不建（留 R3）**。
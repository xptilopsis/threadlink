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
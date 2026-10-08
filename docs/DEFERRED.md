# ThreadLink 延后台账（D13-R2 清扫）

- **日期**：2026-10-08
- **前置 HEAD**：`4d6817d`
- **来源**：全库扫描 `docs/qa/*`、`docs/adr/*`、`README.md` 中「延后 / 登记 / 待办 / 待裁决 / v2 / 暂缓 / nit」。
- **口径**：本文件为**汇总去重**后的唯一台账；各条目原始上下文仍以来源文件为准。

---

## 一、台账汇总

| # | 项 | 来源 | 内容 | 去向 | 现状 |
| --- | --- | --- | --- | --- | --- |
| 1 | criteria 输入表单 | ADR-0012 §8；D5·D7·D11 收口 | BOM 选型 UI 输入页 | **D13（R1 已交付）** | ✅ `/agents/bom-selection/form/` |
| 2 | 占位 PDF 三件套 | D5·D7·D11 收口 | DOC-003/004/005 无文件，需回填 checksum/size/mime | **D13（R1 已判定）** | ✅ 判定「演示不走文件打开」，不生成占位 |
| 3 | `sync` 非事务说明 | D5·D7·D11 收口 | `sync_git_repo` 逐条 upsert 非事务 | **D13（R1 已入档）** | ✅ RUNBOOK 附录 B |
| 4 | `resolve_doc_path` 搬迁 nit | D5 ⑨；D7·D11 收口 | 迁至 `core/paths.py` | **不做（超 R2 边界）→ D14 视情** | 未动；`config/settings.py:161` |
| 5 | `replaces`「在列」硬执行 | D7 §1；ADR-0013 §3 | 建议仅限排除清单内 | **v2** | v1 维持 prompt 约束 + 存在性核验 |
| 6 | ECN 自动推导影响面 | ADR-0015；D7·D11 收口 | 由图计算影响面 | **v2** | v1 以 `ECNImpact` 为权威 |
| 7 | 「修改后确认」（`confirmed_output_json`） | ADR-0010 §9；D5·D7·D11 收口 | 编辑后再确认 | **D7+（维持未启动）** | 未启动 |
| 8 | AgentRun action 的 role 门 | ADR-0016 已知局限；D11 收口 | Admin action 未加 role 门 | **v2** | 已登记 |
| 9 | `agents/traceability.py` run 入口规范化 | D12 收口 | 入口风格统一 | **D14** | 已登记 |
| 10 | `direction` 默认语义偏差 | ADR-0017；D12 收口 | GT-006 默认 `backward` vs 现行无向 | **待 GT 修订再对齐** | 保持双向（31/37 不漂移） |
| 11 | 类别限定候选池 | ADR-0011 §5 | v1 用全项目 `Part` | **v2** | `cost_max` 默认 `None` |
| 12 | `GIT_READONLY_ROOTS` 大小写归一 | D4 收口 ⑤ | Windows 路径大小写 | **暂缓（无归属）** | 风险极低（realpath 已解析真实大小写） |
| 13 | 本机 `.env` `GIT_READONLY_ROOTS` 漂移 | D7 收口 §十一 | 旧占位 `D:\repos\demo` 与 `.data/demo-repo` 不符 | **本机运维**（不入库） | 建议校正为 `.data`；恢复脚本已自带覆盖 |
| 14 | fixture `AR-001.output_json` 旧键 | D13 立项 | `requirement_cards` 与新 schema `cards` 不一致 | **v2（数据统一，受控改 fixture）** | 未改（超边界） |
| 15 | prompts v1 CRLF → checksum 口径 | D5 收口 ⑩ | 冻结基准换行口径 | **已完成（D5 收口）** | 已按仓库 blob 口径修正 |
| 16 | R-3 DeepSeek 无快照 id | ADR-0008 §7 | `model` 记录口径 | **已知局限（不做）** | 记录实际模型名 |

**去向分布**：D13 已闭环 **3**；D14/待裁决 **3**（#4/#9/#10）；v2 **5**（#5/#6/#8/#11/#14）；D7+ **1**（#7）；暂缓/运维 **2**（#12/#13）；已完成/已知局限 **2**（#15/#16）。

---

## 二、低成本就地处置判定

| 项 | 判定 | 理由 |
| --- | --- | --- |
| `resolve_doc_path` 搬迁（#4） | **不做** | 触及 `config/settings.py` + `core/admin.py` + `agents/requirement.py`（R2 禁改代码逻辑）；纯组织性，无功能收益 |
| PDF 占位终判（#2） | **不生成** | RUNBOOK 段 4/5/7/8 仅按编号引用 Document，**不读文件内容** → 「演示不走文件打开」 |
| `sync` 非事务说明（#3） | **已在档** | RUNBOOK 附录 B 已含逐条 upsert / 退出码 1 / 部分写入说明 |
| 大小写归一（#12） | **维持暂缓** | 无归属，风险极低 |
| traceability 入口规范化（#9） | **D14** | `agents/traceability.py` 属禁改包，R2 只登记 |
| 「修改后确认」（#7） | **维持 D7+** | 本轮不启用 |

---

## 三、D14-R1 复检清单雏形

> 从台账与各收口「未经独立复检」声明提炼，供 D14 复检轮覆盖。

1. **未闭环/待裁决项**：#4（`resolve_doc_path`）、#9（入口规范化）、#10（`direction` 默认偏差，待 GT 修订）。
2. **风险登记**：**R-1**（复检方无 key/网 → live 由执行侧举证，复检方验结构层）；**R-2**（非法 JSON/缺字段落 T2，已迁移）；**R-3**（DeepSeek 无快照 id → `model` 记录实际模型名）。
3. **评审债**：D7 / D11 / D12 三份收口均声明「**未经独立复检、freeze 待裁决**」（`d7-agent-freeze` 未打）。
4. **数据统一债**：#14（`AR-001.output_json` 旧键）、#13（本机 `.env` 漂移）。
5. **v2 承接**：#5 / #6 / #8 / #11 / #14。
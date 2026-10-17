# ThreadLink 终局报告（D14 收官）

- **版本**：D14-R3 收官
- **基准 HEAD**：`1b20c18`（D14-R2 最后提交）；`d14-final` tag **待人工下发**，**本文件不预写 tag hash**。
- **文档性质**：**引用式**终局报告——细节以被引文档为准，本文件不复制全文。
- **诚实声明（先置）**：① D14-R1 复检**独立性受限**（复检方参与 D13 修订/彩排/收口）；② **live 未由复检方执行**；③ 存在 **Won't 边界**与 **v2 未闭合项**；④ 本报告**不声称「全部通过」**。

---

## 1. 结论摘要

- **交付结论**：**PASS WITH ISSUES（受限独立）**——无 blocker；1 should-fix（SF-01 已处置）+ 3 nit（N-01 已补打 / N-02 已恢复 / N-03 盲区），见 `docs/qa/2026-10-15-d14-r1-closeout.md` §二。
- **复检基线**（来源：同上 §一）：`manage.py check` 无问题；`validate_seed.py` 通过（22 集合 / TraceLink 39 / 引用闭包完整）；`compileall` rc=0；`pytest -q -m "not live"` = **254 passed / 5 deselected**。
- **部署验证（六组数全过；来源：D14-R2 本机实测回贴）**：

| # | 组 | 实测 |
| --- | --- | --- |
| 1 | sync 跨环境 SHA 一致性 | `added=0 updated=0 missing=0` |
| 2 | bootstrap 全链 | `BOOTSTRAP OK`（migrate + seed + 终态断言） |
| 3 | `.env` 安全 | `NO_ENV_IN_IMAGE` |
| 4 | 宿主 pytest | **259 passed, 5 deselected**（254 + 5 新单测） |
| 5 | 容器 smoke | `SMOKE PASS`（23 + 2 + 9 逐条 `[PASS]`） |
| 6 | 复启存活 | Part=20 / Requirement=5 / TraceLink=39；AgentRun=5 / Bom=1 / BomItem=16 |

---

## 2. 交付范围与冻结基线

- **tag 链（实测 10 枚）**：`d1-scope-freeze` / `d2-schema-freeze` / `d3-crud-freeze` / `d4-trace-freeze` / `d5-agent-freeze` / `d6-selection-freeze` / `d7-agent-freeze` / `d11-e2e-freeze` / `d12-tests-freeze` / `d13-demo-freeze`。
  - `d7-agent-freeze^{}` = `ef4900fe9d331d1e15b05badbe9c1a07b6426c93`
  - `d13-demo-freeze^{}` = `79f4d1dfb216034e55af8b951a94defe4bf3c788`
  - 来源：`git show-ref -d --tags` 实测（见 §6 附表）。
- **`d14-final`**：**待打**——由人工在 R3 提交推送后下发命令（指向 R3 HEAD）；**不预写 hash、不留占位符**。
- **技术栈冻结**：SQLite 开发 / Postgres(pgvector) 部署（ADR-0018）；GT 分层以 SQLite 运行（ADR-0008）。
- **提交链与逐轮摘要**：`docs/qa/2026-10-12-d13-closeout.md` §1、`docs/qa/2026-10-15-d14-r1-closeout.md` §一。

---

## 3. 验证证据索引（引用，不复制）

| 验证面 | 证据位置 | 关键结论 |
| --- | --- | --- |
| 全系统独立复检（受限） | `docs/qa/2026-10-15-d14-r1-closeout.md` | PASS WITH ISSUES；SF-01 已处置；N-01/N-02 已闭环 |
| GT 38 条覆盖矩阵 | `docs/qa/2026-10-07-d12-gt-coverage-matrix.md` | 38/38「有」；R1 复检未发现不一致 |
| 部署（Compose） | `docs/adr/0018-deployment-compose.md` §5 / §9 / §10 | 六组数全过；`.env` 已排除；smoke Host 白名单 |
| 演示 runbook / 字幕 | `docs/demo/RUNBOOK.md`、`docs/demo/CAPTIONS.txt` | 段 1→9；机械执行约 3 min / 演示约 15 min（RUNBOOK §2.4） |
| 延后台账 | `docs/DEFERRED.md` §四 | 17 条终局去向 |

---

## 4. 已知限制与 Won't 边界

**限制（如实）**
1. D14-R1 复检**独立性受限**（复检方参与 D13 修订/彩排/收口）→ 结论按受限采信；
2. **live 未由复检方执行**（无 LLM 出网）；live 证据来自执行侧举证，复检方仅验结构层；
3. HTTP 权限 / 异常路径未独立构造实测（结构层由测试覆盖，见 R1 报告附录 F）；
4. 容器内**不跑 pytest、不验证 LLM/live**（ADR-0018 §5 范围声明）。

**Won't（明确不做，非缺陷）**
- gunicorn / 静态文件服务 / HTTPS / 反向代理（→ v2，ADR-0018 §7）；
- PDF 占位文件生成（演示不走文件打开，DEFERRED #2）；
- ECN 影响面自动推导（v1 以 `ECNImpact` 为权威，#6）；
- `replaces`「在列」硬执行（v1 维持 prompt 约束 + 存在性核验，#5）；
- 种子历史行 schema 化改写（**保留原貌**，DEFERRED #14 豁免口径）；
- DeepSeek 快照 id（记录实际模型名，#16）。

---

## 5. 未闭合项与去向（引用 `docs/DEFERRED.md` §一 / §四）

| 类别 | 条目 | 去向 |
| --- | --- | --- |
| 待裁决 | #4 `resolve_doc_path` 搬迁、#9 traceability 入口规范化、#10 `direction` 默认语义 | D14 视情 / 待 GT 修订 |
| v2 承接 | #5 `replaces` 硬执行、#6 ECN 自动推导、#8 action role 门、#11 类别限定候选池、#14 种子 `output_json`、#17 demo_reset 内容级非确定性 | v2（#14 或永不修） |
| D7+ | #7「修改后确认」 | 未启动 |
| 暂缓 / 运维 | #12 大小写归一、#13 本机 `.env` 漂移 | 暂缓 / 本机运维 |
| 已完成 / 已知局限 | #1/#2/#3/#15/#16 | 已闭环或已知局限 |

---

## 6. 复现与交接

- **开发路径（SQLite）**：`start_threadlink_venv.bat` → `manage.py migrate` → `load_demo_seed` → `runserver`（见 `README.md`「快速开始」/「本地开发与启动脚本」）。
- **部署路径（Compose）**：`docker compose up -d --build` → `scripts/compose_bootstrap.ps1` → `scripts/compose_smoke.ps1`（判据：`SMOKE PASS` + `sync 0/0/0`）。
- **验证路径**：`python manage.py check`；`python scripts/validate_seed.py`；`pytest -q -m "not live"`（期望 ≥259 passed）。
- **演示路径**：`docs/demo/RUNBOOK.md` 段 1→9；`start_threadlink_demo_reset.bat` 恢复终态。
- **交接注意**：`d14-final` 由人工在 R3 推送后打；打 tag 前确认 `git status` 干净、HEAD 与 `origin/main` 一致。

### 附表：tag 链解引用（`git show-ref -d --tags` 实测）

| tag | tag 对象 | `^{}` 解引用 |
| --- | --- | --- |
| d1-scope-freeze | dde5b4f | e326be4 |
| d2-schema-freeze | 2d4cc15 | 937da8d |
| d3-crud-freeze | 6d093fd | eae3e73 |
| d4-trace-freeze | 6589c78 | efd1d16 |
| d5-agent-freeze | 59dbb4c | 673d1a8 |
| d6-selection-freeze | 26433e7 | e5b94b1 |
| d7-agent-freeze | c7e7e1b | **ef4900f** |
| d11-e2e-freeze | 6e7c0b3 | ed75e29 |
| d12-tests-freeze | a2362ae | 1f49b21 |
| d13-demo-freeze | cb7550a | **79f4d1d** |

> `d14-final`：**待打**（本文不预写 hash）。
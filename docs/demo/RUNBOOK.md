# ThreadLink 演示 Runbook

- **轮次**：D13-R1
- **日期**：2026-10-08
- **前置 HEAD**：`1f49b21`（= tag `d12-tests-freeze` 指向提交）
- **演示库终态**：干净种子 + 三类各 1 条 `needs_review`（`bom_selection` run 6 / `traceability` run 7 / `requirement` run 8）
- **总时长**：约 15 分钟（9 段）

> **期望值来源标注**：本文档每段「期望输出」均注明来源——`[dry-run]` = 本批沙箱实测（2026-10-08）；
> `[D11/D12]` = 本机真实调用口径（沙箱无 LLM 出网，本批未复跑）；`[恢复脚本]` = `demo_terminal_assert.py` 断言口径。
> 严禁凭记忆编造演示效果。

---

## 0. 一页速览

| 项 | 内容 |
| --- | --- |
| 演示前 | 运行 `powershell -File scripts/demo_reset.ps1`（需 LLM 可达）→ 库回到终态 |
| 演示中 | 生成线与决策线**分离**：生成线现场产生新 run；决策线固定作用于 runs 6/7/8 |
| 演示后 | **再运行一次恢复脚本**（生成线/决策线/ECN 应用均已写库）；落档文件保留入库 |
| 段序 | 只读在前（段 1、5、6、7）；ECN 应用 = 倒数第二段（段 8）；决策线 = 段 9 |
| LLM 依赖 | 仅段 2b / 3b / 4b 生成线需 LLM；不可达时降级展示预跑 run（见 §6） |

---

## 1. 场景映射表（演示段 → 来源条目 → 载体）

| 段 | 演示场景 | 来源条目 | 载体（命令 / URL / Admin 动作） |
| --- | --- | --- | --- |
| 1 | 状态速览 · 审计队列 | AC-001 / AC-009（D11 S7） | `URL /admin/agents/agentrun/` |
| 2 | **S1 客户邮件 → 需求卡** | AC-002 / AC-003（D11 S1） | Admin Documents 上传 + 「运行 Requirement Agent」 action |
| 3 | **S2 BOM 选型** | AC-004（D11 S2） | `URL /agents/bom-selection/form/`（criteria 表单，D13 新增） |
| 4 | **S3 追溯链** | AC-005（D11 S3） | `URL /trace/serial/SN-DEMO-001/` + `manage.py run_traceability` |
| 5 | **S5 工单齐套** | AC-007（D11 S5） | `manage.py kitting_check WO-001` + WorkOrder 面板 |
| 6 | **S6 只读约束** | AC-008（D11 S6） | Admin Git repos/commits + `scripts/make_demo_repo.py --check` |
| 7 | **S4 ECN 影响投影（只读）** | AC-006（D11 S4） | `manage.py ecn_impact ECN-001` + ECN 面板「影响投影」 |
| 8 | **S4 ECN 应用（写）** | AC-006（D11 S4） | Admin ECNs action「应用 ECN」（`ecn_apply`） |
| 9 | **S7 审计 + 决策线** | AC-003 / AC-009（D11 S7） | Admin Agent runs action「批准/拒绝」（runs 6/8/7） |

---

## 2. 演示前：恢复脚本与终态断言

### 2.1 一键恢复

```powershell
# 从仓库根执行；需 .data/demo-repo 存在、LLM 可达
powershell -ExecutionPolicy Bypass -File scripts/demo_reset.ps1
```

序列（失败即中止，退出码非 0）：`make_demo_repo --check` → 删除 `db.sqlite3` → `migrate` →
`createsuperuser`（`admin`，密码取 `DEMO_ADMIN_PASSWORD`，缺省 `demo-pass-2026`）→
`load_demo_seed --flush` → 清理 `documents/uploads/` → `sync_git_repo` →
三类真实调用各 1 条（顺序固定 `bom_selection → traceability → requirement`）→
`scripts/demo_terminal_assert.py --expect full`。

- **可重复且确定性**：连续两次执行产出**逐字节一致**的终态（run id 恒为 6/7/8）。
- **离线自检**（沙箱无 LLM）：加 `-SkipLive`，跳过三类真实调用，终态断言降级 `--expect base`。

### 2.2 终态断言内容（`scripts/demo_terminal_assert.py`）

- **22 集合计数**：`project 1 / users 5 / parts 20 / part_params 36 / suppliers 3 / supplier_parts 13 /
  requirements 5 / requirement_params 12 / boms 1 / bom_items 16 / inventory_lots 3 / work_orders 1 /
  purchase_orders 5 / test_cases 10 / test_runs 12 / ecns 2 / ecn_impacts 8 / trace_links 39 /
  documents 5 / git_repos 1 / git_commits 3 / agent_runs 8`；
- **AgentRun 矩阵**（8 行）：`bom_selection {failed:1, needs_review:1, success:1}`、
  `requirement {success:1, needs_review:1}`、`traceability {success:2, needs_review:1}`；
- **关键不变量**：`BI-001.part = PART-001`（种子态）、无 `TC-009` `affects` 边；
- **run id 分配**：`6=bom_selection / 7=traceability / 8=requirement`（均 `needs_review`）。

> `[恢复脚本]` 本批沙箱 `-SkipLive` 幂等验证：两次运行输出**逐字节一致**，终态断言 `[OK]`；
> `sync_git_repo = added=0 updated=0 missing=0`；`load_demo_seed` 22 集合计数与上表一致。

---

## 3. 15 分钟分段脚本

### 段 1 — 开场 · 只读状态速览（1 min）

- **目标**：30 秒建立「这是什么系统」；展示审计队列与四值。
- **操作**：
  1. 浏览器登录 `http://127.0.0.1:8000/admin/`（`admin` / `demo-pass-2026`）。
  2. 打开 `http://127.0.0.1:8000/admin/agents/agentrun/`。
- **期望输出**：AgentRun 队列 **8 行**，矩阵 `bom_selection(failed1/success1/needs_review1)`、
  `requirement(success1/needs_review1)`、`traceability(success2/needs_review1)`。
- **踩点**：指出 `failed` 行（run 5）是**刻意的防幻觉样例**——系统不隐藏失败。
- **来源**：`[dry-run]` 8 行 + `[恢复脚本]` 矩阵。

### 段 2 — S1 客户邮件 → 需求卡（2 min，生成线）

- **目标**：文档入库（真实上传）+ 需求提取 Agent。
- **操作**：
  1. Admin → **Documents** → *Add document*：Project `DEMO-GW`、Title「客户邮件（便携式工业网关）」、
     Doc type `email`、Uploaded by `admin`、文件选 **`docs/demo/assets/customer-email.eml`** → Save。
  2. 回到 Documents 列表，勾选刚上传的文档 → action「**运行 Requirement Agent（生成需求卡）**」→ 运行。
- **期望输出**：
  - 上传 detail：`checksum = 708d5f20e797aefecd600b4129ce1202b955ca06daf8e164d15c7c5309dca119`、
    `size = 628`（字节）、`mime_type`（浏览器上报，典型 `message/rfc822`）、`is_readonly = True`；
  - 任务消息「…：**5 张卡片**进入待确认」；AgentRun 队列新增 1 条 `requirement` `needs_review`（现场新 run，id 9）。
  - 5 张卡标题：宽压直流供电 / 宽温工作范围 / IP65 防护等级 / BOM 成本上限 / 工业以太网接口。
- **降级**（时间紧或 LLM 不可达）：**直接展示预跑 run 8**（同 5 张卡）+ 口述「邮件见种子 DOC-001」。
- **时间预算**：2 min（上传 0.5 + Agent 1.5）。
- **踩点**：邮件 5 条诉求 ↔ 5 张卡的对应；每张卡 `source_refs` 指向该 Document（AC-002/AC-003）。
- **来源**：上传三件套 `[dry-run]`（`customer-email.eml` 实测 sha256/size）；5 卡标题
  `[D11/D12]`（run 8 `output_json.cards`）。

### 段 3 — S2 BOM 选型 criteria 表单（2 min，生成线）

- **目标**：确定性引擎打分 + LLM 只写解释文案。
- **操作**：浏览器打开 `http://127.0.0.1:8000/agents/bom-selection/form/` → 表单已预填演示 criteria
  （9/36 V、≥5 A、−40~85 °C、IP65；`cost_max` 留空）→ 点「**运行选型**」→ 自动重定向到新 AgentRun detail。
- **期望输出**（`candidates=3`、`recommended=PART-002`）：
  | 候选 | score | unit_price | lead_time_days | replaces_part_id |
  | --- | --- | --- | --- | --- |
  | PART-002 | 0.9479 | 45.0000 | 14 | PART-017 |
  | PART-001 | 0.8724 | 40.0000 | 21 | PART-017 |
  | PART-018 | 0.0 | 88.0000 | 90 | （无） |
  每候选 `rationale` 中文非空、`source_refs` 非空。
- **降级**：展示预跑 **run 6** 的 detail（上述数值来自其 `output_json`）。
- **时间预算**：2 min。
- **踩点**：分数/价格/交期来自**确定性引擎**（`core/selection.py`，冻结），LLM 只解释——「引擎权威」。
- **来源**：`[D11/D12]` run 6 `output_json`（本批实读）。

### 段 4 — S3 追溯链（1.5 min，只读 + 生成线）

- **目标**：从成品序列号反向追溯到需求/文档/Git。
- **操作**：
  1. 浏览器打开 `http://127.0.0.1:8000/trace/serial/SN-DEMO-001/`（默认双向全链）。
  2. 生成线（可选）：`.venv\Scripts\python.exe manage.py run_traceability SN-DEMO-001`
     → 新 run `needs_review` + 中文 summary。
- **期望输出**：`found=True`、`root=SN-DEMO-001`、`nodes=31`、`edges=37`、`missing=[]`、`complete=True`；
  每个节点 `source_refs` 非空。
- **时间预算**：1.5 min。
- **踩点**：链覆盖需求 REQ-001…005、BOM-001、文档 DOC-001/003/005、采购 PO、ECN、库存批次、测试用例、Git 提交。
- **来源**：`[dry-run]` `/trace/serial/SN-DEMO-001/?format=json` 实测。

### 段 5 — S5 工单齐套（1.5 min，只读）

- **目标**：缺料 + 在途 + 替代项。
- **操作**：`.venv\Scripts\python.exe manage.py kitting_check WO-001`；
  或 Admin → WorkOrders → WO-001 detail「齐套摘要（只读）」面板。
- **期望输出**：`工单 WO-001 / BOM BOM-001 / 数量 10.0000`、`齐套：否`、**缺料 13 项**；
  重点两行：
  - `PART-005: 需求 10 / 可用 0 / 缺口 10 / 在途 0 / 最晚到货 None / critical_shortage`
  - `PART-006: 需求 20 / 可用 0 / 缺口 20 / 在途 200 / 最晚到货 2026-03-06 / insufficient=False`
- **时间预算**：1.5 min。
- **踩点**：`PART-006` 在途 200 来自采购单链路（`ordered_by` 边的 `metadata.quantity`）。
- **来源**：`[dry-run]` 实测。

### 段 6 — S6 只读约束（1 min，只读）

- **目标**：外部 Git 仓库与同步记录**不可写**。
- **操作**：
  1. Admin → **Git repos** / **Git commits**：确认列表**无 Add 按钮**、detail 全字段只读。
  2. `.venv\Scripts\python.exe scripts\make_demo_repo.py --check`。
- **期望输出**：`[OK] 生成 SHA 与 fixtures 完全一致（确定性通过）`；
  3 SHA：`e4738a67bbe0fec85fe2e5b9258c533270b5e00f` / `c6b024f590785d23aa5ebb52693bb63fc1655519` /
  `944c52040a8870eff12a2355a4c81fcb1d376711`；`GitRepo/GitCommit` 写方法 `add/change/delete = False`。
- **时间预算**：1 min。
- **踩点**：AC-008 只读约束（写方法 403/404 + mtime/commit 不变）。
- **来源**：`[dry-run]` `--check` 实测。

### 段 7 — S4 ECN 影响投影（1 min，只读）

- **目标**：应用前的**零写**影响分析。
- **操作**：`.venv\Scripts\python.exe manage.py ecn_impact ECN-001`；
  或 Admin → ECNs → ECN-001 detail「影响投影（只读，D11-R2）」面板。
- **期望输出**：
  - `ECN ECN-001 / status=approved / effective=True / warnings=[]`
  - `[bom_nodes] 1` → `BI-001`；`[inventory_lots] 1` → `LOT-DCDC-001`；
    `[purchase_orders] 1` → `PO-001`；`[test_cases] 2` → `TC-001`、`TC-009`
  - `[consistency] missing_affects_edge:test_case:TC-009`
- **时间预算**：1 min。
- **踩点**：分析**不改任何实体**；`consistency` 提示应用前缺一条 `affects` 边。
- **来源**：`[dry-run]` 实测。

### 段 8 — S4 ECN 应用（倒数第二段，1.5 min，**写**）

- **目标**：唯一写路径——写回 `BomItem.part` + 补确认 `affects` 边。
- **操作**：Admin → **ECNs** → 勾选 `ECN-001` → action「**应用 ECN（写回 BomItem.part + 确认 affects 边）**」。
- **期望输出**：消息「`ECN-001 已应用：新建边 1、补确认 0、写回 BI-001:PART-001→PART-002`」；
  `BI-001.part = PART-002`；`TraceLink 39 → 40`（新增 `TC-009` `affects` 边）。
- **时间预算**：1.5 min。
- **踩点**：这是写操作，**改变 BI-001 与 TL 计数**；演示后必须跑恢复脚本。
- **来源**：`[D11]` S4 实测（`created_edges=1`；`rewritten=[BI-001: PART-001→PART-002]`；`TraceLink 39→40`）。

### 段 9 — S7 审计 + 决策线（2.5 min，**写**）

- **目标**：人工确认/拒绝——「确认 = 决策，非橡皮图章」；补齐四值矩阵。
- **操作**（Admin → **Agent runs**，顺序固定）：
  1. 勾选 **run 6**（`bom_selection`）→ action「**批准**」。
  2. 勾选 **run 8**（`requirement`）→ action「**拒绝**」。
  3. **run 7**（`traceability`）**保持 `needs_review`**（留作审计展示）。
- **期望输出**：
  - run 6 approve → 消息「`#6 已批准：BOM BOM-002，3 项，2 条替代链接`」；
    `Bom 1 → 2`、`BomItem 16 → 19`、`TraceLink +2`（`PART-002→PART-017`、`PART-001→PART-017`）；
  - run 8 reject → 消息「`#8 已拒绝`」；`status = rejected`；落档
    `prompts/requirement_agent/v1/failures/<日期>-human-rejected-8.md`；
  - run 7 → 仍 `needs_review`。
- **时间预算**：2.5 min。
- **踩点**：最终四值齐备——`failed = run 5`（种子防幻觉）、`needs_review = run 7`、
  `success = run 6 + 种子`、`rejected = run 8`。
- **来源**：`[dry-run]` 决策线实测（见 §5）。

---

## 4. 演示期间的写入与收尾

### 4.1 生成线与决策线分离（核心纪律）

- **生成线**（段 2b / 3b / 4b）：现场触发 Agent，**产生新 run**（顺序 id 9/10/11，均 `needs_review`），
  只作**展示**；其内容/措辞跨次可变（LLM 非确定性），**不作为决策对象**。
- **决策线**（段 9）：**固定作用于 runs 6/7/8**，顺序 `6 approve → 8 reject → 7 保留`。
  6/7/8 的内容与期望值已在 D6/D7/D11 报告锁定，runbook 引用精确数字，符合「先跑后写」。
- 四值矩阵最终同时含**存量 + 现场新增**，叙事更强：「现场生成的行实时出现在审计列表里」。

### 4.2 S7 审计矩阵双口径

| 口径 | S3（段 4b）是否现场跑 agent | 新 run | AgentRun 总数 |
| --- | --- | --- | --- |
| A | 跑（+1） | 9/10/11 | 11 |
| B | 不跑 | 9/10 | 10 |

> 两个口径的**存量 8 行**不变；只是现场新增行数不同。dry-run 按实际执行固化。

### 4.3 落档处置

- 演示现场 `reject run 8` 生成的 `human-rejected-8.md` **保留并随收口入库**
  （先例：D7-R3 `human-rejected-11`）。
- 落档为**历史事件记录**：跑恢复脚本还原库状态后，**不要求库状态与历史落档一一对应**。

### 4.4 收尾

1. （若需要复现）运行 `powershell -File scripts/demo_reset.ps1` 回到终态。
2. `documents/uploads/` 的演示上传产物由恢复脚本清理；`documents/` 根下的种子文件（DOC-001/002）不受影响。

---

## 5. 决策线细则（runs 6/7/8）

| run | agent | 动作 | 期望输出 | 来源 |
| --- | --- | --- | --- | --- |
| 6 | `bom_selection` | **approve** | `BOM-002` / `version=v0.1-sel-6` / `status=draft` / `items=3` / `substitute_group=SG-SEL-6` / `links=2`；run 6 → `success` | `[dry-run]` |
| 8 | `requirement` | **reject** | status → `rejected`、`confirmed_by=admin`；落档 `<日期>-human-rejected-8.md` | `[dry-run]` |
| 7 | `traceability` | **保留** | 仍 `needs_review` | `[dry-run]` |

**决策后四值矩阵**（存量 + run 6/8 动作，不含生成线新 run）：

| agent_name | failed | needs_review | success | rejected |
| --- | --- | --- | --- | --- |
| bom_selection | 1（run5） | 0 | 2（run2,run6） | 0 |
| requirement | 0 | 0 | 1（run1） | 1（run8） |
| traceability | 0 | 1（run7） | 2（run3,run4） | 0 |

**决策后实体计数**（不含生成线/ECN 应用）：`Bom 2` / `BomItem 19` / `TraceLink 41`（39 + 2）。

> `[dry-run]` 本批沙箱实测：`approve_bom_selection(run 6)` → `{'bom_no': 'BOM-002', 'items': 3, 'links': 2}`；
> `reject(run 8)` → `rejected`；`run 7` 保持 `needs_review`；`TraceLink 39 → 41`。实测后已按备份还原 prod DB（见 §7 偏差）。

---

## 6. 降级预案

| 场景 | 预案 |
| --- | --- |
| **LLM 不可达** | 段 2b/3b/4b 生成线改**展示预跑结果**（run 6/7/8）；**不伪造** live 输出；必要时延后录制或换机 |
| **现场 live 调用失败** | 重试 ≤1 次；仍失败 → 话术「看，失败也会被如实记录为 `failed`——这正是审计真实性」（引 run 5 先例），**继续下一段，不阻塞、不现场排障** |
| **Git 只读断言展示方式** | Admin detail 无编辑控件 + `make_demo_repo.py --check` 输出 |
| **中途状态损坏** | 运行 `scripts/demo_reset.ps1` 回到终态；或按 §2 指引 |

---

## 7. 附录

### 附录 A — 演示禁用操作清单

- ❌ 演示中途修改 `fixtures/`、`rules/`、`schemas/`、`models/`。
- ❌ 删除或修改任何 `AgentRun` 行（审计记录不可删）。
- ❌ 对 **run 7** 执行 approve/reject（须保留 `needs_review` 供 S7 展示）。
- ❌ 反复执行 ECN 应用 action（写路径非幂等展示，一次即可）。
- ❌ 直接改 `db.sqlite3`（状态恢复一律走 `scripts/demo_reset.ps1`）。
- ❌ 打开 `DOC-003/004/005` 引用的 PDF 文件（占位文件不存在，见附录 C）。
- ❌ 演示中途 `git commit` / `git push`。
- ❌ ECN 应用（段 8）后不跑恢复脚本就结束演示。

### 附录 B — `sync_git_repo` 非事务说明（D13 台账）

`sync_git_repo` 对每个 `GitRepo` **逐条 upsert**，**非整体事务**：

- 仓库有 / DB 无 → 新增 `GitCommit`；两侧都有 → 以仓库为准更新 metadata；
- DB 有 / 仓库无 → 列出明细并以**退出码 1**结束（可能被 TraceLink 引用，禁止自动清理）；
- 中途失败可能留下**部分写入**。

> 演示前用 `make_demo_repo.py --check` 确认零差异；恢复脚本终态断言 `sync = added=0 updated=0 missing=0`。

### 附录 C — PDF 占位判定（D13 台账）

- `DOC-003/004/005` 引用 `documents/sch-power.pdf`、`documents/test-report-SN-DEMO-001.pdf`、
  `documents/spec-enclosure.pdf`，**磁盘上实际不存在**（占位；fixture 中 checksum/size/mime 为登记值）。
- **本 runbook 判定：演示不走文件打开。** 段 4（追溯）/段 7–8（ECN）/段 5（齐套）均**只按编号引用**这些
  Document（`source_refs` / `evidence` 的 `id`），**不读取文件内容** → **不生成占位 PDF**，登记「演示不走文件打开」。
- 若未来演示需真实打开文件 → 须生成占位并回填**三件套**（checksum + size + mime）。

### 附录 D — 本批 dry-run 记录（2026-10-08，沙箱）

命令真实输出（节选）：

| 命令 | 关键输出 |
| --- | --- |
| `make_demo_repo.py --check` | `[OK] 生成 SHA 与 fixtures 完全一致`；3 SHA 如上 |
| `validate_seed.py` | `[OK] 种子校验通过…顶层键 22 个；TraceLink 39 条；引用闭包完整。` |
| `kitting_check WO-001` | `齐套：否`；缺料 **13** 项；PART-005 critical / PART-006 在途 200 到货 2026-03-06 |
| `ecn_impact ECN-001` | `effective=True`；bom_nodes 1 / inventory_lots 1 / purchase_orders 1 / test_cases 2；`missing_affects_edge:test_case:TC-009` |
| `bom_expand BOM-001` | 顶层 4 项；`--hierarchy` 17 行、totals 15 项（PART-009 聚合 28） |
| `/trace/serial/SN-DEMO-001/?format=json` | `found=True`；`nodes=31`；`edges=37`；`missing=[]`；`complete=True` |
| URL 可达性（登录后） | `/admin/` `/admin/agents/agentrun/` `/admin/core/{document,ecn,workorder,gitrepo}/` `/agents/bom-selection/form/` `/trace/serial/SN-DEMO-001/` → 200；`/agents/requirement/run/` → 405（require_POST，端点存在） |
| `demo_reset.ps1 -SkipLive` ×2 | 两次输出**逐字节一致**；终态断言 `[OK]`（`expect=base`）；`sync=0/0/0` |

**未在沙箱复跑**（无 LLM 出网）：段 2b/3b/4b 生成线、`run_bom_selection`/`run_traceability` 的 live 调用、
`demo_reset.ps1` 的 full 路径（第 7 步三类真实调用）。上述期望值引用 `[D11/D12]` 本机实测口径；
**待本机执行 `scripts/demo_reset.ps1`（full）以复现终态并采集最后一段证据。**

---

## 附：相关记忆/台账处置（D13-R1）

| 台账项 | 本批处置 |
| --- | --- |
| rationale 截断 | ✅ 本批：plumb `…` 标注 + `--full` 旗标（`run_bom_selection`） |
| criteria 表单 | ✅ 本批：`/agents/bom-selection/form/`（`agents/admin.py` + `config/urls.py`） |
| 占位 PDF 三件套 | ✅ 本批判定：演示不走文件打开 → 不生成（附录 C） |
| `sync` 非事务说明 | ✅ 本批：入 runbook 附录 B |
| `resolve_doc_path` 搬迁 nit | 本批**未动**（不属于规则内允许改动面；判定延后 D14，见汇报） |
| `agents/traceability.py` run 入口规范化 | 已定 D14（`agents/` 禁改边界） |
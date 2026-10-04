# D1 增量复检报告归档（2026-10-04）

> 归档说明：以下「增量复检报告原文」由 D1 增量复检会话产出，归档时**逐字保留、未作改动**；本轮收口微修的批注统一置于文末「批注区（收口微修）」，不改动原文。

---

D1 增量复检报告
基准 commit：43f4cdce7dabd1d320ed16638a308aa041db9780   复检时间：2026-10-04
提交轨迹：329320f（复检基线）→ b32ee21（修复轮）→ b57d370（微修）→ 43f4cdc（微修）；工作区干净
结论：PASS WITH ISSUES（受限）  — 0 blocker / 1 should-fix / 2 nit
（“受限”= 本会话曾参与本批修复，独立性不达标，见附录 E）

发现列表（按严重级）
- [should-fix] SF-01 | B5 契约一致性 | docs/golden_tests.md:93 | §2.5「根实体存在但无 TraceLink」条目仅写
  `found=true`、`nodes 含根节点`、`warnings 含"未建立追溯链"`，未声明 `complete=false` 与
  `missing=["no_trace_links"]`；M-01 对齐时只更新了同节的 `found=false` 条目（L92）。与 M 定稿的机器字段
  口径不完整对齐（因 `warnings` 已被 M 明确“不作机器判定依据”），非硬冲突（GT-TRACE-003 已给全）。
  | 证据：read golden_tests L86-94；ADR-0002:35 表行 `true|false|含根节点|missing=["no_trace_links"]`；
  GT-TRACE-003:499 | 建议：L93 补 `complete=false`、`missing=["no_trace_links"]`。

- [nit] N-01 | A2 文档格式 | docs/adr/0002-empty-chain-and-reference-verification.md:57-58 | 列表项
  `- 本 ADR 只冻结契约…`（L57）与 `## Amendment`（L58）之间缺空行；CommonMark 下标题仍可中断列表，渲染
  无碍，但与全文其余节间空行风格不一致 | 证据：read L50-63 | 建议：L57 后补一空行。

- [nit] N-02 | 归档一致性 | docs/qa/2026-10-04-d1-recheck.md:195 | 批注区记 COUNT_MIN 为
  `test_runs ≥10 / part_params≥30 / boms≥1 / git_commits≥3`，与 HEAD 不符：`test_runs` 已移入
  `COUNT_EQUALS ==12`（b57d370），并新增 `trace_links ≥30`（43f4cdc）。批注未随微修更新（代码本身正确）。
  | 证据：read validate_seed.py:143-160（COUNT_EQUALS 含 test_runs:12；COUNT_MIN 含 trace_links:30）；
  git log b57d370/43f4cdc | 建议：更新批注 L195，或加“微修后口径”附注。

附录
- A 反例实测结果（系统 Python + pydantic 2.13.5，导入 schemas.agent_outputs.TraceabilityAgentOutput）
  8/8 全部符合预期：
   拒绝 complete=false∧missing=[]（"missing 为空时 complete 必须为 True"）
   拒绝 found=false∧nodes 非空（"found=False 时 nodes 必须为空"）
   拒绝 found=false∧complete=true（"found=False 时 complete 必须为 False"）
   拒绝 found=true∧nodes=[]（"found=True 时 nodes 至少包含根节点"）
   拒绝 complete=true∧missing 非空（"complete=True 时 missing 必须为空"）
   接受 found=false + nodes=[] + complete=false + missing=["serial_not_found"]
   接受 found=true + 根节点 + missing 非空 + complete=false
   接受 found=true + 根节点 + missing=[] + complete=true
  → 覆盖 B2 要求的全部拒绝/接受面向，并额外覆盖“found=false 合法空链”正例。

- B 定向破坏结果（含阴性对照）9/9：复制 fixture 到仓库外执行 validate_seed.py <副本>
   阴性对照(原样) rc=0
   parts 改数(删 PART-001) rc=1（16 项）
   test_runs 12→11 rc=1（1 项）
   删 AR-005 rc=1（防幻觉样例缺失）
   AR-005 status→success(无 confirmed) rc=1（2 项）
   删停产料 PART-017 rc=1（4 项）
   删长交期 SupplierPart(>60) rc=1（1 项）
   TraceLink to_id 悬空 rc=1（引用闭包）
   id≠编号字段 rc=1（16 项）；重复 id rc=1（2 项）

- C 复算/复现数值
  1) GT-BOM-008 构造集独立重算：cost C1=1.0/C2=0/C3=0；lead C1=1/C2=1/C3=0；
     multi C1=0/C2=1/C3=0.5 → 总分 80 / 50 / 10，与文档期望一致（nrnd 边界仅新增构造口径，未改期望）。
  2) GT-BOM-009 全表基线独立重算：阶段 1 通过 3（PART-001/002/018），排除 17
     （missing_param×14、current_below_min×1[PART-011]、temp_out_of_range×1[PART-012]、
     lifecycle:obsolete×1[PART-017]）；Top3 = PART-002 94.79 / PART-001 87.24 / PART-018 0.00。
     明细：PART-001 40.00/21/2（SP-003 eol 排除）、PART-002 45.00/14/3、PART-018 88.00/90/1。
  3) 基线三命令全过（输出见附录 D）。
  4) EntityType(13) == data_dictionary §0.1 端点=是(13)；fixture TraceLink 实际使用 12 类，
     全部落在白名单内，无超集（`supplier` 未用到，允许）。AgentRun.references 中的 `trace_link`
     属 ReferenceType（合法含 trace_link），非 EntityType，未计入。

- D 命令清单
  1) git rev-parse HEAD → 43f4cdce7dabd1d320ed16638a308aa041db9780
  2) git log -5 --format="%h %s" → 43f4cdc/b57d370/b32ee21/329320f/9f57f7d
  3) git status --short → 空（复检前后一致）
  4) .venv/Scripts/python.exe manage.py check → System check identified no issues (0 silenced)
  5) .venv/Scripts/python.exe scripts/validate_seed.py → OK（顶层键 22、TraceLink 39、引用闭包完整）
  6) .venv/Scripts/python.exe -m compileall -q agents scripts schemas → 成功（无输出）
  7) 仓库外脚本：rc_md_gap.py（md 表格空行扫描，0 命中）、rc_entitytypes.py、rc_invariants.py、
     rc_breaks.py、rc_scoring.py；用毕已删除
  8) grep：正交 / no_trace_links / KNOWLEDGE_ITEM / output_valid|llm_output|run_error|record_id /
     作废编号 / status.*approved

- E 盲区声明
  1) 独立性声明：本会话前段实际参与本批修复（修复轮 b32ee21 与微修 b57d370/43f4cdc），未满足“复检者
     未参与任何修订”的独立性要求。本轮全部结论均以重新读取仓库文件、重新运行命令与自行构造脚本取证，
     未引用任何汇报文字；但先验知识无法完全消除，故结论标注 PASS WITH ISSUES（受限）。
  2) HTTP 行为未实测：GT-TRACE-003 的 HTTP 200 + mock LLM 断言、AC-009 端点行为均为文档级审查，
     D1 无实现环境，留待 D12 交付后验证。
  3) 评分实现一致性未验证：仅验证规则文件 + ADR-0005 文本 + fixture 独立重算；D12 实现代码尚不存在。
  4) 非 TraceLink 域（ECN/TestRun 等）数值断言未逐条重算，超出清单范围。
  5) 环境差异：.venv 无 pydantic，契约反例实测使用系统 Python（pydantic 2.13.5）；schemas 为纯契约
     模块、不被 Django 加载，结果不受影响。
  6) 仓库路径以实际 C:\Users\Lenovo\Desktop\Threadlink\threadlink 为准。
  7) 不声称“全部通过”；上述 SF-01/N-01/N-02 为遗留问题。

报告写完即止，未对仓库做任何修改；临时脚本位于仓库外且已删除，复检前后 git status 一致。

---

## 批注区（收口微修）

> 本节为收口微修新增，**不改动上方原文**。基准：HEAD `43f4cdc`。本批只做 SF-01/N-01/N-02 修复、venv 依赖补齐、归档增量复检报告四项。

- **独立性声明（受限）**：执行本轮收口微修者为参与过本批修复（b32ee21/b57d370/43f4cdc）与增量复检的同一会话，独立性不达标；增量复检报告原文保留其 `PASS WITH ISSUES（受限）` 结论与附录 E 声明，未改写。
- **SF-01 已修复**：`docs/golden_tests.md` §2.5「根实体存在但无 TraceLink」条目补 `complete = false`、`missing = ["no_trace_links"]`（机器 token），`warnings` 保留并标注「人类可读镜像，不作机器判定依据」，与 GT-TRACE-003 边界 1、ADR-0002 表行逐字一致。
- **N-01 已修复**：`docs/adr/0002-empty-chain-and-reference-verification.md` L57 列表项与 `## Amendment` 标题之间补空行，恢复节间空行风格。
- **N-02 已修复**：`docs/qa/2026-10-04-d1-recheck.md` 批注区补「微修后口径」条目，记 `test_runs` 已入 `COUNT_EQUALS ==12`、`COUNT_MIN` 现含 `trace_links ≥30`；原文保留留痕。
- **venv 依赖已补齐**：`uv pip install -r requirements/dev.txt`（项目 venv，uv 0.12.23）；`.venv` 内 `import pydantic` → `2.13.5`、`import schemas.agent_outputs` → `OK`；主 venv 复跑 4 个 validator 用例 4/4 符合预期。原「venv 无 pydantic」滚动盲区已消除。
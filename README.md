# Threadlink

面向中小机电研发团队的单租户轻量研发追溯平台：以 TraceLink 追溯元数据为主线管理需求、BOM、测试、库存、采购与 ECN，只读关联 Git 与文件，并用可审计的 AI 智能体辅助物料选型与全链路追溯。

## 快速开始（Windows）

> 新克隆者最短路径；各分区细节见下文对应章节。

1. **前置**：Python 3.13、Git；PowerShell（或下文 `.bat` 启动器）。
2. **克隆 + 虚拟环境 + 依赖**：

   ```cmd
   git clone <repo-url> threadlink && cd threadlink
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements\dev.txt
   ```

3. **配置 `.env`**：`copy .env.example .env`，至少填 `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_BASE_URL`（全量键见「环境变量」节）。
4. **建库 + 种子 + 演示仓库**：

   ```cmd
   .venv\Scripts\python.exe manage.py migrate
   .venv\Scripts\python.exe scripts\make_demo_repo.py          :: 生成确定性演示 Git 仓库
   .venv\Scripts\python.exe manage.py createsuperuser          :: 用户名填 admin（供演示登录）
   .venv\Scripts\python.exe manage.py load_demo_seed --flush
   set GIT_READONLY_ROOTS=.data
   .venv\Scripts\python.exe manage.py sync_git_repo
   ```

5. **启动**：`start_threadlink_admin.bat`（推荐，自动打开 admin）或 `.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000`。
6. **登录**：http://127.0.0.1:8000/admin/ （`admin` / 你设置的密码）。

> **一键演示**：熟悉后可直接双击 `start_threadlink_demo_reset.bat`，确定性重建演示库到终态（含三类真实调用，需 LLM 可达）。

## 环境变量（`.env`）

完整键位以 `.env.example` 为准：

| 键 | 说明 |
| --- | --- |
| `DJANGO_SECRET_KEY` / `DJANGO_DEBUG` / `DJANGO_ALLOWED_HOSTS` | Django 基础配置 |
| `DATABASE_URL` | 数据库（开发 SQLite；目标 PostgreSQL） |
| `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_BASE_URL` | LLM 端点与模型（key 与 base 须同源） |
| `LLM_BACKEND` | `openai`（默认）或 `fake`（离线回放，**不落 AgentRun**） |
| `LLM_TIMEOUT` / `LLM_MAX_RETRIES` | 超时 / 重试上限 |
| `LLM_STRUCTURED_MODE` | `auto`（默认，`json_schema`→`json_object` 自动降级）/ `json_schema` / `json_object` |
| `LLM_EXTRA_BODY` | 通用 provider 参数（JSON；DeepSeek 推荐 `{"thinking": {"type": "disabled"}}`） |
| `VECTOR_STORE` / `CHROMA_DIR` | 向量库预留配置 |
| `GIT_READONLY_ROOTS` | Git 只读白名单（`sync_git_repo` 用；Windows `;` 分隔，相对 `BASE_DIR`） |
| `GIT_ALLOW_WRITE` | 默认 `0`（只读；勿改） |

## Must（必须做）

1. 单租户登录 + 项目管理。
2. 核心实体：需求、参数、BOM、物料、供应商、库存批次、采购单、测试、ECN、文件、Git 提交、追溯元数据。
3. TraceLink 追溯元数据表，所有关联都走它。
4. Requirement Agent：PRD/SOR/邮件 → 需求卡 → 人工确认 → 写追溯链。
5. BOM/选型 Agent：参数过滤 + 规则评分 + LLM 解释 → 候选料/初版 BOM。
6. Traceability Agent：序列号/批次/样机 → 反查需求、图纸、物料、采购、测试、ECN、Git。
7. Git 与文件只读关联。
8. AgentRun 审计：凡经 LLM 推理的智能体调用记录输入、输出、引用、确认人；纯数据查询不产生 AgentRun。

## Won't（明确不做）

- 真实 ERP/MES/供应商 API。
- CAD/EDA 文件深度解析。
- 多租户、复杂 RBAC。
- 自动下单、自动发邮件、自动改 BOM。
- 自主多智能体循环。
- 模型微调。

## 最小数据模型

- 项目与用户：`Project`, `User`
- 物料与供应：`Part`, `PartParam`, `Supplier`, `SupplierPart`
- 需求：`Requirement`, `RequirementParam`
- BOM：`Bom`, `BomItem`
- 库存与采购：`InventoryLot`, `WorkOrder`, `PurchaseOrder`
- 测试：`TestCase`, `TestRun`
- 变更：`ECN`, `ECNImpact`
- 追溯与文档：`TraceLink`, `Document`
- Git：`GitRepo`, `GitCommit`
- 智能体：`AgentRun`

## 技术栈

- Django + Django Admin/HTMX
- SQLite/PostgreSQL

- OpenAI SDK
- GitPython
- pdfplumber

## 本地开发与启动脚本

项目提供 4 个 Windows 批处理启动器，双击或命令行运行即可（均 `chcp 65001` UTF-8、自动进入项目根目录）：

| 脚本 | 用途 | 依赖 |
| --- | --- | --- |
| `start_threadlink_admin.bat` | 一键启动 Django 开发服务器（清理 `8000` 僵尸进程 + 看门狗 + 自动打开 admin） | `.venv`、Microsoft Edge |
| `start_threadlink_venv.bat` | 打开**已激活 `.venv`** 的交互式 cmd（提示符显示 `(.venv)`），可直接 `python manage.py ...` | `.venv` |
| `start_threadlink_shell.bat` | 打开**普通** cmd（仅切到项目根，**不激活** venv），用于需要系统 `python` 或纯 cmd 操作的场合 | 无 |
| `start_threadlink_demo_reset.bat` | 演示前一键重建演示库到终态（调用 `scripts/demo_reset.ps1`） | `.venv`、LLM 可达 |

> **`powershell` 不在 PATH 时**：`start_threadlink_demo_reset.bat` 已内置
> `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe` 全路径回退；若需手工调用，用
> `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File scripts\demo_reset.ps1`，
> 或先打开 PowerShell 窗口再执行 `.\scripts\demo_reset.ps1`。

### start_threadlink_admin.bat —— 开发服务器

功能：

1. **激活虚拟环境**：调用 `.venv\Scripts\activate.bat`。
2. **启动前清理僵尸进程**：在打开浏览器之前，结束占用 `8000` 端口的旧 `python.exe`。
3. **启动独立看门狗**：另起一个独立进程，基于主窗口 PID 轮询；主窗口关闭后自动杀掉占用 `8000` 的残留进程。
4. **启动 Django 开发服务器**：`python manage.py runserver 127.0.0.1:8000 --noreload`（`--noreload` 关闭自动重载，减少 Windows 上关窗后残留的子进程）。
5. **自动打开管理后台**：服务器就绪后延迟 5 秒，用 Microsoft Edge 打开 `http://127.0.0.1:8000/admin/`。
6. **停止后清理**：`Ctrl+C` 停止服务后再清理一次僵尸进程。

### 僵尸进程清理机制

Windows 下直接关闭控制台窗口会立即终止批处理，脚本末尾的清理代码不会执行，`runserver` 的 `python` 进程可能残留并占用 `8000`。脚本通过以下四重保障确保端口始终可用：

1. 启动前清理占用 `8000` 的旧进程；
2. 独立 PID 看门狗，在主窗口关闭后自动回收；
3. `Ctrl+C` 停止后再次清理；
4. `--noreload` 减少残留子进程。

### 依赖

- 已创建虚拟环境 `.venv`（`python -m venv .venv`）。
- 已安装 Microsoft Edge。

### 使用

```cmd
start_threadlink_admin.bat
```

### 验证

关闭服务器窗口后执行以下命令，应无 `LISTENING` 输出：

```cmd
netstat -ano | findstr ":8000"
```
### start_threadlink_venv.bat —— 虚拟环境 Shell

在项目根目录打开一个**已激活 `.venv`** 的交互式 cmd：调用 `.venv\Scripts\activate.bat`，再以 `cmd /k` 保持窗口；提示符前显示 `(.venv)`，可直接执行 `python manage.py ...`；输入 `exit` 关闭窗口。

使用：

```cmd
start_threadlink_venv.bat
```

手动等价操作：

```cmd
cd /d C:\Users\Lenovo\Desktop\Threadlink\threadlink
.venv\Scripts\activate.bat
```

依赖：已创建虚拟环境 `.venv`（`python -m venv .venv`）。

### start_threadlink_shell.bat —— 普通 Shell

在项目根目录打开一个**未激活虚拟环境**的普通 cmd（仅 `cd` 到项目根 + `cmd /k`）。适合需要系统 `python`、或不想让 `.venv` 抢先解析 `python` 的场合。

使用：

```cmd
start_threadlink_shell.bat
```

> 与 `start_threadlink_venv.bat` 的区别：本脚本**不**调用 `activate.bat`，提示符不带 `(.venv)`，`python` 解析为系统解释器。

### start_threadlink_demo_reset.bat —— 演示库恢复

演示前一键把演示库重建到终态（干净种子 + `bom_selection` / `traceability` / `requirement` 各 1 条 `needs_review`，run id 恒为 6/7/8）。内部调用 `scripts/demo_reset.ps1`，并内置 PowerShell **全路径回退**，兼容 `powershell` 不在 PATH 的环境。

使用：

```cmd
start_threadlink_demo_reset.bat             :: 完整恢复（三类真实调用，需 LLM 可达）
start_threadlink_demo_reset.bat -SkipLive   :: 离线自检（跳过真实 LLM 调用）
```

参数会原样透传给 `scripts/demo_reset.ps1`（脚本实现与断言见 `docs/demo/RUNBOOK.md`）。手工调用（不用启动器）等价于：

```cmd
%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File scripts\demo_reset.ps1
```

### 故障排查（启动器与演示库恢复）

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `'powershell' is not recognized as an internal or external command` | 当前 cmd 会话的 `PATH` 中没有 `powershell` | 用 `start_threadlink_demo_reset.bat`（内置全路径回退），或全路径 `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File scripts\demo_reset.ps1`，或先打开 PowerShell 窗口再 `.\scripts\demo_reset.ps1` |
| 启动器 banner 出现 `'xxx' is not recognized ...` | cmd 对非 ASCII `echo` 文本与代码页组合的解析异常 | 启动器 banner 已改为**纯 ASCII**；中文用途说明见本节与各 `.bat` 顶部注释 |
| 启动器窗口一闪而过 | 执行失败或立即结束 | 用 `start_threadlink_shell.bat` 打开 cmd 后手动运行该 `.bat`，观察 `[OK]` / `[FAIL]` 与退出码 |
| 演示库未回到终态 | `demo_reset.ps1` 中途失败（LLM 不可达 / Git 白名单 / 迁移） | 按窗口内 `==>` 步骤与错误信息排错；仅做离线 bootstrap 时加 `-SkipLive` |

> **`requirement` Agent 无 management command**：其命令行等价入口为
> `.venv\Scripts\python.exe scripts\run_requirement_demo.py`（可加 `--project DEMO-GW --document DOC-001 --username admin`）；
> `scripts/demo_reset.ps1` 第 7 步（requirement → run 8）即调用该脚本。
## 种子数据校验

`scripts/validate_seed.py` 对 `fixtures/demo_seed.json` 做**数据契约校验**（业务编号唯一性、`id == 业务编号字段` 的 R8 自洽、引用闭包、多态端点白名单、`AgentRun.status` 四值规则、`User.role` 职能枚举）。校验不依赖 Django / 数据库 / 第三方库，退出码 `0` 通过、`1` 失败。

### 使用（Windows cmd）

```cmd
cd /d C:\Users\Lenovo\Desktop\Threadlink\threadlink
python scripts\validate_seed.py
```

也可显式指定种子文件：

```cmd
python scripts\validate_seed.py fixtures\demo_seed.json
```

通过时输出形如：

```text
[OK] 种子校验通过：...\fixtures\demo_seed.json
     顶层键 22 个；TraceLink 39 条；引用闭包完整。
```
## 演示仓库准备流程（D4 只读 Git 关联）

GitCommit 使用**本地确定性生成**的演示仓库：SHA 由固定文件内容（LF）/ 作者 / 时间戳复现，并回填 `fixtures/demo_seed.json`；同步命令以仓库为准 upsert、fail-loud、不静默删。

三条命令序列（Windows cmd，项目根目录）：

```cmd
python scripts\make_demo_repo.py            :: 生成 .data/demo-repo（确定性 3 commit，存在则拒绝）
python manage.py load_demo_seed --flush     :: 导入种子（业务编号直写、不触发编号器）
set GIT_READONLY_ROOTS=.data                :: 只读白名单（Windows 分号 ";" 分隔多个，相对 BASE_DIR）
python manage.py sync_git_repo              :: 从仓库 upsert GitCommit（added/updated/missing）
```

自检（确定性）：`python scripts\make_demo_repo.py --check` 须与 fixture 的 3 个 SHA 零差异。

说明：

- `GIT_READONLY_ROOTS` 未配置时 `sync_git_repo` **拒绝执行**（fail-closed）；仓库路径经 `realpath` 前缀校验，防 `../` 逃逸。
- 同步仅使用 `git log` 类**只读**操作，不改动仓库状态。
- `python scripts\make_demo_repo.py --force` 可重建仓库（覆盖 `.data/demo-repo`；Windows 下自动清除只读 `.git` 文件）。
- `sync_git_repo` 遇「DB 有、仓库无」的 GitCommit 会列出明细并以退出码 1 结束（这些行可能被 TraceLink 引用，禁止自动清理）。
## LLM live 测试（D5）

`agents/llm.py` 为 LLM 客户端层；`pytest -q` 默认包含 `live`（真实调用）等分层测试。

配置（`.env`，密钥不入库）：

```dotenv
OPENAI_API_KEY=<本地填写>
OPENAI_MODEL=<带日期快照 id（OpenAI）或 provider 模型名（如 deepseek-chat）>
OPENAI_BASE_URL=<可选，自定义兼容端点，如 https://api.deepseek.com>
LLM_BACKEND=openai          # 断网开发可设 fake（从 tests/fixtures/llm_fake 回放）
LLM_TIMEOUT=30
LLM_MAX_RETRIES=2
LLM_STRUCTURED_MODE=auto    # auto 时 json_schema → json_object 自动降级
LLM_EXTRA_BODY={"thinking": {"type": "disabled"}}   # DeepSeek 推荐：禁用思考档位；OpenAI 原生置空
```

运行：

```cmd
python scripts\llm_preflight.py                    :: 连通预检：model / 延迟 / 用量，断言 content 非空
python scripts\llm_preflight.py --probe-reasoning  :: 三组探测推理档位（基线 / thinking=enabled+low / disabled）
python -m pytest -q                                :: 全套（含 live）
python -m pytest -q -m "not live"                  :: 断网/无 key 逃生（跳过真实调用）
```

要点：

- live 用例会**真实调用模型**并落 `AgentRun`；注意用量与成本（默认 `temperature=0`、`max_tokens` 保守）。
- Pydantic 校验为唯一成功判据；provider 不支持 `json_schema` 时自动降级 `json_object`（记录实际模式）。
- **推理档位**：若 provider 为思考模型（如 DeepSeek `deepseek-flash`），reasoning tokens 计入 `max_tokens`，小配额会耗尽预算致 `content` 为空；用 `--probe-reasoning` 找到「reasoning_tokens 趋零 + content 非空」的配置，写入 `LLM_EXTRA_BODY`（通用注入，无代码特判）。
- **探测结论（2026-10-05，DeepSeek）**：三组 `baseline` / `thinking=enabled+low` / `thinking=disabled` 的 `reasoning_tokens` = 41 / 14 / None，`content` 均非空（`max_tokens=512`）；**定稿推荐 `LLM_EXTRA_BODY={"thinking": {"type": "disabled"}}`**（等价 `{"reasoning_effort": "none"}`）。合法值：`thinking.type ∈ {enabled, disabled}`、`reasoning_effort ∈ {none, low, high, max}`。
- 配置缺失 fail-loud（报错含变量名），不静默跳过、不产生 `AgentRun`。
## 演示流程：邮件 → 需求卡（D5-R2）

Requirement Agent 从来源文档抽取需求卡，经引用核验后进入 `needs_review` 待确认队列（**不写 Requirement、不建 TraceLink**——确认动作留 D5-R3）。

准备与运行（Windows cmd，项目根）：

```cmd
.venv\Scripts\python.exe scripts\make_demo_repo.py         :: 首次：生成确定性 demo 仓库
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py load_demo_seed --flush  :: 导入种子（含 DOC-001 客户邮件）
.venv\Scripts\python.exe manage.py sync_git_repo           :: 需先 set GIT_READONLY_ROOTS=.data
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

操作：

1. 打开 `/admin/core/document/`，勾选 **DOC-001（客户需求邮件）** → 动作「运行 Requirement Agent（生成需求卡）」→ 消息「DOC-001：N 张卡片进入待确认」。
2. 打开 `/admin/agents/agentrun/` 只读队列（过滤 `status=needs_review`），查看 `output_summary`（卡片标题）与详情 `output_json`。
3. 引用核验失败时该 `AgentRun.status=failed`、`invalid_references` 落库，**不进队列**。

命令行等价入口（`requirement` 无 management command）：

```cmd
.venv\Scripts\python.exe scripts\run_requirement_demo.py --project DEMO-GW --document DOC-001 --username admin
```

契约端点（程序化触发；响应 `{agent_run, output}`）：

```cmd
curl -X POST http://127.0.0.1:8000/agents/requirement/run/ ^
  -H "Content-Type: application/json" ^
  -d "{\"project_id\": \"DEMO-GW\", \"document_id\": \"DOC-001\", \"prompt_id\": \"prompt.requirement.extract\", \"prompt_version\": \"v1\"}"
```

断网开发可设 `LLM_BACKEND=fake`，从 `tests/fixtures/llm_fake/` 回放、**不落 AgentRun**。
## 演示流程：确认（approve / reject，D5-R3）

`needs_review` 的 AgentRun 经人工确认后**写实体**（Requirement + RequirementParam + TraceLink）或拒绝。

操作：

1. 打开 `/admin/agents/agentrun/`（过滤 `status=needs_review`）。
2. 勾选待确认行 → 动作「批准（写 Requirement + TraceLink）」→ 消息「已批准 N 条，创建需求 REQ-00x、…」；或「拒绝（不写实体）」→ 状态转 `rejected`。
3. 打开 `/admin/core/requirement/` 可见新建需求（`status=confirmed`、编号器自动 `REQ-###`）；`/admin/traceability/tracelink/` 可见 `requirement → document (derived_from)` 边。

规则（详见 ADR-0010）：

- 仅 `status=needs_review` **且** `reference_check_passed=True` 可处置；其余跳过并提示。
- approve 全程事务：任一步失败整体回滚（保持 `needs_review`）；**不产生新 AgentRun 行**。
- 幂等：对已处置行再次 approve/reject → 报错、不重复写实体。
- 每卡对源 Document 写一条 `derived_from` TraceLink；卡片自带 `code` 不采用（编号器自动生成）。
## 演示流程：选型解释（BOM Selection，D6-R2）

引擎（`core/selection.py`，冻结）**权威**产出候选 / 分数 / 价格 / 交期 / 生命周期 / 排序；LLM 只写解释文案（`rationale` / `summary`）与 `replaces_part_id` 建议。

**management command**：

```cmd
.venv\Scripts\python.exe manage.py run_bom_selection --project DEMO-GW
```

5 项 criteria 可覆盖（`--voltage-min/--voltage-max/--current-min/--temp-min/--temp-max/--ip-min`；`--cost-max` 默认不启用）。输出 run id + 候选摘要（`part_number / score / price / lead`）。

- `--full`：输出**完整** `rationale`（默认截断 80 字符并以 `…` 标注；完整文本始终存于 `AgentRun.output_json`）。
- **criteria 表单（UI 入口，D13）**：浏览器打开 `/agents/bom-selection/form/`，填电压/电流/温度/IP/`cost_max`（可选）→ 提交 → 重定向到新 `AgentRun` 详情（登录必填）。

**契约端点**（响应 `{agent_run, output}`）：

```cmd
curl -X POST http://127.0.0.1:8000/agents/bom-selection/run/ ^
  -H "Content-Type: application/json" ^
  -d "{\"project_id\": \"DEMO-GW\", \"prompt_id\": \"prompt.bom.selection\", \"prompt_version\": \"v1\"}"
```

**队列派发**（`/admin/agents/agentrun/`）：`requirement` 走确认流程（写 Requirement+TraceLink）；`bom_selection` **reject** 生效、**approve** 返回「未实现（D6-R3）」（不写实体）；未知 `agent_name` 跳过。断网开发可 `LLM_BACKEND=fake`（回放、**不落 AgentRun**）。
## 演示流程：追溯链解释（Traceability，D7-R1）

链结构（`root` / `found` / `complete` / `nodes` / `edges` / `missing`）由 **DB 权威**派生（`traceability/chain.py`，冻结）；LLM 只写中文 `summary` 与 `trace_refs` 建议（经核验）。序列号未命中 → **短路**（`found=false`，**不调用 LLM、不产生 AgentRun**，HTTP 200；GT-TRACE-003）。

**management command**：

```cmd
.venv\Scripts\python.exe manage.py run_traceability SN-DEMO-001 --project DEMO-GW
```

未命中时输出「未命中，无 run 产生」；命中时输出 run id + 中文摘要。

**契约端点**（响应 `{agent_run, output}`）：

```cmd
curl -X POST http://127.0.0.1:8000/agents/traceability/run/ ^
  -H "Content-Type: application/json" ^
  -d "{\"project_id\": \"DEMO-GW\", \"serial_number\": \"SN-DEMO-001\", \"query_type\": \"serial\", \"prompt_id\": \"prompt.traceability.chain\", \"prompt_version\": \"v1\"}"
```

**核验**：`trace_refs` 的每个端点经 `agents/verification.verify_references`；失败 → `status=failed` + `invalid_references`（不进人工确认队列）。断网开发可 `LLM_BACKEND=fake`（回放 `tests/fixtures/llm_fake/prompt.traceability.chain.json`、**不落 AgentRun**）。
## 计划计算：BOM 多级展开 + 工单齐套（D11-R1）

**确定性、零 LLM、零 AgentRun、纯只读**（口径见 ADR-0014 与 `docs/golden_tests.md` §2.1–§2.2）。

**BOM 多级展开**：

```cmd
.venv\Scripts\python.exe manage.py bom_expand BOM-001 --hierarchy --qty 1
```

`--hierarchy` 展开全部层级（默认仅顶层）；`--qty N` 指定展开基数。输出层级缩进表 + `totals`（按物料汇总）。

**工单齐套**：

```cmd
.venv\Scripts\python.exe manage.py kitting_check WO-001
```

输出齐套结论 + 缺料表（需求 / 可用 / 缺口 / 在途 / 最晚到货日 / 风险标记）+ 替代可行项。`WorkOrderAdmin` change 页亦含**只读齐套摘要面板**。在途量来源 = `TraceLink(Part -ordered_by-> PO).metadata.quantity`（`PO.status ∈ {open, partial}`）。
## ECN 影响投影 + 正式应用（D11-R2）

**分析（只读、零写）** 与 **应用（唯一写路径，人工动作）** 两阶段；口径与最小决策见 ADR-0015。

**影响投影（只读）**：

```cmd
.venv\Scripts\python.exe manage.py ecn_impact ECN-001
```

读 `ECNImpact`（影响面权威）→ 分类清单（BOM 节点 / 库存批次 / 在途 PO / 测试用例）+ `unresolved`（fail-soft）+ `consistency`（缺 `affects` 边提示）。**零写**（不改 EI / 边 / 正式实体）。`ECNAdmin` change 页含只读「影响投影」面板。

**正式应用（写回 + 确认）**：

```cmd
.venv\Scripts\python.exe manage.py ecn_apply ECN-001
```

前置门：状态 ∈ `{approved, implemented}` 且 `effective_date ≤ 当日`（`approved` + 空日期 → `missing_effective_date`）。事务内：确保 `ECN→目标` `affects` 边（缺 → 建、未确认 → 补确认、已确认 → 不动）+ 写回受影响 `BomItem.part ← 替代料`（`replaces` 目标）。二次应用为 **no-op**（幂等）。亦可经 `ECNAdmin` action「应用 ECN（写回 BomItem.part + 确认 affects 边）」。
## 命令清单

**演示（Agent / 业务动作）**

```cmd
.venv\Scripts\python.exe manage.py run_bom_selection --project DEMO-GW        :: 选型（--full 输出完整 rationale）
.venv\Scripts\python.exe manage.py run_traceability SN-DEMO-001               :: 追溯链解释
.venv\Scripts\python.exe scripts\run_requirement_demo.py --document DOC-001   :: 需求卡（requirement 无 command）
```

- UI 入口：`/agents/bom-selection/form/`（criteria 表单）、`/admin/core/document/`（Document action「运行 Requirement Agent」）、`/admin/agents/agentrun/`（approve / reject）。

**运维 / 计算（确定性、零 LLM）**

```cmd
.venv\Scripts\python.exe manage.py bom_expand BOM-001 --hierarchy             :: BOM 多级展开
.venv\Scripts\python.exe manage.py kitting_check WO-001                       :: 工单齐套
.venv\Scripts\python.exe manage.py ecn_impact ECN-001                         :: ECN 影响投影（只读）
.venv\Scripts\python.exe manage.py ecn_apply ECN-001                          :: ECN 应用（写）
.venv\Scripts\python.exe manage.py sync_git_repo                              :: Git 同步（需 GIT_READONLY_ROOTS）
start_threadlink_demo_reset.bat                                               :: 演示库确定性重建
```

**验证**

```cmd
.venv\Scripts\python.exe scripts\validate_seed.py                            :: 种子契约校验
.venv\Scripts\python.exe scripts\make_demo_repo.py --check                   :: 演示仓库确定性自检
.venv\Scripts\python.exe -m pytest -q -m "not live"                          :: 非 live 全量
.venv\Scripts\python.exe -m pytest -q                                        :: 全量（含 live，真打）
.venv\Scripts\python.exe scripts\demo_terminal_assert.py --expect full       :: 演示库终态断言
```

## 演示

15 分钟分 9 段的完整演示脚本（含各段期望值、决策线、降级预案、禁用清单）见 **`docs/demo/RUNBOOK.md`**；演示前用 `start_threadlink_demo_reset.bat` 重建终态；交付证据见 `docs/qa/2026-10-08-d13-r1-evidence.md`。

## 测试

- 分层（ADR-0008）：**live**（真实调用，默认执行）/ **transport**（HTTP 边界 mock）/ **craft**（构造数据）/ **fake**（`LLM_BACKEND=fake` 离线回放，**不落 AgentRun**）。
- 断网 / 无 key 逃生：`.venv\Scripts\python.exe -m pytest -q -m "not live"`。
- 覆盖：GT **38/38**（`docs/qa/2026-10-07-d12-gt-coverage-matrix.md`）。

## 文档索引

| 类别 | 位置 |
| --- | --- |
| 需求 / 范围 | `docs/PRD.md`、`docs/demonstration_project_requirements.md` |
| 契约 / 数据字典 | `docs/interface_contract.md`、`docs/data_dictionary.md` |
| 数据模型 / ER | `docs/er_diagram.md` |
| 架构图 | `docs/architecture/README.md` |
| 决策记录（ADR） | `docs/adr/0001…0017` |
| 黄金测试 | `docs/golden_tests.md` |
| 收口 / 覆盖矩阵 | `docs/qa/*` |
| 演示 runbook | `docs/demo/RUNBOOK.md` |
| 报告骨架 | `docs/report/REPORT.md` |
| 延后台账 | `docs/DEFERRED.md` |
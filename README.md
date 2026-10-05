# Threadlink

面向中小机电研发团队的单租户轻量研发追溯平台：以 TraceLink 追溯元数据为主线管理需求、BOM、测试、库存、采购与 ECN，只读关联 Git 与文件，并用可审计的 AI 智能体辅助物料选型与全链路追溯。

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

项目提供 `start_threadlink_admin.bat`，双击即可一键启动开发环境。

### 功能

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
## 虚拟环境 Shell

项目提供 `start_threadlink_shell.bat`，双击后打开一个已进入项目虚拟环境的 cmd 窗口。

### 功能

1. **切换目录**：进入项目根目录。
2. **激活虚拟环境**：调用 `.venv\Scripts\activate.bat`。
3. **保持窗口打开**：以 `cmd /k` 启动交互式 shell，提示符前显示 `(.venv)`，可直接执行 `python manage.py ...`；输入 `exit` 关闭窗口。

### 依赖

- 已创建虚拟环境 `.venv`（`python -m venv .venv`）。

### 使用

```cmd
start_threadlink_shell.bat
```

手动等价操作：

```cmd
cd /d C:\Users\Lenovo\Desktop\Threadlink\threadlink
.venv\Scripts\activate.bat
```
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
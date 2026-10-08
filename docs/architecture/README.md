# ThreadLink 架构图（D13-R2）

> 单文件承载四张 Mermaid 图 + 读图说明。系统边界与决策以 `docs/adr/`（0001–0017）与
> `docs/interface_contract.md` 为权威；完整数据模型见 `docs/er_diagram.md`。
>
> **语法自检**：节点文本一律用 `"..."` 包裹，内部只用全角括号、不含双引号 / 分号；
> `erDiagram` 关系名规范、注释行以 `%%` 开头且不与语法同行。**GitHub 端渲染确认列为 R3 前置动作。**

---

## 1. 系统总览

```mermaid
flowchart LR
    subgraph roles["角色"]
        eng["工程 engineer"]
        proc["采购 procurement"]
        test["测试 test"]
        quality["质量 quality"]
        boss["管理 admin"]
    end

    subgraph access["接入层"]
        admin_site["Django Admin + HTMX"]
        api["HTTP 端点 /agents/*/run/"]
    end

    subgraph service["服务层"]
        planning["planning：BOM 多级展开 + 工单齐套（确定性 / 零 LLM）"]
        selection["selection：选型引擎（冻结）"]
        ecn["ecn：影响投影 + 应用"]
        pipeline["agents 管道：requirement / bom_selection / traceability"]
        confirm["confirmation：approve / reject"]
        chain["traceability.chain：链结构（DB 权威）"]
    end

    subgraph data["数据层"]
        sqlite["SQLite（开发）"]
        pg["PostgreSQL（目标）"]
        meta["TraceLink / AgentRun 审计"]
    end

    subgraph external["外部"]
        llm["LLM API（OpenAI 兼容）"]
        git["Git 仓库（只读）"]
        files["文件（只读）"]
    end

    roles --> admin_site
    admin_site --> planning
    admin_site --> pipeline
    admin_site --> confirm
    admin_site --> ecn
    api --> pipeline
    pipeline --> selection
    pipeline --> chain
    pipeline --> llm
    confirm --> meta
    planning --> sqlite
    selection --> sqlite
    ecn --> sqlite
    pipeline --> sqlite
    chain --> meta
    admin_site --> git
    admin_site --> files
    sqlite -.->|生产部署| pg
```

**读图**：角色（五职能）只经 **Admin + HTMX** 或受限 HTTP 端点进入，权限仅落在 Admin 写路径（ADR-0016）。
服务层分三类：**确定性计算**（planning 展开/齐套、selection 引擎，零 LLM）、**写路径**（ecn 应用、confirmation）、
**LLM 管道**（agents）。跨域追溯统一落 `TraceLink`，LLM 调用统一落 `AgentRun`（审计）。数据层开发用 SQLite、
目标为 PostgreSQL；外部 LLM API 可换端点（ADR-0008），Git 与文件严格只读。

---

## 2. 追溯视角（TraceLink 中心）

```mermaid
erDiagram
    PROJECT ||--o{ TRACELINK : scopes
    TRACELINK }o--o{ ENDPOINT : "from / to"

    PROJECT {
        string code
    }
    TRACELINK {
        string from_type
        string from_id
        string to_type
        string to_id
        string relation_type
    }
    ENDPOINT {
        string entity_type
        string business_no
    }
%% 13 端点抽象（EntityType 白名单）：
%% requirement, part, supplier, bom, bom_item, inventory_lot, work_order,
%% purchase_order, test_case, test_run, ecn, document, git_commit
```

**读图**：`TraceLink` 为**多态边**（`from_*` / `to_*` 存**业务编号**而非主键），任何跨域关系统一走它——
这是全系统唯一追溯入口。两端 `ENTITY` 抽象为 **13 类白名单**（`EntityType`）：强结构关系（层级/包含/归属）
仍用 FK，不进 TraceLink。`User` / `Project` 仅经 FK、`AgentRun` / `TraceLink` 为审计记录、明细表无业务编号，
均不作端点。**完整 ER（FK 强关系）见 `docs/er_diagram.md`**。

---

## 3. Agent 管道

```mermaid
flowchart TD
    input["输入：Document / 序列号 / 项目 criteria"] --> load["prompt 装载：system + user_template + schema"]
    load --> call["call_json：provider 结构化输出"]
    call --> pyd["Pydantic 校验：冻结 schema"]
    pyd --> verify["引用核验：verify_references"]
    verify -->|通过| nr["AgentRun = needs_review"]
    verify -->|失败| failed["AgentRun = failed + invalid_references"]
    nr --> decide["人工处置：AgentRunAdmin"]
    decide -->|approve| write["写实体 + TraceLink / 或纯审计确认"]
    decide -->|reject| rejected["AgentRun = rejected + human-rejected 落档"]
    failed --> archive["失败样例落档（防幻觉，保持可审计）"]

    subgraph short["未命中短路分支（GT-TRACE-003）"]
        miss["序列号未命中：found=false"]
        miss --> nollm["零 LLM 调用 / 不建 AgentRun / 不记 failed"]
    end
```

**读图**：三 Agent 共用一条管道——**输入 → prompt 装载 → 结构化调用 → Pydantic 校验 → 引用核验 → 落 `AgentRun`**。
核验通过进 `needs_review` 等待人工；失败当场转 `failed` 并落档。`output_json` 一律存**合并后的冻结输出模型**
（D6 教训），可再反序列化。**未命中短路**为独立分支：只返回 `found=false` 链负载，**零 LLM、不建 `AgentRun`、不记 `failed`**。
人工处置：`requirement`/`bom_selection` **approve 写实体 + TraceLink**，`traceability` 为**纯审计确认**（零实体写入，ADR-0013）。

---

## 4. AgentRun 状态机

```mermaid
stateDiagram-v2
    [*] --> failed : LLM / 校验 / 核验失败
    [*] --> needs_review : 核验通过，等待人工
    needs_review --> success : approve
    needs_review --> rejected : reject
    failed --> [*]
    success --> [*]
    rejected --> [*]

    note right of failed
        confirmed_by / confirmed_at = NULL
    end note
    note right of needs_review
        confirmed_by / confirmed_at = NULL
        output_schema_valid = True
        reference_check_passed = True
    end note
    note right of success
        confirmed_by / confirmed_at 必填
        output_schema_valid = True
        reference_check_passed = True
    end note
    note right of rejected
        confirmed_by / confirmed_at 必填
    end note
```

**读图**：`AgentRun` 固定**四值**。机器侧产生 `failed` / `needs_review`，二者的 `confirmed_by` / `confirmed_at`
**必须为 NULL**；人工处置产生 `success` / `rejected`，二者**必填**确认人/时间，且为**终态**（不可再处置）。
`success` 额外要求 `output_schema_valid=True` 且 `reference_check_passed=True`。该四值与绑定规则是审计不变量
（`tests/test_audit_r3.py`），approve/reject 全程事务、幂等（ADR-0010）。
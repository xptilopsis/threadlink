# ADR-0011：BOM 选型引擎（D6-R1）

| 项 | 内容 |
| --- | --- |
| 状态 | 已接受（Accepted） |
| 日期 | 2026-10-05 |
| 里程碑 | D6-R1（确定性选型引擎 + 冻结基线 golden tests） |
| 关联 | `rules/bom_scoring.v1.json`（frozen v1） · `docs/golden_tests.md` GT-BOM-008/009 · `core/selection.py` · `tests/test_selection_r1.py` · `docs/adr/0005-bom-scoring-v1-frozen.md` · `.gitattributes` |

## 背景

`rules/bom_scoring.v1.json` 已于 D1 冻结（两阶段模型、权重、归一化方向、过滤顺序、lifecycle 映射）；D6-R1 首次以**确定性代码**实现该规则（零 LLM、零 DB 写、零 AgentRun），并用 GT-BOM-008/009 锁定排序口径与演示基线。

## 决策

### 1. 引擎接口（`core/selection.py`）

- `select(project, criteria=None, top=3) -> SelectionResult`；
- `SelectionResult.passed`：排序后 Top-N `PassedCandidate`（`total_score` / 三因子归一值 `cost_norm·lead_time_norm·multi_source_norm` / 有效源明细 `min_price·min_lead·source_count` / `warnings`）；
- `SelectionResult.excluded`：逐条 `Excluded{part_number, reason, details}`；
- `Criteria`（`voltage_min/max=9/36`、`current_min=5`、`temp_min/max=-40/85`、`ip_min=65`、`cost_max=None`）；
- `as_dict()` 提供可 JSON 化结构（Decimal→str）供逐字节比较；
- **纯读**；v1 候选池 = 项目内全部 `Part`（类别限定登记 v2）。

### 2. 参数映射表（criteria → fixture 形态）

| criteria | PartParam 形态 | 判定 |
| --- | --- | --- |
| `input_voltage` | `value_min=9` / `value_max=36` | `value_min <= 9 且 value_max >= 36` |
| `rated_current` | `value_num` | `>= 5` |
| `operating_temp` | `value_min=-40` / `value_max=85` | `value_min <= -40 且 value_max >= 85` |
| `ip_rating` | `value_text`（如 `"IP65"`） | 解析 `IP(\d+)` → `>= 65` |
| `unit_cost`（`cost_max` 可选） | `value_text`（字符串数字） | `<= cost_max`（默认不启用） |

**有效供货渠道** = `SupplierPart.lifecycle_status != "eol"`；`nrnd` 保留为有效渠道 + `warnings`（`nrnd_source:<id>`）、不降权（v1 行为，业务影响留 D6 评估）。

### 3. reason token 全集（固化为代码常量）

`lifecycle:obsolete` / `lifecycle:discontinued` / `missing_param` / `voltage_out_of_range` / `current_below_min` / `temp_out_of_range` / `ip_below_min` / `cost_exceeded`
（= `rules` 的 `exclude_reasons` 全集；`lifecycle:discontinued` 为其他输入预留。**`missing_param` 为裸 token**，缺失参数名记入 `details.missing`，不并入 token——与 GT-BOM-009 逐条一致。）

**过滤顺序（固定）**：`lifecycle → param_completeness → param_threshold → cost_max`（受约束：obsolete/discontinued 的 reason 不被 `missing_param` 淹没）。

### 4. 取整口径

`rules` **无明文取整规则**；采用 **`Decimal` 全程 + `ROUND_HALF_UP` 输出 2 位小数**。以 GT-BOM-009 反证成立：`PART-002=94.79` / `PART-001=87.24` / `PART-018=0.00`（`100×(0.5·cost_norm+0.3·lead_norm+0.2·ms_norm)`）。归一化 `max == min` 时该维度计 `1.0`（rules `normalization.degenerate`）。

### 5. 候选池口径

v1 = **项目内全部 `Part`**（无类别/状态预筛，lifecycle 在阶段 1 处理）；**类别限定候选池登记 v2**；`cost_max` 默认 `None`（演示不启用——AC-004 的 800 元为整机 BOM 成本，非单料单价上限）。

### 6. 与 golden tests 的对应

- **GT-BOM-008**（构造集 C1/C2/C3，独立 Project 隔离）：`80.00 / 50.00 / 10.00`、排序 `C1>C2>C3`；`C1` 三因子 `(1.00, 1.00, 0.00)`。
- **GT-BOM-009**（演示 fixture 全表）：通过 3 = `PART-002 94.79` / `PART-001 87.24` / `PART-018 0.00`；排除 17 = `missing_param` 14（PART-003/004/005/006/007/008/009/010/013/014/015/016/019/020）+ `PART-011 current_below_min` + `PART-012 temp_out_of_range` + `PART-017 lifecycle:obsolete`；`PART-001` 有效源 2（`SP-003` eol 剔除）、`PART-002` 有效源 3。

### 7. 确定性

`nodes` 按 `part_number` 遍历；排序键 `(-total_score, min_price, part_number)`；`as_dict()` 两次调用 JSON 逐字节一致（测试 `test_deterministic`）。

### 8. 冻结基准口径（D6 步骤 0 关联）

新增 `.gitattributes`（`* text=auto` + `*.md/*.py/... text eol=lf` + `*.ps1/*.bat text eol=crlf` + 二进制 `binary`），**冻结/核验基准统一为仓库 blob（`git cat-file`）/规范化口径**；工作树字节仅在 `.gitattributes` 生效后的**新克隆**中才可作为稳定基准（此前 D5 prompts v1 的 CRLF 工作树值已按此修正为 blob 口径）。`git add --renormalize .` 后无已跟踪文件被修改，证明现有 blob 已是 LF。

## 后果

- 正向：选型口径可执行、可回归（GT 锁定）；引擎纯确定性便于复检；reason token 全集 + 过滤顺序保证演示可读性。
- 成本：v1 无类别限定（大池性能留 v2）；`nrnd` 降权未启用（业务影响留 D6 评估）。
- 留痕：接口、映射表、token 全集、取整口径、候选池口径、GT 对应与确定性均固化于本 ADR。
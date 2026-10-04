# ADR-0005：BOM 选型评分口径 v1 冻结（两阶段模型 + OI-6 处置）

| 项 | 内容 |
| --- | --- |
| 状态 | 已接受（Accepted） |
| 日期 | 2026-10-04 |
| 里程碑 | D1（范围冻结） |
| 关联 | `rules/bom_scoring.v1.json` · `fixtures/demo_seed.json` · `docs/golden_tests.md` §3/§5.1（GT-BOM-008/009）/§6（OI-6） · `docs/PRD.md#AC-004` · ADR-0004 |

## 背景

D1 需冻结「BOM / 选型评分」口径以承载 PRD **AC-004** 与 golden test **GT-BOM-008**。批次 3 首次以全表演算演示 fixture 时，阶段 1 硬过滤通过者为 **0**，AC-004「候选 ≥ 3」不可满足——即开放问题 **OI-6**（见 `docs/golden_tests.md` §6）。

根因：原 fixture 的 20 个 `Part` 中，`PART-001`/`PART-002` 仅缺 `ip_rating`，其余料普遍缺关键参数；同时 `Part.lifecycle_status` 只有 `active`/`obsolete`（无 `discontinued` 字面值），`SupplierPart.lifecycle_status` 另有 `nrnd`/`eol`。这与「不得改数据凑规则」的初判冲突。

本 ADR 记录经人工裁决后的评分口径冻结，以及 **OI-6 的处置**。

## 决策

### 1. 两阶段模型

评分分两阶段，**硬过滤（合规门槛，非排序）** 与 **加权评分（排序）** 严格分离：

- 阶段 1：逐项判定，任一不满足即排除；参数缺失视为不满足。
- 阶段 2：仅对通过阶段 1 者评分，各维度 min-max 归一化到 `[0,1]` 后加权。

**修正记录**：voltage / current / temp / ip 由初版的「评分维度」改判为「硬过滤门槛」，不参与排序（见 ADR-0004 决策 ③）。

### 2. 硬过滤顺序（保证排除原因可读）

`filter_order = lifecycle → param_completeness → param_threshold → cost_max`

1. **lifecycle**：`Part.lifecycle_status ∈ {obsolete, discontinued}` → 排除，`reason = lifecycle:obsolete` / `lifecycle:discontinued`；若存在 `replaces` 关系，输出 `replaces_part_id` 与替代理由。
2. **param_completeness**：四个关键参数 `input_voltage` / `rated_current` / `operating_temp` / `ip_rating` 任一缺失 → 排除，`reason = missing_param`（先判完整性再判阈值，避免原因混淆）。
3. **param_threshold**：电压 `9-36V`、电流 `≥5A`、温度 `-40~85°C`、`IP ≥ IP65`；各自 `reason` 为 `voltage_out_of_range` / `current_below_min` / `temp_out_of_range` / `ip_below_min`。
4. **cost_max**（可选）：调用方提供单价上限时启用，超出 `reason = cost_exceeded`；演示不启用（AC-004 的 800 元为整机 BOM 成本约束，非单料单价上限）。

### 3. lifecycle 映射

| 层级 | 字段 | 取值 | 处置 |
| --- | --- | --- | --- |
| 物料级 | `Part.lifecycle_status` | `obsolete` / `discontinued` | **排除**（`lifecycle:<value>`） |
| 物料级 | `Part.lifecycle_status` | 其它（`active` 等） | 保留 |
| 渠道级 | `SupplierPart.lifecycle_status` | `eol` | **排除该供货渠道**（非排除物料），不计入 `min(unit_price)` / `min(lead_time)` / `multi_source` |
| 渠道级 | `SupplierPart.lifecycle_status` | `nrnd` | 保留渠道并计入 `warning`；**v1 不做降权**，留 D6 评估 |

物料级与渠道级互不替代。演示中的「停产」由 `PART-017`（`obsolete`）承载。

### 4. 权重与归一化方向

| 维度 | 权重 | 方向 | 取值口径 |
| --- | --- | --- | --- |
| `cost` | 0.5 | `lower_better` | `min(unit_price)` over 有效渠道 |
| `lead_time` | 0.3 | `lower_better` | `min(lead_time_days)` over 有效渠道 |
| `multi_source` | 0.2 | `higher_better` | `count(有效渠道)` |

- 归一化：min-max 到 `[0,1]`；`max == min` 时该维度计 `1.0`。
- 方向：`lower_better` 用 `(max-x)/(max-min)`；`higher_better` 用镜像 `(x-min)/(max-min)`。
- 总分：`100 × (0.5·cost_norm + 0.3·lead_time_norm + 0.2·multi_source_norm)`。

### 5. tie-break

总分相同 → 先按 `cost` 升序，再按 `part_number` 升序。

### 6. OI-6 处置：补齐 fixture 关键参数（人工放行修数据）

**裁决**：采纳选项 (a) —— 补齐演示 fixture 的关键参数。理由：原 fixture 无一组完整参数，AC-004 客观不可满足，属 **fixture 质量问题**而非规则缺陷；人工放行修数据是正规流程，非「改数据凑规则」（后者指边跑边调数据让结果好看）。

补齐明细：

| 物料 | 补入字段 | 结果 |
| --- | --- | --- |
| `PART-001` | `ip_rating = IP65` | 通过 |
| `PART-002` | `ip_rating = IP65` | 通过 |
| `PART-018` | `input_voltage 9-36V` / `rated_current 5A` / `operating_temp -40~85°C` / `ip_rating IP65` / `unit_cost 88.00` | 通过（高成本、长交期） |
| `PART-011` | `input_voltage` / `operating_temp` / `ip_rating` / `unit_cost`（`rated_current` 已有 `3A`） | 阈值排除（`current_below_min`） |
| `PART-012` | `input_voltage` / `rated_current` / `operating_temp -20~70°C` / `ip_rating` / `unit_cost` | 阈值排除（`temp_out_of_range`） |
| `PART-017` | **不补**（`obsolete` 保留） | lifecycle 排除载体 |

新增渠道（使多源有区分度、保证低交期/高成本覆盖）：`SP-011`（`SUP-002`→`PART-001`）、`SP-012`（`SUP-001`→`PART-002`）、`SP-013`（`SUP-003`→`PART-002`）。

### 7. 首次演算基线（冻结值）

候选池 20 → 阶段 1 通过 **3**，排除 **17**（三类原因齐全）：

| 通过者 | 有效渠道 min 单价 | min 交期 | 有效源数 | 总分 |
| --- | --- | --- | --- | --- |
| `PART-002` | 45.00 | 14 | 3 | **94.79**（Top1） |
| `PART-001` | 40.00 | 21 | 2 | **87.24**（Top2） |
| `PART-018` | 88.00 | 90 | 1 | **0.00**（Top3） |

- 排除分类：`lifecycle:obsolete`（`PART-017`）、`missing_param`（14 个）、`current_below_min`（`PART-011`）、`temp_out_of_range`（`PART-012`）。
- 渠道级：`SP-003`（`eol`）计算 `PART-001` 时排除；`SP-007`（`nrnd`）保留 + `warning`。
- 权重/公式核对：构造集 `C1/C2/C3` 的 `80/50/10` 与冻结公式一致（GT-BOM-008）。
- 基线由 `GT-BOM-009` 锁定。

**规则文件状态**：`rules/bom_scoring.v1.json` 由 `proposed` → **`frozen`**（`frozen_at = 2026-10-04`）。

## 后果

- 正向：AC-004 可满足；评分口径（模型/顺序/映射/权重/归一化/tie-break）全部冻结，GT-BOM-008/009 可锁定排序与基线。
- 负向 / 成本：`nrnd` 降权延后至 D6；fixture 后续若再改物料参数，必须重跑 GT-BOM-009 基线并同步更新，不得边跑边调数据。
# ADR-0014：BOM 多级展开 + 工单齐套（D11-R1）

| 项 | 内容 |
| --- | --- |
| 状态 | 已接受（Accepted） |
| 日期 | 2026-10-07 |
| 里程碑 | D11-R1（BOM 多级展开 + 工单齐套；确定性、零 LLM、零 AgentRun、零写路径） |
| 关联 | `docs/golden_tests.md` §2.1/§2.2 + GT-BOM-001…007 + GT-KIT-001…008 · `core/bom_expand.py` · `core/kitting.py` · `core/management/commands/{bom_expand,kitting_check}.py` · `core/admin.py::WorkOrderAdmin` |

## 背景

D11 引入**计划层只读计算**：BOM 多级展开（父子树 → 累计需求）与工单齐套（需求 vs 库存/在途/替代）。
本轮**确定性计算、零 LLM、零 AgentRun、纯只读**（GT 为唯一依据）。

## GT → 实现点映射表（§0.1）

| GT | 输入 | 期望 | 实现点 |
| --- | --- | --- | --- |
| GT-BOM-001 | `expand_bom(BOM-001, qty=1)` | 顶层 4 行、`depth==0`、BI-004=2 | `expand_bom` 默认 `include_hierarchy=False` |
| GT-BOM-002 | `include_hierarchy=true` | BI-005(d1, parent BI-001, ×4)、叶子无子 | 递归展开 + `depth` 递增 |
| GT-BOM-003 | `expand_bom_for_work_order(WO-001)` | PART-006=20 / PART-010=120 / PART-001=10 | `expand_bom_for_work_order`（全层级 × `WO.quantity`） |
| GT-BOM-004 | 多路径同 part | 汇总 = 3+5 = 8、明细保留两行 | `totals` 按 part 求和 |
| GT-BOM-005 | `BOM.status=obsolete` / `draft` | 抛 `bom_not_releasable` / `draft_bom` warning | `_check_status` |
| GT-BOM-006 | 含 `PART-017`(obsolete) | 行 `risk_flags` 含 `discontinued` | `_risk_flags` |
| GT-BOM-007 | BI-001→BI-006→BI-016 | BI-016 `depth=2`、累计 `1×10×2=20` | 路径连乘 |
| GT-KIT-001 | 需求=可用 | `shortages==[]`、`ready==true` | `analyze_kitting` |
| GT-KIT-002 | `qty_available=80` vs 需求 90 | `available_qty=80`、`shortage_qty=10` | `_available_qty`（仅 `status=available`） |
| GT-KIT-003 | 在途 PO-A/PO-B | `latest_arrival_date=2026-03-20`、`in_transit_qty=70` | `_latest_arrival`（按 `expected_date` 升序累加） |
| GT-KIT-004 | `PART-002 replaces PART-001` | `alternatives` 含替代料 + `shortest_arrival_date` | `_alternatives` |
| GT-KIT-005 | `PART-017` 缺料 | `risk_flags` 含 `discontinued` | `_risk_flags`（缺料行） |
| GT-KIT-006 | `PART-018` lead=90 | `risk_flags` 含 `long_lead_time` | `_has_long_lead`（> 60） |
| GT-KIT-007 | `PART-001`(critical) 缺料 | 全字段 + `critical_shortage` | `Part.is_critical` |
| GT-KIT-008 | 无在途/无替代 | `latest_arrival_date=null`、`insufficient=true` | `_latest_arrival` |

§0 核对结论：**GT 文本与模型/数据来源可调和，无阻塞**（GT-BOM-008/009 属选型、D6-R1 已实现，本轮跳过）。

## 齐套数据来源表（§0.3，fixtures 实例验证）

| 量 | 来源 | 机制 | 过滤 / 方向 |
| --- | --- | --- | --- |
| **需求** | `WorkOrder.bom` → BomItem 树展开 × `WorkOrder.quantity` | **字段级** | §2.1 |
| **可用（库存）** | `InventoryLot.qty_available` | **字段级**（`InventoryLot.part` FK） | `status = "available"`（`allocated`/`consumed`/`scrapped` 不计） |
| **在途** | `TraceLink(from=Part, relation_type="ordered_by", to=PurchaseOrder).metadata["quantity"]` | **TraceLink 级** | `PO.status ∈ {open, partial}`；方向 Part → PO |
| **替代** | `TraceLink(from=替代料 Part, relation_type="replaces", to=被替代料 Part)` | **TraceLink 级** | 替代料 `lifecycle_status == "active"`；方向 替代料 → 被替代料 |
| **风险** | `Part.lifecycle_status` / `SupplierPart.lead_time_days` / `Part.is_critical` | **字段级** | — |

- **关键**：`PurchaseOrder` 模型**无明细行、无 `metadata` 字段**——在途量以 `TraceLink.metadata["quantity"]` 承载（fixtures 验证：`PART-001→PO-001` qty 100/open 等）。
- **WorkOrder ↔ InventoryLot 无直接关联**：齐套按 **part 层**比较（需求汇总 vs 可用汇总），不做序列级分配。

## 最小决策（§0.5，GT 未覆盖处，采用与既有口径一致的最小决策）

1. **`expand_bom(bom, quantity=1, include_hierarchy=False)`**：默认仅**顶层行**（GT-BOM-001 `len==4`）；`include_hierarchy=True` 返回**全层级**（GT-BOM-002/007）。
2. **`expand_bom_for_work_order(work_order)`** = 全层级 × `WorkOrder.quantity`（GT-BOM-003）。
3. **lines 顺序** = 全局 `depth` 升序；同层按 `position`、`ref_des`、`item_no` 稳定排序（§2.1 字面口径；满足指令「父先子后」——父 `depth` 更小故在先）。
4. **异常模型**：`BomExpandError.code ∈ {bom_not_releasable, cyclic_bom_structure, orphan_bom_item}`（GT 机器 token）。
5. **孤儿检查为防御性**：`BomItem.part` 为 `FK(PROTECT)`，正常数据下不可达；保留检查以满足 GT 语义。
6. **函数命名**：实现为 `analyze_kitting`（GT §5.2 名），并导出 `check_kitting` 别名（指令 §2.1 名）；二者同一实现。
7. **`discontinued` 集合** = `Part.lifecycle_status ∈ {eol, obsolete, discontinued}`（§2.2 列 `eol/obsolete`，GT-BOM-008 边界含字面 `discontinued`）。
8. **`long_lead_time`** = 该 part 任一 `SupplierPart.lead_time_days > 60`（GT-KIT-006；阈值严格 `> 60`）。
9. **`critical_shortage`** 取 `Part.is_critical`（GT-KIT-007「物料 `is_critical`」；非 `BomItem.is_critical`）。
10. **在途批次 `expected_date` 为 `None`** 的排在最后（GT 未定义；最小确定性决策）。
11. **无在途且缺料 → `insufficient=true`**（GT-KIT-008）；`shortage<=0` 不在 `shortages` 中。
12. **输出数值**：`Decimal` 全程计算，`quantize(0.0001)`（4 位小数），无浮点漂移（GT-BOM-003 边界）。
13. **只读**：零写、零 AgentRun、零 LLM；查询仅 `SELECT`。

## 命令

```cmd
.venv\Scripts\python.exe manage.py bom_expand BOM-001 --hierarchy --qty 1
.venv\Scripts\python.exe manage.py kitting_check WO-001
```

## 确定性

- 两次调用输出**逐字节一致**（`json.dumps(sort_keys=True)` 比较，测试固化）。
- 排序键完全确定（`depth` + `position` + `ref_des` + `item_no`；在途按 `expected_date` + `None` 置后）。

## 后果

- 计划层计算与 LLM 完全解耦（本 ADR 覆盖 R1；R2 = ECN 影响投影 + 正式应用）。
- `WorkOrderAdmin` change 页含**只读齐套摘要面板**（异常捕获显示「计算失败：<原因>」，不 500）。
- 未覆盖处均已按最小决策固化（上列 13 条），后续如需变更走新裁决。
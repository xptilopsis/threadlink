# ADR-0003：User.role 由「权限档位」改为「职能枚举」（D3 决策修正）

| 项 | 内容 |
| --- | --- |
| 状态 | 已接受（Accepted） |
| 日期 | 2026-10-04 |
| 里程碑 | D1（范围冻结） |
| 关联 | D3 四项开放决策 · 批次任务 T2.4 修正版 · `docs/data_dictionary.md` §1 · `docs/PRD.md` §3 |

## 背景

D3 四项开放决策初版将 `User.role` 定为**权限档位**三值 `admin` / `engineer` / `viewer`，语义是「账号的操作档位」。但：

- `viewer` **没有任何写权限语义**，与平台「建议须经人工确认后写入正式实体」（R6）的岗位分工对不上；
- PRD §3 已按**岗位职能**列举使用者（研发、硬件/结构、采购/供应链、测试、质量/项目经理、系统管理员），与档位三值无法一一映射；
- 种子数据 `fixtures/demo_seed.json` 实际使用 `admin` / `engineer` / `procurement` / `test` / `quality`，与档位三值冲突。

## 决策

`User.role` **冻结为职能枚举**（`varchar(16)`）：

`admin` / `engineer` / `procurement` / `test` / `quality`

- **以 PRD §3 为权威，与 fixtures 取并集**：PRD §3 的 6 类人类角色全部落入上述 5 值——`admin`=系统管理员；`engineer`=研发工程师 · 硬件/结构工程师；`procurement`=采购/供应链；`test`=测试工程师；`quality`=质量/项目经理。「系统（AI 智能体）」不是 User，不占 `role`。**PRD 无独有角色缺失**。
- **取代**上一版「权限档位」三值 `admin` / `engineer` / `viewer`；`viewer` 作废。
- **与 Django 内置的关系**：`role=admin` 落地时置 `is_superuser=True`、`is_staff=True`；其余 `is_staff=False`。`is_superuser`/`is_staff` 不参与业务判权。
- **role → 可写实体集映射**：以 PRD §3「主要使用功能」为骨架，D11 实现（框架见 `docs/data_dictionary.md` §1）；D1 只冻结框架，不实现判定逻辑。
- `scripts/validate_seed.py` 断言每个 `user.role` ∈ 冻结枚举。

## 后果

- 正向：角色即业务职能，D11 权限映射可直接落到实体集；与 PRD §3、种子数据一致；满足 R6 的人工确认分工。
- 负向 / 成本：需要在 D11 维护 `role → 可写实体集` 映射表；无法表达「同一人兼任多角色」——按**单角色**处理，如需兼任在 D2 及以后评估是否扩展为多角色。
- 与 `AUTH_USER_MODEL` 前置动作（删 `db.sqlite3`、重建迁移、重跑 `createsuperuser`）无冲突，仍按 D2 落地执行。
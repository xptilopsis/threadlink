# R2 历史改写与 force-push 事件记录（2026-10-05）

## 事件
D3-R2 期间（本会话复核对账时）发现仓库处于**矛盾状态**：

- HEAD = `191d5c5`（已完整包含 R2：Step 0 = `b253b1f`、主体 = `191d5c5`）；
- 但工作区被**静默、精确回退**到 R1 基线 `5b04393`：`git diff 5b04393 --stat` 为空；5 处未暂存改动净删除 R2 全部内容（删 `tests/test_admin_r2.py`、`tests/test_seed_users.py`，回退 `core/admin.py` / `core/management/commands/load_demo_seed.py` / `tests/test_admin_r1.py`）。

## 决策出处（如实记录，不美化）
- 该矛盾状态由**并行会话 / 本机操作**产生，非本会话显式执行；本会话仅观察到矛盾。
- 本会话按纪律**停下汇报、交用户人工裁决**；用户裁决 = **重做 R2**：`git reset --hard 5b04393`，丢弃 `b253b1f`、`191d5c5` 与工作区回退改动，由本会话从 Step 0 重新实现。
- 本会话 R3 阶段回溯确认：重做前已核对 `docs/adr/0003` L26 与 `docs/data_dictionary.md` §1 L83 原文一致（无出入）；旧 R2 与本会话重做的 R2 为**同一 spec 的两份实现**，据此追认等价（同 spec、21 tests passed）。

## 旧提交 metadata（本地 object 仍可读）
- `b253b1f`（`Mon Oct 5 09:03:14 2026 +0800`）`fix(d3-r2-0): seed loader honors ADR-0003 role<->flags mapping + r1 test cleanup [ref: ADR-0003]`
  - `core/management/commands/load_demo_seed.py` | 16 ++++++++++++++--
  - `tests/test_admin_r1.py` | 11 ++++-------
  - `tests/test_seed_users.py` | 30 ++++++++++++++++++++++++++++++
  - 3 files changed, 48 insertions(+), 9 deletions(-)
- `191d5c5` `feat(d3-r2): bom tree view + bomitem/inventorylot admin + smoke tests`
  - `core/admin.py` | 93 +++++++++++++++++++++++++++++++
  - `tests/test_admin_r2.py` | 146 +++++++++++++++++++++++++++++++++++++++++++++++
  - 2 files changed, 239 insertions(+)

## 新历史与等效声明
`5b04393`(R1) → `2d2db35`(Step 0) → `4e2efc0`(R2 主体)

- `2d2db35`：`load_demo_seed` role↔flags 映射修正 + `tests/test_admin_r1.py` 清理 + 新增 `tests/test_seed_users.py`，等效旧 `b253b1f`；Step 0 后 **15 passed**。
- `4e2efc0`：`BomAdmin` 只读树视图 + `BomItemAdmin` + `InventoryLotAdmin` + `tests/test_admin_r2.py`，等效旧 `191d5c5`；收口 **21 passed**。
- **等效声明**：新旧 R2 为同一 spec 的两份实现；重做版最终 `pytest -q` 21 passed、`manage.py check` 无问题、`makemigrations --check --dry-run` = No changes、`scripts/validate_seed.py` = OK。

## force push 记录
- 因 `reset` 改写了已推送历史，普通 push 会被拒（non-fast-forward），须 force push。
- 用户于本机执行 force push，报告：**`4e2efc0` 已推送成功**。
- 本会话沙箱 `git ls-remote origin refs/heads/main` 返回 `Network is unreachable`（沙箱访问 `ssh.github.com:443` 受限），**无法在会话内逐字回填远端 hash**；以用户报告为准，逐字 `ls-remote` 输出待补充。

## 结论
- **无内容损失**：旧 R2 两提交的能力在 `2d2db35` / `4e2efc0` 中完整等价重现。
- 远端与本地一致（据用户报告）；旧对象 `191d5c5` / `b253b1f` 仍可经 `reflog` 取回，但已不在主线。
- 后续以 **`4e2efc0`** 为 R2 收口 HEAD；**勿再引用 `191d5c5`**。
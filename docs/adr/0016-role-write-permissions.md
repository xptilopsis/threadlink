# ADR-0016：role → 可写实体集（Admin 轻量写权限，D11-R3）

| 项 | 内容 |
| --- | --- |
| 状态 | 已接受（Accepted） |
| 日期 | 2026-10-07 |
| 里程碑 | D11-R3（权限映射 + 审计面 + 异常处理 + E2E 收口） |
| 关联 | `docs/data_dictionary.md` §1（L83–84）· `core/admin.py::RoleWritePermissionMixin` · `traceability/admin.py` · `tests/test_permissions_r3.py` |

## 背景

`docs/data_dictionary.md` §1（L84）冻结「**role → 可写实体集（映射框架，D11 实现）**」，D1 仅冻结框架、不实现判定逻辑。R3 将其落地为 **Admin 写路径**的轻量权限。

## 原文引述（data_dictionary §1 L83–84）

> - **与 Django 内置的关系**：`role=admin` ⟺ 系统管理员，落地时置 `is_superuser=True`、`is_staff=True`；其余四个角色 `is_staff=False`（无 Django Admin 后台权限，写权限由应用层按下方映射判定）。`is_superuser`/`is_staff` 不参与业务判权。
> - **role → 可写实体集（映射框架，D11 实现）**：以 PRD §3「主要使用功能」为骨架，D11 落为权限映射——`admin`=全部；`engineer`=`Requirement` / `RequirementParam` / `Part` / `PartParam` / `Bom` / `BomItem`；`procurement`=`Supplier` / `SupplierPart` / `PurchaseOrder` / `InventoryLot` / `WorkOrder`（齐套）；`test`=`TestCase` / `TestRun`；`quality`=`ECN` / `ECNImpact` / `TraceLink` / `AgentRun`（审计）。**D1 仅冻结框架，不实现判定逻辑**；只读查询不受限。

## 最小落地映射表（role × 实体 × add/change/delete）

| role | 可写实体（add / change / delete 同步） | 映射外实体 |
| --- | --- | --- |
| `admin` | **全部** | — |
| `engineer` | `Requirement` / `RequirementParam` / `Part` / `PartParam` / `Bom` / `BomItem` | 只读 |
| `procurement` | `Supplier` / `SupplierPart` / `PurchaseOrder` / `InventoryLot` / `WorkOrder` | 只读 |
| `test` | `TestCase` / `TestRun` | 只读 |
| `quality` | `ECN` / `ECNImpact` / `TraceLink` / `AgentRun` | 只读 |

未映射实体：`Project` / `User` / `Document` / `GitRepo` / `GitCommit`（见「已知局限」）。

## 实现

- `core/admin.py`：`WRITABLE_BY_ROLE`（`model_name` → 可写 role 集合）+ `RoleWritePermissionMixin`。
- 13 个 core `ModelAdmin`（Project/Part/Supplier/Requirement/TestCase/TestRun/Bom/BomItem/InventoryLot/PurchaseOrder/WorkOrder/ECN/ECNImpact）与 `traceability.TraceLinkAdmin` 继承 mixin。
- `has_add_permission` / `has_change_permission` / `has_delete_permission` = `f(request.user.role)`：
  `is_superuser` 或 `role == "admin"` → 全权；否则 `model._meta.model_name ∈ WRITABLE_BY_ROLE[role]`。
- `has_view_permission` 恒 True（active 用户可读）——**只读查询不受限**（L84）；非 staff / 未登录由 Django `AdminSite` 层拦截（302/403）。
- **只读类维持现状**：`Document`（add 放开、change/delete 关；照 ADR-0009）/ `GitRepo` / `GitCommit`（全只读，`ReadOnlyModelAdmin`）——**不接 mixin、语义不回归**。

## Won't（本轮红线）

- **不做多租户**；**不做复杂 RBAC**；**不引入新权限引擎 / 中间件链**。
- 权限**只影响 Admin 写路径**；**服务层不设权限门**（v1：`agents/*` service、`core/ecn.py`、`core/kitting.py` 等调用不经 Admin 权限；测试 `test_service_not_gated_by_admin_permission` 锁定）。

## 测试

`tests/test_permissions_r3.py`：role × 实体**写矩阵**（允许 → add 页 200 / 拒绝 → 403）；**读路径 200**（映射外实体列表页）；superuser 全权；非 staff 与未登录 → 302/403；**服务层不经 Admin 权限**。

## 已知局限（登记）

- `AgentRun` 的实质写路径是 **Admin action**（`approve_selected` / `reject_selected`）→ 服务层；本轮 **action 层不加 role 门**（与「服务层不设权限门」一致）。「`quality` 可写 `AgentRun`」当前体现为**可读 + action 可用**；**action 的 role 化留 v2**。
- `User` / `Document` 未纳入映射：`UserAdmin` 由 Django 默认 perms 控制（`admin`-only 效果）；`Document` add 照 ADR-0009。
- 映射外实体的非 `admin` 用户 = **只读**（view 可用、写 403）。
#!/usr/bin/env python
"""D1 种子数据校验（fixtures/demo_seed.json）。

本脚本只做**数据契约校验**，不依赖 Django / 数据库 / Pydantic，也不含业务逻辑：

1. JSON 可解析，顶层键与 ``demonstration_project_requirements.md`` 一致（22 个，多/少均报错）；
2. 各实体业务编号在 ``(project, 类型)`` 内唯一，且 ``id`` 在集合内唯一（R2）；
3. 每个含业务编号字段的条目 ``id == <编号字段>``（逐值照搬，R8）；
4. 所有业务编号引用可闭合：FK 字段、多态端点（TraceLink / ECNImpact）、``AgentRun.references``；
5. 多态端点类型落在 ``EntityType`` 白名单内（与 ``schemas/agent_outputs.py`` 对齐）；
6. ``AgentRun.status`` 为四值且 ``confirmed_by`` / ``confirmed_at`` 绑定规则成立（R1）；
7. 每个 ``user.role`` 落在冻结职能枚举内（T2.4）；
8. 演示数据集数量对齐 PRD AC-001（``==`` 精确清点 / ``>=`` 下限，V-01）；
9. 防幻觉（failed AgentRun）/ 停产料 / 长交期样例齐备（V-01）。

退出码：0 全部通过；1 存在校验失败。
用法：``python scripts/validate_seed.py [seed_path]``
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SEED = REPO_ROOT / "fixtures" / "demo_seed.json"

REQUIRED_KEYS = {
    "project",
    "users",
    "parts",
    "part_params",
    "suppliers",
    "supplier_parts",
    "requirements",
    "requirement_params",
    "boms",
    "bom_items",
    "inventory_lots",
    "work_orders",
    "purchase_orders",
    "test_cases",
    "test_runs",
    "ecns",
    "ecn_impacts",
    "trace_links",
    "documents",
    "git_repos",
    "git_commits",
    "agent_runs",
}

# 集合 → 业务编号字段（R2；对外标识，非数据库主键）
BIZNO = {
    "project": "id",
    "users": "id",
    "parts": "part_number",
    "suppliers": "code",
    "requirements": "code",
    "boms": "bom_no",
    "bom_items": "item_no",
    "inventory_lots": "serial_number",
    "work_orders": "code",
    "purchase_orders": "po_number",
    "test_cases": "code",
    "test_runs": "run_no",
    "ecns": "ecn_number",
    "documents": "doc_no",
    "git_repos": "id",
    "git_commits": "sha",
}

# 集合 → [(FK 字段, 目标集合)]，值均为业务编号；None / 缺失跳过
FK_REFS = {
    "project": [("created_by_id", "users")],
    "parts": [("project_id", "project")],
    "part_params": [("part_id", "parts")],
    "suppliers": [("project_id", "project")],
    "supplier_parts": [("part_id", "parts"), ("supplier_id", "suppliers")],
    "requirements": [
        ("project_id", "project"),
        ("agent_run_id", "agent_runs"),
        ("confirmed_by_id", "users"),
    ],
    "requirement_params": [("requirement_id", "requirements")],
    "boms": [("project_id", "project"), ("created_by_id", "users")],
    "bom_items": [("bom_id", "boms"), ("parent_item_id", "bom_items"), ("part_id", "parts")],
    "inventory_lots": [("project_id", "project"), ("part_id", "parts")],
    "work_orders": [("project_id", "project"), ("bom_id", "boms"), ("created_by_id", "users")],
    "purchase_orders": [("project_id", "project"), ("supplier_id", "suppliers")],
    "test_cases": [("project_id", "project")],
    "test_runs": [
        ("project_id", "project"),
        ("test_case_id", "test_cases"),
        ("tester_id", "users"),
    ],
    "ecns": [
        ("project_id", "project"),
        ("requested_by_id", "users"),
        ("approved_by_id", "users"),
        ("agent_run_id", "agent_runs"),
    ],
    "ecn_impacts": [("ecn_id", "ecns")],
    "trace_links": [
        ("project_id", "project"),
        ("agent_run_id", "agent_runs"),
        ("confirmed_by_id", "users"),
    ],
    "documents": [("project_id", "project"), ("uploaded_by_id", "users")],
    "git_repos": [("project_id", "project")],
    "git_commits": [("repo_id", "git_repos"), ("project_id", "project")],
    "agent_runs": [("project_id", "project"), ("confirmed_by_id", "users")],
}

# EntityType 白名单：可作 TraceLink 端点 / TraceNode 的类型（与 schemas/agent_outputs.py 对齐）
ENTITY_TYPE_COLLECTION = {
    "requirement": "requirements",
    "part": "parts",
    "supplier": "suppliers",
    "bom": "boms",
    "bom_item": "bom_items",
    "inventory_lot": "inventory_lots",
    "work_order": "work_orders",
    "purchase_order": "purchase_orders",
    "test_case": "test_cases",
    "test_run": "test_runs",
    "ecn": "ecns",
    "document": "documents",
    "git_commit": "git_commits",
}

# SourceRef.type（ReferenceType）：在 EntityType 基础上额外允许审计记录 trace_link
REF_TYPE_COLLECTION = {**ENTITY_TYPE_COLLECTION, "trace_link": "trace_links"}

# 无独立业务编号、但可被引用（按 ``id`` 解析）的集合
ID_INDEXED_COLLECTIONS = {"trace_links", "agent_runs"}

AGENT_RUN_STATUS = {"failed", "needs_review", "success", "rejected"}
CONFIRMED_STATUS = {"success", "rejected"}

# 数量断言（T2.0/V-01，对齐 PRD AC-001 清点）：== 精确清点、>= 下限
COUNT_EQUALS = {
    "project": 1,
    "parts": 20,
    "requirements": 5,
    "test_cases": 10,
    "suppliers": 3,
    "purchase_orders": 5,
    "inventory_lots": 3,
    "ecns": 2,
}
COUNT_MIN = {
    "test_runs": 10,
    "part_params": 30,
    "boms": 1,
    "git_commits": 3,
}

# User.role 冻结职能枚举（T2.4，以 PRD §3 为权威）
ROLE_ENUM = {"admin", "engineer", "procurement", "test", "quality"}


class Validator:
    def __init__(self, data: dict) -> None:
        self.data = data
        self.errors: list[str] = []
        # (collection, bizno) -> row，用于引用解析
        self.index: dict[str, dict[str, dict]] = {}

    def fail(self, message: str) -> None:
        self.errors.append(message)

    def rows(self, coll: str) -> list[dict]:
        value = self.data.get(coll)
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        return []

    def build_index(self) -> None:
        # 注：project 归属一致性校验（R9 解析键含 project_id）在单项目 fixture 下延后至
        # D2 引用核验统一实现；BomItem 等无 project_id 的实体经父级 FK 间接归属。
        for coll, bizno_field in BIZNO.items():
            rows = self.rows(coll)
            if not rows:
                continue
            table: dict[str, dict] = {}
            bizno_counts: Counter = Counter()
            for row in rows:
                bizno = row.get(bizno_field)
                if not bizno:
                    self.fail(f"{coll}: 缺少业务编号字段 {bizno_field}（{row.get('id')}）")
                    continue
                scope = row.get("project_id")

                key = f"{scope}|{bizno}" if scope else f"|{bizno}"
                bizno_counts[key] += 1
                table[bizno] = row
            for key, count in bizno_counts.items():
                if count > 1:
                    self.fail(f"{coll}: 业务编号重复 {key}（{count} 次）")
            self.index[coll] = table
        for coll in ID_INDEXED_COLLECTIONS:
            self.index[coll] = {
                row["id"]: row
                for row in self.data.get(coll, []) or []
                if isinstance(row, dict) and row.get("id")
            }

    def check_ids_unique(self) -> None:
        for coll, rows in self.data.items():
            if not isinstance(rows, list):
                continue
            ids = [r.get("id") for r in rows if isinstance(r, dict)]
            for dup, count in Counter(ids).items():
                if count > 1:
                    self.fail(f"{coll}: id 重复 {dup}（{count} 次）")

    def check_bizno_equals_id(self) -> None:
        """R8：fixture 每个条目的 ``id`` 必须等于该实体业务编号字段的值。"""
        for coll, field in BIZNO.items():
            if field == "id":
                continue
            for row in self.rows(coll):
                rid = row.get("id")
                value = row.get(field)
                if rid != value:
                    self.fail(
                        f"{coll}: id 与业务编号字段不一致 id={rid!r} {field}={value!r}（R8）"
                    )

    def check_user_roles(self) -> None:
        """T2.4：每个 ``user.role`` 必须落在冻结职能枚举内。"""
        for row in self.rows("users"):
            role = row.get("role")
            if role not in ROLE_ENUM:
                self.fail(
                    f"users {row.get('id')}: role 非法 {role!r}（须为 {sorted(ROLE_ENUM)} 之一）"
                )

    def check_ref(self, coll: str, field: str, target: str, value: str) -> None:
        # 注：此处仅按业务编号解析存在性；project 归属一致性（R9）在单项目 fixture 下延后至 D2。
        table = self.index.get(target, {})
        if value not in table:
            self.fail(f"{coll}.{field} → {target}: 引用无法闭合 {value!r}")

    def check_fk_refs(self) -> None:
        for coll, refs in FK_REFS.items():
            for row in self.rows(coll):
                for field, target in refs:
                    value = row.get(field)
                    if value is None:
                        continue
                    self.check_ref(coll, field, target, value)

    def check_polymorphic(self) -> None:
        for row in self.rows("trace_links"):
            for type_field, id_field in (("from_type", "from_id"), ("to_type", "to_id")):
                etype = row.get(type_field)
                eid = row.get(id_field)
                target = ENTITY_TYPE_COLLECTION.get(etype)
                if target is None:
                    self.fail(f"trace_links {row.get('id')}.{type_field}: 非端点类型 {etype!r}")
                    continue
                self.check_ref("trace_links", id_field, target, eid)
        for row in self.rows("ecn_impacts"):
            etype = row.get("affected_type")
            eid = row.get("affected_id")
            target = ENTITY_TYPE_COLLECTION.get(etype)
            if target is None:
                self.fail(f"ecn_impacts {row.get('id')}.affected_type: 非端点类型 {etype!r}")
                continue
            self.check_ref("ecn_impacts", "affected_id", target, eid)

    def check_source_refs(self) -> None:
        for row in self.rows("agent_runs"):
            for ref in row.get("references", []) or []:
                if not isinstance(ref, dict):
                    continue
                rtype = ref.get("type")
                rid = ref.get("id")
                if not rid:
                    # 自由文本引用（页码 / 章节 / 文件名片段）不核验
                    continue
                target = REF_TYPE_COLLECTION.get(rtype)
                if target is None:
                    self.fail(f"agent_runs {row.get('id')}.references: 未知类型 {rtype!r}")
                    continue
                self.check_ref("agent_runs", "references", target, rid)

    def check_agent_run_status(self) -> None:
        for row in self.rows("agent_runs"):
            aid = row.get("id")
            status = row.get("status")
            if status not in AGENT_RUN_STATUS:
                self.fail(f"agent_runs {aid}: status 非法 {status!r}（须为四值之一）")
                continue
            has_conf = bool(row.get("confirmed_by_id")) and bool(row.get("confirmed_at"))
            if status in CONFIRMED_STATUS and not has_conf:
                self.fail(f"agent_runs {aid}: status={status} 须同时提供 confirmed_by_id / confirmed_at")
            if status not in CONFIRMED_STATUS and has_conf:
                self.fail(f"agent_runs {aid}: status={status} 时 confirmed_by_id / confirmed_at 必须为 NULL")

    def check_counts(self) -> None:
        """V-01：演示数据集清点对齐 PRD AC-001（``COUNT_EQUALS`` 精确 / ``COUNT_MIN`` 下限）。"""
        for coll, expected in COUNT_EQUALS.items():
            actual = len(self.rows(coll))
            if actual != expected:
                self.fail(f"{coll}: 数量 {actual} != 期望 {expected}（AC-001 清点）")
        for coll, minimum in COUNT_MIN.items():
            actual = len(self.rows(coll))
            if actual < minimum:
                self.fail(f"{coll}: 数量 {actual} < 下限 {minimum}（AC-001 清点）")

    def check_demo_requirements(self) -> None:
        """V-01：防幻觉 / 停产料 / 长交期演示样例齐备。"""
        has_failed = any(
            row.get("status") == "failed"
            and row.get("invalid_references")
            and row.get("reference_check_passed") is False
            and not row.get("confirmed_by_id")
            and not row.get("confirmed_at")
            for row in self.rows("agent_runs")
        )
        if not has_failed:
            self.fail(
                "agent_runs: 缺少 status=failed 且 invalid_references 非空、"
                "reference_check_passed=false、confirmed_by/at 为 NULL 的防幻觉样例（V-01）"
            )
        if not any(
            row.get("lifecycle_status") in {"obsolete", "discontinued"}
            for row in self.rows("parts")
        ):
            self.fail("parts: 缺少停产料样例（lifecycle_status ∈ {obsolete, discontinued}）")
        if not any(
            (row.get("lead_time_days") or 0) > 60 for row in self.rows("supplier_parts")
        ):
            self.fail("supplier_parts: 缺少 lead_time_days > 60 的长交期样例")

    def run(self) -> list[str]:
        keys = set(self.data)
        for missing in sorted(REQUIRED_KEYS - keys):
            self.fail(f"缺少顶层键：{missing}")
        for extra in sorted(keys - REQUIRED_KEYS):
            self.fail(f"存在未预期顶层键：{extra}")
        self.build_index()
        self.check_ids_unique()
        self.check_bizno_equals_id()
        self.check_user_roles()
        self.check_fk_refs()
        self.check_polymorphic()
        self.check_source_refs()
        self.check_agent_run_status()
        self.check_counts()
        self.check_demo_requirements()
        return self.errors


def main(argv: list[str]) -> int:
    seed_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_SEED
    if not seed_path.exists():
        print(f"[FAIL] 种子文件不存在：{seed_path}")
        return 1
    try:
        data = json.loads(seed_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[FAIL] JSON 解析失败：{exc}")
        return 1
    if not isinstance(data, dict):
        print("[FAIL] 顶层结构必须是 JSON 对象")
        return 1

    errors = Validator(data).run()
    if errors:
        print(f"[FAIL] 种子校验未通过，共 {len(errors)} 项：")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"[OK] 种子校验通过：{seed_path}")
    print(f"     顶层键 {len(data)} 个；TraceLink {len(data.get('trace_links', []))} 条；引用闭包完整。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
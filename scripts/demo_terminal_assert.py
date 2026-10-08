#!/usr/bin/env python
"""D13-R1：演示库终态断言（配合 ``scripts/demo_reset.ps1``）。

两种模式：

- ``--expect base``：仅确定性 bootstrap 后（fixtures 5 条 AgentRun）；
- ``--expect full``：三类真实调用各 1 条后（AgentRun=8，``needs_review`` 行 id=6/7/8）。

断言内容：22 集合计数 + AgentRun 矩阵 + 关键不变量（``BI-001.part=PART-001``、
``ECN-001`` 未应用）。退出码：0 全过；1 有失败。

用法：``python scripts/demo_terminal_assert.py --expect base``
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from agents.models import AgentRun  # noqa: E402
from core.models import (  # noqa: E402
    Bom,
    BomItem,
    Document,
    ECN,
    ECNImpact,
    GitCommit,
    GitRepo,
    InventoryLot,
    Part,
    PartParam,
    Project,
    PurchaseOrder,
    Requirement,
    RequirementParam,
    Supplier,
    SupplierPart,
    TestCase,
    TestRun,
    User,
    WorkOrder,
)
from traceability.models import TraceLink  # noqa: E402

# 22 集合 → (模型, fixtures 基准计数)。``agent_runs`` 基准随模式浮动（5 / 8）。
EXPECTED_COUNTS = {
    "project": (Project, 1),
    "users": (User, 5),
    "parts": (Part, 20),
    "part_params": (PartParam, 36),
    "suppliers": (Supplier, 3),
    "supplier_parts": (SupplierPart, 13),
    "requirements": (Requirement, 5),
    "requirement_params": (RequirementParam, 12),
    "boms": (Bom, 1),
    "bom_items": (BomItem, 16),
    "inventory_lots": (InventoryLot, 3),
    "work_orders": (WorkOrder, 1),
    "purchase_orders": (PurchaseOrder, 5),
    "test_cases": (TestCase, 10),
    "test_runs": (TestRun, 12),
    "ecns": (ECN, 2),
    "ecn_impacts": (ECNImpact, 8),
    "trace_links": (TraceLink, 39),
    "documents": (Document, 5),
    "git_repos": (GitRepo, 1),
    "git_commits": (GitCommit, 3),
    "agent_runs": (AgentRun, 5),
}

BASE_MATRIX = {
    "bom_selection": {"failed": 1, "needs_review": 0, "success": 1},
    "requirement": {"failed": 0, "needs_review": 0, "success": 1},
    "traceability": {"failed": 0, "needs_review": 0, "success": 2},
}

FULL_MATRIX = {
    "bom_selection": {"failed": 1, "needs_review": 1, "success": 1},
    "requirement": {"failed": 0, "needs_review": 1, "success": 1},
    "traceability": {"failed": 0, "needs_review": 1, "success": 2},
}

# D11/D12 终态：三类 needs_review 行 id（真实调用顺序 bom_selection → traceability → requirement）
FULL_NEEDS_REVIEW_IDS = {6: "bom_selection", 7: "traceability", 8: "requirement"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="演示库终态断言")
    parser.add_argument("--expect", choices=("base", "full"), default="base")
    args = parser.parse_args(argv)

    failures: list[str] = []
    expected_agent_runs = 5 if args.expect == "base" else 8

    for name, (model, expected) in EXPECTED_COUNTS.items():
        if name == "agent_runs":
            expected = expected_agent_runs
        actual = model.objects.count()
        if actual != expected:
            failures.append(f"{name}: {actual} != {expected}")

    bi = BomItem.objects.filter(item_no="BI-001").first()
    actual_part = bi.part.part_number if bi and bi.part else None
    if actual_part != "PART-001":
        failures.append(f"BI-001.part != PART-001（实际 {actual_part!r}）")

    if TraceLink.objects.filter(
        relation_type="affects", to_type="test_case", to_id="TC-009"
    ).exists():
        failures.append("ECN-001 已应用（存在 TC-009 affects 边），非种子态")

    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for run in AgentRun.objects.all():
        matrix[run.agent_name][run.status] += 1
    expected_matrix = BASE_MATRIX if args.expect == "base" else FULL_MATRIX
    for agent, statuses in expected_matrix.items():
        for status, count in statuses.items():
            actual = matrix[agent][status]
            if actual != count:
                failures.append(f"AgentRun[{agent}][{status}]: {actual} != {count}")

    if args.expect == "full":
        for run_id, agent in FULL_NEEDS_REVIEW_IDS.items():
            run = AgentRun.objects.filter(pk=run_id).first()
            if run is None:
                failures.append(f"run {run_id} 不存在")
            elif run.agent_name != agent or run.status != "needs_review":
                failures.append(
                    f"run {run_id}: 期望 {agent}/needs_review，实际 "
                    f"{run.agent_name}/{run.status}"
                )

    if failures:
        print("[FAIL] 终态断言未通过：")
        for item in failures:
            print(f"  - {item}")
        return 1
    print(f"[OK] 终态断言全过（expect={args.expect}）：22 集合 + 矩阵 + 关键不变量")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
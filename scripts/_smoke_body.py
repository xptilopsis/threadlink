"""D14-R2：容器内 smoke 断言体（由 compose_smoke.ps1 复制入容器后执行）。

运行方式：
    docker compose cp scripts/_smoke_body.py web:/tmp/_smoke_body.py
    docker compose exec -T web python /tmp/_smoke_body.py

Host 白名单：Django 的 test Client 请求 Host 为 'testserver'，容器 ALLOWED_HOSTS 未必包含，
故在 settings 层就地补齐 —— **不依赖** compose/exec 传 `-e DJANGO_ALLOWED_HOSTS`
（避免污染生产 compose 环境、避免传参漏配）。

断言口径（v4）：每条独立、独立诊断（失败打印 `[断言名] 期望=X 实际=Y`），不聚合。
DB 版追溯链无 LLM → `summary=None` 是契约 Optional 的正确值（D4-R3），显式断言为 None。
"""

import os
import sys

# 容器内代码根；脚本从 /tmp 执行时须显式加入（SMOKE_APP_ROOT 可覆盖，默认 /app）
sys.path.insert(0, os.environ.get("SMOKE_APP_ROOT", "/app"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402

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

COLLECTIONS = [
    Project,
    Part,
    PartParam,
    Supplier,
    SupplierPart,
    Requirement,
    RequirementParam,
    Bom,
    BomItem,
    InventoryLot,
    WorkOrder,
    PurchaseOrder,
    TestCase,
    TestRun,
    ECN,
    ECNImpact,
    TraceLink,
    Document,
    GitRepo,
    GitCommit,
    AgentRun,
    User,
]


def check(name, ok, expected, actual, detail=""):
    """单条断言：独立打印 PASS/FAIL；失败返回诊断串，成功返回 None。"""
    if ok:
        print(f"  [PASS] {name} (actual={actual!r})")
        return None
    msg = f"[{name}] 期望={expected} 实际={actual!r}"
    if detail:
        msg += f" | {detail}"
    print(f"  [FAIL] {msg}")
    return msg


def main() -> int:
    failures = []

    print("== collections (each > 0) ==")
    for model in COLLECTIONS:
        name = model.__name__
        try:
            count = model.objects.count()
        except Exception as exc:  # noqa: BLE001
            msg = f"[collection:{name}] 期望>0 实际=query_error:{exc}"
            print(f"  [FAIL] {msg}")
            failures.append(msg)
            continue
        msg = check(f"collection:{name}", count > 0, ">0", count)
        if msg:
            failures.append(msg)

    msg = check("collections:count", len(COLLECTIONS) == 22, 22, len(COLLECTIONS))
    if msg:
        failures.append(msg)

    print("== admin ==")
    client = None
    user = get_user_model().objects.filter(username="admin").first()
    if user is None:
        msg = "[admin:user] 期望=admin 存在 实际=missing"
        print(f"  [FAIL] {msg}")
        failures.append(msg)
    else:
        client = Client()
        client.force_login(user)

    if client is not None:
        resp = client.get("/admin/")
        body = resp.content.decode("utf-8", "replace")
        msg = check("admin:status", resp.status_code == 200, 200, resp.status_code, body[:200])
        if msg:
            failures.append(msg)
        markers = [m for m in ("Traceback", "DisallowedHost") if m in body]
        msg = check(
            "admin:no_error_page",
            not markers,
            "无 Traceback/DisallowedHost",
            markers or "clean",
            body[:200] if markers else "",
        )
        if msg:
            failures.append(msg)

        print("== trace chain (db-backed) ==")
        resp = client.get("/trace/serial/SN-DEMO-001/?format=json")
        body = resp.content.decode("utf-8", "replace")
        msg = check("trace:status", resp.status_code == 200, 200, resp.status_code, body[:200])
        if msg:
            failures.append(msg)

        data = None
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            msg = f"[trace:json] 期望=JSON 实际=parse_error:{exc} | body={body[:200]!r}"
            print(f"  [FAIL] {msg}")
            failures.append(msg)

        if data is not None:
            msg = check("trace:found", data.get("found") is True, True, data.get("found"))
            if msg:
                failures.append(msg)
            msg = check("trace:complete", data.get("complete") is True, True, data.get("complete"))
            if msg:
                failures.append(msg)
            msg = check("trace:missing", data.get("missing") == [], [], data.get("missing"))
            if msg:
                failures.append(msg)

            nodes = data.get("nodes") or []
            edges = data.get("edges") or []
            msg = check("trace:nodes_len", len(nodes) == 31, 31, len(nodes))
            if msg:
                failures.append(msg)
            msg = check("trace:edges_len", len(edges) == 37, 37, len(edges))
            if msg:
                failures.append(msg)

            # GT-TRACE-004：每个节点 source_refs 非空（逐节点断言）
            empty_refs = [
                i for i, node in enumerate(nodes) if not (node.get("source_refs") or [])
            ]
            msg = check(
                "trace:node_source_refs",
                not empty_refs,
                "每节点 source_refs 非空",
                f"empty_indices={empty_refs[:10]} (total {len(empty_refs)})",
            )
            if msg:
                failures.append(msg)

            # DB 版无 LLM：summary 必须显式为 None（契约 Optional，D4-R3）
            msg = check("trace:summary_none", data.get("summary") is None, None, data.get("summary"))
            if msg:
                failures.append(msg)

    if failures:
        print(f"SMOKE FAIL ({len(failures)} assertion(s))")
        for item in failures:
            print(" -", item)
        return 1

    print("SMOKE PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
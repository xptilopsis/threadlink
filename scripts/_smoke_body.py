"""D14-R2：容器内 smoke 断言体（由 compose_smoke.ps1 复制入容器后执行）。

运行方式：
    docker compose cp scripts/_smoke_body.py web:/tmp/_smoke_body.py
    docker compose exec -T web python /tmp/_smoke_body.py

Host 白名单：Django 的 test Client 请求 Host 为 'testserver'，容器 ALLOWED_HOSTS 未必包含，
故在 settings 层就地补齐 —— **不依赖** compose/exec 传 `-e DJANGO_ALLOWED_HOSTS`
（避免污染生产 compose 环境、避免传参漏配）。
"""

import os
import sys

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


def main() -> int:
    failures = []

    print("== collections ==")
    for model in COLLECTIONS:
        try:
            count = model.objects.count()
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{model.__name__}: query error {exc}")
            continue
        print(f"  {model.__name__:24s} {count}")
        if count <= 0:
            failures.append(f"{model.__name__}: expected >0, got {count}")
    print(f"COLLECTIONS {len(COLLECTIONS)}")

    client = None
    user = get_user_model().objects.filter(username="admin").first()
    if user is None:
        failures.append("admin user missing")
    else:
        client = Client()
        client.force_login(user)

    if client is not None:
        checks = [
            ("/admin/", 200, None),
            ("/trace/serial/SN-DEMO-001/?format=json", 200, {"nodes": 31, "edges": 37}),
        ]
        for url, want_status, extra in checks:
            resp = client.get(url)
            body = resp.content.decode("utf-8", "replace")
            ok = resp.status_code == want_status
            detail = ""
            if extra is not None:
                try:
                    data = resp.json()
                except Exception:  # noqa: BLE001
                    data = {}
                    ok = False
                detail = f" nodes={data.get('nodes')} edges={data.get('edges')}"
                for key, expected in extra.items():
                    if data.get(key) != expected:
                        ok = False
            print(f"HTTP {resp.status_code} {url}{detail} -> {'OK' if ok else 'FAIL'}")
            if not ok:
                failures.append(
                    f"{url}: status={resp.status_code} body[:200]={body[:200]!r}"
                )

    if failures:
        print("SMOKE FAIL")
        for item in failures:
            print(" -", item)
        return 1

    print("SMOKE PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
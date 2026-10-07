"""D11-R3 §1：role → 可写实体集权限矩阵（轻量；只影响 Admin 写路径）。

- 写路径：role 映射内 → 200（add 页），映射外 → 403；
- 读路径：映射外实体列表页仍 200（读不受限）；
- superuser / role=admin → 全权；
- 非 staff / 未登录 → 302/403（不泄露内容）；
- **服务层不经 Admin 权限**（v1：service 不设 role 门）。
"""

import pytest
from django.core.management import call_command

from core.ecn import project_ecn_impact
from core.models import ECN, Project, User


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)


def _staff(username):
    user = User.objects.get(username=username)
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return user


def _add_status(client, app, model):
    return client.get(f"/admin/{app}/{model}/add/").status_code


def _list_status(client, app, model):
    return client.get(f"/admin/{app}/{model}/").status_code


# --- role × 实体 写/读矩阵 --------------------------------------------------
@pytest.mark.parametrize(
    "username,allowed,denied",
    [
        (
            "rd_engineer",
            [("core", "part"), ("core", "requirement"), ("core", "bom"), ("core", "bomitem")],
            [("core", "supplier"), ("core", "ecn"), ("core", "testcase")],
        ),
        (
            "buyer",
            [("core", "supplier"), ("core", "purchaseorder"), ("core", "inventorylot"), ("core", "workorder")],
            [("core", "part"), ("core", "ecn"), ("core", "testcase")],
        ),
        (
            "tester",
            [("core", "testcase"), ("core", "testrun")],
            [("core", "part"), ("core", "supplier")],
        ),
        (
            "pm",
            [("core", "ecn"), ("core", "ecnimpact"), ("traceability", "tracelink")],
            [("core", "part"), ("core", "supplier")],
        ),
    ],
)
def test_role_write_matrix(seeded, client, username, allowed, denied):
    client.force_login(_staff(username))
    for app, model in allowed:
        assert _add_status(client, app, model) == 200, (username, app, model)
    for app, model in denied:
        assert _add_status(client, app, model) == 403, (username, app, model)


def test_read_path_not_restricted(seeded, client):
    """不可写实体（映射外）的**列表页仍可读**（读路径不受限）。"""

    client.force_login(_staff("rd_engineer"))
    assert _list_status(client, "core", "supplier") == 200
    assert _list_status(client, "core", "ecn") == 200


def test_superuser_full_permissions(seeded, client):
    admin = User.objects.get(username="admin")  # 超管
    assert admin.is_superuser is True
    client.force_login(admin)
    for app, model in [("core", "part"), ("core", "supplier"), ("core", "ecn"), ("core", "testrun")]:
        assert _add_status(client, app, model) == 200


def test_non_staff_denied(seeded, client):
    user = User.objects.get(username="rd_engineer")  # fixtures：非 staff
    assert user.is_staff is False
    client.force_login(user)
    assert client.get("/admin/core/part/").status_code in (302, 403)
    assert client.get("/admin/core/part/add/").status_code in (302, 403)


def test_anonymous_redirects_to_login(seeded, client):
    resp = client.get("/admin/core/part/")
    assert resp.status_code == 302
    assert "/admin/login/" in resp["Location"]


# --- 服务层不经 Admin 权限（v1） --------------------------------------------
def test_service_not_gated_by_admin_permission(seeded):
    """service 直调不经 role 权限门（无 request 依赖）。"""

    project = Project.objects.get(code="DEMO-GW")
    ecn = ECN.objects.get(project=project, ecn_number="ECN-001")
    result = project_ecn_impact(ecn)
    assert result["ecn"] == "ECN-001"
    assert "impacts" in result
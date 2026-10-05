"""D4-R1：TraceLink 解析服务 + Admin + 手工建链冒烟。

先数后写（fixtures 实况）：13 类端点各取首条业务编号；``trace_links`` = 39 条，
其中 ``TL-010`` = REQ-001 → PART-001（satisfied_by）已存在（建链冒烟前先清该重复边）。
"""

import pytest
from django.core.management import call_command

from core.models import (
    Bom,
    BomItem,
    GitCommit,
    GitRepo,
    Part,
    Project,
    User,
)
from core.numbering import numbering_suspended
from traceability.models import TraceLink
from traceability.services import (
    AmbiguousReferenceError,
    EntityNotFoundError,
    UnknownEntityTypeError,
    create_trace_link,
    resolve_entity,
)


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


@pytest.fixture
def project(seeded):
    return Project.objects.get(code="DEMO-GW")


GIT_SHA = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"

RESOLVE_CASES = [
    ("part", "PART-001", "part_number"),
    ("supplier", "SUP-001", "code"),
    ("requirement", "REQ-001", "code"),
    ("bom", "BOM-001", "bom_no"),
    ("bom_item", "BI-001", "item_no"),
    ("inventory_lot", "SN-DEMO-001", "serial_number"),
    ("work_order", "WO-001", "code"),
    ("purchase_order", "PO-001", "po_number"),
    ("test_case", "TC-001", "code"),
    ("test_run", "TR-001", "run_no"),
    ("ecn", "ECN-001", "ecn_number"),
    ("document", "DOC-001", "doc_no"),
    ("git_commit", GIT_SHA, "sha"),
]


# --- 1) resolve 13 类 ------------------------------------------------------
@pytest.mark.parametrize("entity_type,business_no,field", RESOLVE_CASES)
def test_resolve_entity_ok(project, entity_type, business_no, field):
    obj = resolve_entity(project.pk, entity_type, business_no)
    assert getattr(obj, field) == business_no


# --- 2) 异常三例 -----------------------------------------------------------
def test_resolve_not_found(project):
    with pytest.raises(EntityNotFoundError):
        resolve_entity(project.pk, "part", "PART-999")


def test_resolve_unknown_type(project):
    with pytest.raises(UnknownEntityTypeError):
        resolve_entity(project.pk, "knowledge_item", "X-001")


def test_resolve_ambiguous_bom_item(seeded, project):
    part = Part.objects.get(part_number="PART-001")
    second_bom = Bom.objects.create(
        project=project, name="歧义 BOM", version="v9.9", created_by=seeded
    )
    with numbering_suspended():
        BomItem.objects.create(bom=second_bom, item_no="BI-001", part=part)
    with pytest.raises(AmbiguousReferenceError):
        resolve_entity(project.pk, "bom_item", "BI-001")


def test_resolve_ambiguous_git_commit(seeded, project):
    repo = GitRepo.objects.create(
        project=project, name="demo-firmware-2", local_path="/tmp/demo-firmware-2"
    )
    GitCommit.objects.create(repo=repo, project=project, sha=GIT_SHA)
    with pytest.raises(AmbiguousReferenceError):
        resolve_entity(project.pk, "git_commit", GIT_SHA)


# --- 3) Admin --------------------------------------------------------------
def test_admin_pages_200(seeded, client):
    client.force_login(seeded)
    link = TraceLink.objects.order_by("id").first()
    for url in (
        "/admin/traceability/tracelink/",
        f"/admin/traceability/tracelink/{link.pk}/change/",
    ):
        assert client.get(url).status_code == 200, url


def test_create_trace_link_smoke(seeded, project):
    # fixture 已有 TL-010 REQ-001 → PART-001 (satisfied_by)；先清该重复边以验证 +1
    TraceLink.objects.filter(
        project=project,
        from_type="requirement",
        from_id="REQ-001",
        to_type="part",
        to_id="PART-001",
        relation_type="satisfied_by",
    ).delete()
    base = TraceLink.objects.count()
    create_trace_link(
        project.pk, "requirement", "REQ-001", "part", "PART-001", "satisfied_by"
    )
    assert TraceLink.objects.count() == base + 1


def test_create_trace_link_rejects_missing(project):
    with pytest.raises(EntityNotFoundError):
        create_trace_link(
            project.pk, "requirement", "REQ-001", "part", "PART-999", "satisfied_by"
        )
    assert not TraceLink.objects.filter(to_id="PART-999").exists()


def _link_post(project, **overrides):
    data = {
        "project": project.pk,
        "from_type": "part",
        "from_id": "PART-001",
        "to_type": "part",
        "to_id": "PART-002",
        "relation_type": "references",
        "source": "manual",
        "created_at_0": "2026-10-05",
        "created_at_1": "10:00:00",
    }
    data.update(overrides)
    return data


def test_admin_form_rejects_missing_id(seeded, client, project):
    client.force_login(seeded)
    response = client.post(
        "/admin/traceability/tracelink/add/", _link_post(project, from_id="PART-999")
    )
    assert response.status_code == 200
    form = response.context["adminform"].form
    assert "from_id" in form.errors


def test_admin_form_rejects_unknown_type(seeded, client, project):
    client.force_login(seeded)
    response = client.post(
        "/admin/traceability/tracelink/add/",
        _link_post(project, from_type="knowledge_item"),
    )
    assert response.status_code == 200
    form = response.context["adminform"].form
    assert "from_type" in form.errors


# --- 4) 计数回归 -----------------------------------------------------------
def test_counts_regression(seeded):
    assert TraceLink.objects.count() == 39
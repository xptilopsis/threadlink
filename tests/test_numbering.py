import pytest

from core import numbering
from core.models import Part, Project, User
from core.numbering import NumberingError, next_number, numbering_suspended


@pytest.fixture
def project(db):
    user = User.objects.create_user(username="num_owner", password="x")
    return Project.objects.create(code="P-NUM", name="编号测试", created_by=user)


def test_auto_increment(project):
    first = Part.objects.create(project=project, name="A")
    second = Part.objects.create(project=project, name="B")
    assert first.part_number == "PART-001"
    assert second.part_number == "PART-002"


def test_manual_value_preserved_then_max_plus_one(project):
    manual = Part.objects.create(project=project, part_number="PART-050", name="manual")
    assert manual.part_number == "PART-050"
    auto = Part.objects.create(project=project, name="after")
    assert auto.part_number == "PART-051"


def test_manual_duplicate_raises(project):
    Part.objects.create(project=project, part_number="PART-001", name="seed")
    with pytest.raises(NumberingError):
        Part.objects.create(project=project, part_number="PART-001", name="dup")


def test_auto_conflict_retries_then_raises(project, monkeypatch):
    Part.objects.create(project=project, part_number="PART-001", name="seed")
    monkeypatch.setattr(numbering, "next_number", lambda *a, **k: "PART-001")
    with pytest.raises(NumberingError):
        Part.objects.create(project=project, name="always-conflict")


def test_import_mode_does_not_generate(project):
    with numbering_suspended():
        part = Part.objects.create(project=project, name="imported")
    assert part.part_number == ""


def test_next_number_overflow_advances_width(project):
    Part.objects.create(project=project, part_number="PART-999", name="max")
    assert (
        next_number(project, "PART-", model=Part, field_name="part_number")
        == "PART-1000"
    )
"""D6-R1：确定性选型引擎 golden tests（GT-BOM-008/009 + 边界 + 确定性）。

- GT-BOM-008：构造最小集 C1/C2/C3 → 80/50/10 排序口径（与 fixture 无关，用独立 Project 隔离）；
- GT-BOM-009：演示 fixture 全表基线（PART-002/001/018 + 17 条排除逐条）；
- 边界：max==min→1.0、tie-break 链、eol 渠道剔除后源数、过滤顺序；
- 确定性：两次调用 JSON 逐字节一致。纯读、零 LLM、零 DB 写。
"""

import json

import pytest
from django.core.management import call_command

from core.models import Part, PartParam, Project, Supplier, SupplierPart, User
from core.selection import Criteria, as_dict, select


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


@pytest.fixture
def project(seeded):
    return Project.objects.get(code="DEMO-GW")


def _make_part(project, supplier_pool, number, price, lead, sources, lifecycle="active"):
    part = Part.objects.create(
        project=project, part_number=number, name=number, lifecycle_status=lifecycle
    )
    PartParam.objects.create(part=part, name="input_voltage", value_min=9, value_max=36)
    PartParam.objects.create(part=part, name="rated_current", value_num=5)
    PartParam.objects.create(part=part, name="operating_temp", value_min=-40, value_max=85)
    PartParam.objects.create(part=part, name="ip_rating", value_text="IP65")
    for index in range(sources):
        SupplierPart.objects.create(
            supplier=supplier_pool[index],
            part=part,
            unit_price=price,
            lead_time_days=lead,
            lifecycle_status="active",
        )
    return part


# --- GT-BOM-008 -------------------------------------------------------------
def test_gt_bom_008_constructed_set(seeded):
    other = Project.objects.create(code="GT008", name="构造集", created_by=seeded)
    pool = list(Supplier.objects.filter(project__code="DEMO-GW").order_by("code"))
    assert len(pool) >= 3
    _make_part(other, pool, "C1", 10, 5, 1)
    _make_part(other, pool, "C2", 20, 5, 3)
    _make_part(other, pool, "C3", 20, 10, 2)

    result = select(other)
    scores = {c.part_number: str(c.total_score) for c in result.passed}
    assert scores == {"C1": "80.00", "C2": "50.00", "C3": "10.00"}
    assert [c.part_number for c in result.passed] == ["C1", "C2", "C3"]
    c1 = result.passed[0]
    assert (str(c1.cost_norm), str(c1.lead_time_norm), str(c1.multi_source_norm)) == (
        "1.00",
        "1.00",
        "0.00",
    )


# --- GT-BOM-009 -------------------------------------------------------------
def test_gt_bom_009_fixture_baseline(seeded, project):
    result = select(project)
    passed = [(c.part_number, str(c.total_score)) for c in result.passed]
    assert passed == [("PART-002", "94.79"), ("PART-001", "87.24"), ("PART-018", "0.00")]

    # 有效渠道明细
    by_no = {c.part_number: c for c in result.passed}
    assert (str(by_no["PART-001"].min_price), by_no["PART-001"].min_lead, by_no["PART-001"].source_count) == (
        "40.0000",
        21,
        2,
    )
    assert by_no["PART-002"].source_count == 3

    # 排除 17 条、reason 逐条匹配
    assert len(result.excluded) == 17
    reasons = {e.part_number: e.reason for e in result.excluded}
    assert reasons["PART-017"] == "lifecycle:obsolete"
    assert reasons["PART-011"] == "current_below_min"
    assert reasons["PART-012"] == "temp_out_of_range"
    missing = {no for no, reason in reasons.items() if reason == "missing_param"}
    assert missing == {
        "PART-003", "PART-004", "PART-005", "PART-006", "PART-007", "PART-008", "PART-009",
        "PART-010", "PART-013", "PART-014", "PART-015", "PART-016", "PART-019", "PART-020",
    }


def test_nrnd_source_warning(seeded, project):
    # 构造：过阶段 1 的 Part + 一个 nrnd 渠道 → 该渠道保留 + warning
    other = Project.objects.create(code="NRND", name="nrnd", created_by=seeded)
    pool = list(Supplier.objects.filter(project__code="DEMO-GW").order_by("code"))
    part = _make_part(other, pool, "N1", 10, 5, 1)
    SupplierPart.objects.create(
        supplier=pool[1], part=part, unit_price=12, lead_time_days=6, lifecycle_status="nrnd"
    )
    result = select(other)
    candidate = result.passed[0]
    assert candidate.source_count == 2  # nrnd 保留为有效渠道
    assert candidate.warnings and candidate.warnings[0].startswith("nrnd_source:")


# --- 边界 -------------------------------------------------------------------
def test_degenerate_dimension_is_one(seeded):
    other = Project.objects.create(code="DEGEN", name="degenerate", created_by=seeded)
    pool = list(Supplier.objects.filter(project__code="DEMO-GW").order_by("code"))
    _make_part(other, pool, "D1", 10, 5, 2)
    _make_part(other, pool, "D2", 10, 5, 2)  # 与 D1 完全同值 → 各维度 max==min → 1.0
    result = select(other)
    assert [str(c.total_score) for c in result.passed] == ["100.00", "100.00"]
    for candidate in result.passed:
        assert (candidate.cost_norm, candidate.lead_time_norm, candidate.multi_source_norm) == (1, 1, 1)


def test_tie_break_part_number_asc(seeded):
    other = Project.objects.create(code="TIE", name="tie", created_by=seeded)
    pool = list(Supplier.objects.filter(project__code="DEMO-GW").order_by("code"))
    _make_part(other, pool, "B", 10, 5, 1)
    _make_part(other, pool, "A", 10, 5, 1)  # 同总分同价 → part_number asc
    result = select(other)
    assert [c.part_number for c in result.passed] == ["A", "B"]


def test_filter_order_lifecycle_before_missing(seeded):
    other = Project.objects.create(code="ORD1", name="ord1", created_by=seeded)
    # obsolete 且缺关键参数 → reason 必须是 lifecycle:obsolete（非 missing_param）
    Part.objects.create(
        project=other, part_number="O1", name="O1", lifecycle_status="obsolete"
    )
    result = select(other)
    assert result.excluded[0].reason == "lifecycle:obsolete"


def test_filter_order_missing_before_threshold(seeded):
    other = Project.objects.create(code="ORD2", name="ord2", created_by=seeded)
    part = Part.objects.create(project=other, part_number="M1", name="M1")
    PartParam.objects.create(part=part, name="input_voltage", value_min=9, value_max=36)
    PartParam.objects.create(part=part, name="rated_current", value_num=3)  # 电流不足
    # 缺 operating_temp/ip_rating → 完整性优先于阈值
    result = select(other)
    assert result.excluded[0].reason == "missing_param"


def test_cost_max_optional(seeded):
    other = Project.objects.create(code="COST", name="cost", created_by=seeded)
    pool = list(Supplier.objects.filter(project__code="DEMO-GW").order_by("code"))
    part = _make_part(other, pool, "K1", 100, 5, 1)
    PartParam.objects.create(part=part, name="unit_cost", value_text="150.00")
    # 默认不启用
    assert select(other).passed
    # 显式启用且超限 → 排除
    result = select(other, Criteria(cost_max=120))
    assert result.excluded[0].reason == "cost_exceeded"


# --- 确定性 -----------------------------------------------------------------
def test_deterministic(seeded, project):
    first = json.dumps(as_dict(select(project)), sort_keys=True, ensure_ascii=False)
    second = json.dumps(as_dict(select(project)), sort_keys=True, ensure_ascii=False)
    assert first == second
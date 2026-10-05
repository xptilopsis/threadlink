"""确定性 BOM 选型引擎（D6-R1）。

纯读、**零 LLM、零 DB 写、零 AgentRun**；逐条对齐冻结规则 ``rules/bom_scoring.v1.json``（v1）。

- 阶段 1 硬过滤顺序（固定）：``lifecycle → param_completeness → param_threshold → cost_max``；
- 有效供货渠道 = ``SupplierPart.lifecycle_status != "eol"``；``nrnd`` 保留 + warning；
- 阶段 2：``min-max`` 归一化（``lower_better`` 用 ``(max-x)/(max-min)``、``higher_better`` 用 ``(x-min)/(max-min)``，
  ``max == min`` 计 1.0）+ 冻结权重 ``cost 0.5 / lead_time 0.3 / multi_source 0.2``，总分 ``100×``；
- 排序：``total desc → cost asc → part_number asc``；``Decimal`` 全程、输出 2 位（ROUND_HALF_UP）。

v1 候选池 = **项目内全部 Part**（类别限定登记 v2）；``cost_max`` 默认 ``None``。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal

from core.models import Part

# --- reason token 全集（rules exclude_reasons 全集 + 为其他输入预留 lifecycle:discontinued）---
REASON_MISSING_PARAM = "missing_param"
REASON_VOLTAGE = "voltage_out_of_range"
REASON_CURRENT = "current_below_min"
REASON_TEMP = "temp_out_of_range"
REASON_IP = "ip_below_min"
REASON_COST = "cost_exceeded"

REASON_TOKENS = (
    "lifecycle:obsolete",
    "lifecycle:discontinued",
    REASON_MISSING_PARAM,
    REASON_VOLTAGE,
    REASON_CURRENT,
    REASON_TEMP,
    REASON_IP,
    REASON_COST,
)

FILTER_ORDER = ("lifecycle", "param_completeness", "param_threshold", "cost_max")
REQUIRED_PARAMS = ("input_voltage", "rated_current", "operating_temp", "ip_rating")
WEIGHTS = {"cost": Decimal("0.5"), "lead_time": Decimal("0.3"), "multi_source": Decimal("0.2")}
DECIMAL_2 = Decimal("0.01")
DEFAULT_TOP = 3


@dataclass
class Criteria:
    voltage_min: Decimal = Decimal(9)
    voltage_max: Decimal = Decimal(36)
    current_min: Decimal = Decimal(5)
    temp_min: Decimal = Decimal(-40)
    temp_max: Decimal = Decimal(85)
    ip_min: int = 65
    cost_max: Decimal | None = None  # 可选；默认 None（演示不启用）


@dataclass
class Excluded:
    part_number: str
    reason: str
    details: dict


@dataclass
class PassedCandidate:
    part_number: str
    total_score: Decimal
    cost_norm: Decimal
    lead_time_norm: Decimal
    multi_source_norm: Decimal
    min_price: Decimal | None
    min_lead: int | None
    source_count: int
    warnings: list


@dataclass
class SelectionResult:
    passed: list
    excluded: list


def _q2(value: Decimal) -> Decimal:
    return value.quantize(DECIMAL_2, rounding=ROUND_HALF_UP)


def _parse_ip(text) -> int | None:
    if not text:
        return None
    match = re.search(r"IP\s*(\d+)", str(text), re.IGNORECASE)
    return int(match.group(1)) if match else None


def _parse_decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def _hard_filter(part, criteria: Criteria):
    """返回 ``(reason, details)``；通过则 ``(None, {})``。"""

    # 1 lifecycle
    if part.lifecycle_status in ("obsolete", "discontinued"):
        return f"lifecycle:{part.lifecycle_status}", {"lifecycle_status": part.lifecycle_status}

    params = {param.name: param for param in part.params.all()}

    # 2 param_completeness
    missing = [name for name in REQUIRED_PARAMS if name not in params]
    if missing:
        return REASON_MISSING_PARAM, {"missing": missing}

    # 3 param_threshold（按 rules criteria 顺序）
    voltage = params["input_voltage"]
    if (
        voltage.value_min is None
        or voltage.value_max is None
        or voltage.value_min > criteria.voltage_min
        or voltage.value_max < criteria.voltage_max
    ):
        return REASON_VOLTAGE, {"value_min": voltage.value_min, "value_max": voltage.value_max}

    current = params["rated_current"]
    if current.value_num is None or current.value_num < criteria.current_min:
        return REASON_CURRENT, {"value_num": current.value_num}

    temp = params["operating_temp"]
    if (
        temp.value_min is None
        or temp.value_max is None
        or temp.value_min > criteria.temp_min
        or temp.value_max < criteria.temp_max
    ):
        return REASON_TEMP, {"value_min": temp.value_min, "value_max": temp.value_max}

    ip = params["ip_rating"]
    ip_value = _parse_ip(ip.value_text)
    if ip_value is None or ip_value < criteria.ip_min:
        return REASON_IP, {"value_text": ip.value_text}

    # 4 cost_max（可选）
    if criteria.cost_max is not None:
        unit_cost = params.get("unit_cost")
        cost = _parse_decimal(unit_cost.value_text) if unit_cost else None
        if cost is None or cost > criteria.cost_max:
            return REASON_COST, {"unit_cost": None if unit_cost is None else unit_cost.value_text}

    return None, {}


def _valid_sources(part):
    sources = [sp for sp in part.supplier_parts.all() if sp.lifecycle_status != "eol"]
    warnings = [f"nrnd_source:{sp.id}" for sp in sources if sp.lifecycle_status == "nrnd"]
    return sources, warnings


def _lower_norm(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    return Decimal("1") if high == low else (high - value) / (high - low)


def _higher_norm(value, low, high) -> Decimal:
    if high == low:
        return Decimal("1")
    return (Decimal(value) - Decimal(low)) / (Decimal(high) - Decimal(low))


def select(project, criteria: Criteria | None = None, top: int = DEFAULT_TOP) -> SelectionResult:
    criteria = criteria or Criteria()
    parts = list(
        Part.objects.filter(project=project)
        .order_by("part_number")
        .prefetch_related("params", "supplier_parts")
    )

    excluded: list[Excluded] = []
    survivors = []
    for part in parts:
        reason, details = _hard_filter(part, criteria)
        if reason is not None:
            excluded.append(Excluded(part.part_number, reason, details))
            continue
        sources, warnings = _valid_sources(part)
        prices = [sp.unit_price for sp in sources if sp.unit_price is not None]
        leads = [sp.lead_time_days for sp in sources if sp.lead_time_days is not None]
        survivors.append(
            {
                "part_number": part.part_number,
                "min_price": min(prices) if prices else None,
                "min_lead": min(leads) if leads else None,
                "source_count": len(sources),
                "warnings": warnings,
            }
        )

    if not survivors:
        return SelectionResult(passed=[], excluded=excluded)

    price_values = [s["min_price"] for s in survivors if s["min_price"] is not None]
    lead_values = [s["min_lead"] for s in survivors if s["min_lead"] is not None]
    count_values = [s["source_count"] for s in survivors]
    cost_lo, cost_hi = (min(price_values), max(price_values)) if price_values else (Decimal(0), Decimal(0))
    lead_lo, lead_hi = (min(lead_values), max(lead_values)) if lead_values else (0, 0)
    ms_lo, ms_hi = min(count_values), max(count_values)

    scored = []
    for s in survivors:
        cost_norm = (
            _lower_norm(s["min_price"], cost_lo, cost_hi) if s["min_price"] is not None else Decimal("1")
        )
        lead_norm = (
            _lower_norm(Decimal(s["min_lead"]), Decimal(lead_lo), Decimal(lead_hi))
            if s["min_lead"] is not None
            else Decimal("1")
        )
        ms_norm = _higher_norm(s["source_count"], ms_lo, ms_hi)
        total = 100 * (
            WEIGHTS["cost"] * cost_norm
            + WEIGHTS["lead_time"] * lead_norm
            + WEIGHTS["multi_source"] * ms_norm
        )
        scored.append(
            PassedCandidate(
                part_number=s["part_number"],
                total_score=_q2(total),
                cost_norm=_q2(cost_norm),
                lead_time_norm=_q2(lead_norm),
                multi_source_norm=_q2(ms_norm),
                min_price=s["min_price"],
                min_lead=s["min_lead"],
                source_count=s["source_count"],
                warnings=s["warnings"],
            )
        )

    scored.sort(
        key=lambda c: (
            -c.total_score,
            c.min_price if c.min_price is not None else Decimal("Infinity"),
            c.part_number,
        )
    )
    return SelectionResult(passed=scored[:top], excluded=excluded)


def _jsonify(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonify(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonify(item) for item in value]
    return value


def as_dict(result: SelectionResult) -> dict:
    """确定性序列化（供逐字节比较）。"""

    return {
        "passed": [
            {
                "part_number": c.part_number,
                "total_score": str(c.total_score),
                "cost_norm": str(c.cost_norm),
                "lead_time_norm": str(c.lead_time_norm),
                "multi_source_norm": str(c.multi_source_norm),
                "min_price": None if c.min_price is None else str(c.min_price),
                "min_lead": c.min_lead,
                "source_count": c.source_count,
                "warnings": c.warnings,
            }
            for c in result.passed
        ],
        "excluded": [
            {"part_number": e.part_number, "reason": e.reason, "details": _jsonify(e.details)}
            for e in result.excluded
        ],
    }
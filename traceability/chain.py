"""DB 版追溯链构建器（D4-R3；D12-R2 扩展）。

纯 DB、只读、无 LLM、无 AgentRun（R1 边界）。负载与冻结契约
``schemas.agent_outputs.TraceabilityAgentOutput`` 同构——**字段名以该文件为准**
（边用 ``from_node_id`` / ``to_node_id``，无 ``from_type``/``to_type``）。

语义遵循 ``docs/interface_contract.md`` §3.1：

- 根未命中：``found=false``、``nodes=[]``、``complete=false``、``missing=["serial_not_found"]``。
- 根命中零边：``found=true``、``nodes=[根]``、``complete=false``、``missing=["no_trace_links"]``。
- 遍历中悬空引用（TraceLink 端点解析失败）：fail-soft——追加
  ``unresolved_reference:<entity_type>:<编号>``，该节点不入 ``nodes``，不中断，``complete=false``。
- 不变量：``complete ⇔ missing==[]``（双向强制，无特例分支）。

**D12-R2 变更（裁决 C1/C2/C3/TRACE-002）**：

- **confirmed 过滤**（TRACE-002）：仅 ``confirmed_by`` 非空边入链。
- **`source_refs` 聚合**（C1）：**每个节点（含根）** = 其全部关联边 ``evidence`` 聚合去重
  （按 ``TraceLink.pk`` 升序）；边照旧聚合。根不再恒为 ``[]``。
- **断点 token**（C2，GT-005）：根 ``InventoryLot`` 关系缺失时写入 ``no_purchase_order`` /
  ``no_test_run``；dangling 仍为 ``unresolved_reference:*``（独立类别）。
- **`depth` / `direction`**（C3，GT-006）：``depth=0``（缺省）→ 全链（与旧行为逐字节一致）；
  ``depth=N>0`` → 保留 ≤N 跳节点 + 两端均在保留集的边，若确裁边则 ``missing`` 增 ``depth_truncated``；
  ``direction=None``（缺省）→ **无向遍历**（保持 31/37）；``forward``/``backward`` → 有向遍历
  （见 ADR-0017「停下列项」）。
"""

from __future__ import annotations

import json
from collections import deque

from django.db.models import Q

from traceability.models import TraceLink
from traceability.services import (
    TraceReferenceError,
    resolve_entity,
)

MAX_DEPTH = 20
NOT_FOUND_TOKEN = "serial_not_found"
NO_TRACE_LINKS_TOKEN = "no_trace_links"
NO_PURCHASE_ORDER_TOKEN = "no_purchase_order"
NO_TEST_RUN_TOKEN = "no_test_run"
DEPTH_TRUNCATED_TOKEN = "depth_truncated"
WARNING_NO_TRACE_LINKS = "未建立追溯链"
UNRESOLVED_TOKEN = "unresolved_reference:{entity_type}:{business_no}"
SOURCED_FROM_RELATION = "sourced_from"
TESTED_BY_RELATION = "tested_by"
VALID_DIRECTIONS = {"forward", "backward"}

_LABELERS = {
    "part": lambda obj: f"{obj.part_number} {obj.name}",
    "supplier": lambda obj: f"{obj.code} {obj.name}",
    "requirement": lambda obj: f"{obj.code} {obj.title}",
    "bom": lambda obj: f"{obj.bom_no} {obj.name}",
    "bom_item": lambda obj: obj.item_no,
    "inventory_lot": lambda obj: obj.serial_number,
    "work_order": lambda obj: obj.code,
    "purchase_order": lambda obj: obj.po_number,
    "test_case": lambda obj: f"{obj.code} {obj.name}",
    "test_run": lambda obj: obj.run_no,
    "ecn": lambda obj: f"{obj.ecn_number} {obj.title}",
    "document": lambda obj: f"{obj.doc_no} {obj.title}",
    "git_commit": lambda obj: obj.sha,
}


def node_label(entity_type: str, obj) -> str:
    """集中定义的 per-type label 函数；缺失时回退 ``str(obj)``。"""

    labeler = _LABELERS.get(entity_type)
    return labeler(obj) if labeler is not None else str(obj)


def serial_not_found_payload(root: str, query_type: str = "serial") -> dict:
    return {
        "agent_name": "traceability",
        "summary": None,
        "root": root,
        "query_type": query_type,
        "found": False,
        "complete": False,
        "nodes": [],
        "edges": [],
        "missing": [NOT_FOUND_TOKEN],
        "trace_refs": [],
        "warnings": [NOT_FOUND_TOKEN],
    }


def _edge_tuple(link):
    confidence = float(link.confidence) if link.confidence is not None else None
    return (
        link.from_type,
        link.from_id,
        link.relation_type,
        link.to_type,
        link.to_id,
        confidence,
    )


def _aggregate_evidence(links) -> list:
    """按 ``TraceLink.pk`` 升序聚合 ``evidence`` 并**稳定去重**（D7-R2 回填）。

    去重键 = ``json.dumps(evidence, sort_keys=True)``，保持首次出现顺序；无 evidence → ``[]``。
    """

    refs: list = []
    seen: set[str] = set()
    for link in sorted(links, key=lambda link: link.pk):
        for evidence in link.evidence or []:
            key = json.dumps(evidence, sort_keys=True, ensure_ascii=False, default=str)
            if key in seen:
                continue
            seen.add(key)
            refs.append(evidence)
    return refs


def build_trace_chain(
    project_id,
    entity_type: str,
    business_no: str,
    query_type: str = "serial",
    depth: int = 0,
    direction: str | None = None,
) -> dict:
    """构建与 ``TraceabilityAgentOutput`` 同构的追溯链负载 dict。

    - ``depth``：``0``=全链；``N>0``=距根 ≤N 跳（截断时 ``missing`` 增 ``depth_truncated``）。
    - ``direction``：``None``=无向（缺省，保持现行 31/37）；``forward``/``backward``=有向。
    - ``confirmed`` 过滤：仅 ``confirmed_by`` 非空边入链。
    """

    try:
        root_obj = resolve_entity(project_id, entity_type, business_no)
    except TraceReferenceError:
        return serial_not_found_payload(business_no, query_type)

    root_key = (entity_type, business_no)
    visited = {root_key}
    # (discovery_depth, node_type, node_id, relation_type(指向前驱), obj)
    discovered = [(0, entity_type, business_no, None, root_obj)]
    queue = deque([(root_key, 0)])
    edge_links: dict[tuple, dict[int, object]] = {}  # edge_key -> {pk: link}
    missing: list[str] = []

    base = TraceLink.objects.filter(project_id=project_id, confirmed_by__isnull=False)

    while queue:
        (cur_type, cur_id), node_depth = queue.popleft()
        if node_depth >= MAX_DEPTH:
            continue
        if direction == "forward":
            links = base.filter(from_type=cur_type, from_id=cur_id)
        elif direction == "backward":
            links = base.filter(to_type=cur_type, to_id=cur_id)
        else:
            links = base.filter(
                Q(from_type=cur_type, from_id=cur_id) | Q(to_type=cur_type, to_id=cur_id)
            )
        for link in links.order_by("from_type", "from_id", "relation_type", "to_type", "to_id"):
            if link.from_type == cur_type and link.from_id == cur_id:
                other_type, other_id = link.to_type, link.to_id
            else:
                other_type, other_id = link.from_type, link.from_id
            other_key = (other_type, other_id)
            edge_links.setdefault(_edge_tuple(link), {})[link.pk] = link
            if other_key in visited:
                continue
            try:
                other_obj = resolve_entity(project_id, other_type, other_id)
            except TraceReferenceError:
                token = UNRESOLVED_TOKEN.format(
                    entity_type=other_type, business_no=other_id
                )
                if token not in missing:
                    missing.append(token)
                continue
            visited.add(other_key)
            discovered.append((node_depth + 1, other_type, other_id, link.relation_type, other_obj))
            queue.append((other_key, node_depth + 1))

    # --- depth 截断（C3） ---------------------------------------------------
    if depth and depth > 0:
        kept = {(row[1], row[2]) for row in discovered if row[0] <= depth}
        truncated = any(row[0] > depth for row in discovered)
        discovered = [row for row in discovered if row[0] <= depth]
        edge_links = {
            key: value
            for key, value in edge_links.items()
            if (key[0], key[1]) in kept and (key[3], key[4]) in kept
        }
        if truncated and DEPTH_TRUNCATED_TOKEN not in missing:
            missing.append(DEPTH_TRUNCATED_TOKEN)

    # --- 断点 token（C2，根批次关系缺失） ----------------------------------
    if not edge_links:
        missing = [NO_TRACE_LINKS_TOKEN]
    elif entity_type == "inventory_lot":
        for relation, token in (
            (SOURCED_FROM_RELATION, NO_PURCHASE_ORDER_TOKEN),
            (TESTED_BY_RELATION, NO_TEST_RUN_TOKEN),
        ):
            exists = TraceLink.objects.filter(
                project_id=project_id,
                from_type="inventory_lot",
                from_id=business_no,
                relation_type=relation,
                confirmed_by__isnull=False,
            ).exists()
            if not exists and token not in missing:
                missing.append(token)

    complete = not missing

    # 节点 evidence 来源 = 保留集内的全部关联边（两端各记一次）
    node_links: dict[tuple, dict[int, object]] = {}
    for key, links_map in edge_links.items():
        node_links.setdefault((key[0], key[1]), {}).update(links_map)
        node_links.setdefault((key[3], key[4]), {}).update(links_map)

    nodes = [
        {
            "node_type": node_type,
            "node_id": node_id,
            "label": node_label(node_type, obj),
            "relation_type": relation_type,
            "depth": row_depth,
            "source_refs": _aggregate_evidence(node_links.get((node_type, node_id), {}).values()),
            "confirmed": False,
            "confirmed_by": None,
            "confirmed_at": None,
        }
        for row_depth, node_type, node_id, relation_type, obj in discovered
    ]
    edge_list = []
    for edge_key in sorted(edge_links):
        from_type, from_id, relation_type, to_type, to_id, confidence = edge_key
        edge_list.append(
            {
                "from_node_id": from_id,
                "to_node_id": to_id,
                "relation_type": relation_type,
                "confidence": confidence,
                "source_refs": _aggregate_evidence(edge_links[edge_key].values()),
            }
        )
    warnings = [WARNING_NO_TRACE_LINKS] if NO_TRACE_LINKS_TOKEN in missing else []
    return {
        "agent_name": "traceability",
        "summary": None,
        "root": business_no,
        "query_type": query_type,
        "found": True,
        "complete": complete,
        "nodes": nodes,
        "edges": edge_list,
        "missing": missing,
        "trace_refs": [],
        "warnings": warnings,
    }
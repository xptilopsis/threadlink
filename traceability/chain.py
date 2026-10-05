"""DB 版追溯链构建器（D4-R3）。

纯 DB、只读、无 LLM、无 AgentRun（R1 边界）。负载与冻结契约
``schemas.agent_outputs.TraceabilityAgentOutput`` 同构——**字段名以该文件为准**
（指令所述 "title" 在 schema 实为 ``TraceNode.label``；边用 ``from_node_id`` /
``to_node_id``，无 ``from_type``/``to_type``）。

语义遵循 ``docs/interface_contract.md`` §3.1：

- 根未命中：``found=false``、``nodes=[]``、``complete=false``、``missing=["serial_not_found"]``。
- 根命中零边：``found=true``、``nodes=[根]``、``complete=false``、``missing=["no_trace_links"]``。
- 遍历中悬空引用（TraceLink 端点解析失败）：fail-soft——追加
  ``unresolved_reference:<entity_type>:<编号>``（**D4 扩展词汇**，D7/D12 对账），
  该节点不入 ``nodes``，不中断，``complete=false``。
- 不变量：``complete ⇔ missing==[]``（双向强制，无特例分支）。

遍历：从根起沿 ``TraceLink`` **无向**遍历（**只走 TraceLink 边、不走 FK**，TraceLink
中心原则），``visited`` 集合防环、深度上限 ``MAX_DEPTH``、project 域过滤；节点解析复用
R1 ``resolve_entity``。确定性：``nodes`` 按 BFS 发现序，``edges`` 按全元组排序去重。
"""

from __future__ import annotations

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
WARNING_NO_TRACE_LINKS = "未建立追溯链"
UNRESOLVED_TOKEN = "unresolved_reference:{entity_type}:{business_no}"

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


def build_trace_chain(project_id, entity_type: str, business_no: str, query_type: str = "serial") -> dict:
    """构建与 ``TraceabilityAgentOutput`` 同构的追溯链负载 dict。"""

    try:
        root_obj = resolve_entity(project_id, entity_type, business_no)
    except TraceReferenceError:
        return serial_not_found_payload(business_no, query_type)

    root_key = (entity_type, business_no)
    visited = {root_key}
    # (depth, node_type, node_id, relation_type(指向前驱), obj)
    discovered = [(0, entity_type, business_no, None, root_obj)]
    queue = deque([(root_key, 0)])
    edges = set()
    missing = []

    while queue:
        (cur_type, cur_id), depth = queue.popleft()
        if depth >= MAX_DEPTH:
            continue
        links = (
            TraceLink.objects.filter(project_id=project_id)
            .filter(
                Q(from_type=cur_type, from_id=cur_id)
                | Q(to_type=cur_type, to_id=cur_id)
            )
            .order_by("from_type", "from_id", "relation_type", "to_type", "to_id")
        )
        for link in links:
            if link.from_type == cur_type and link.from_id == cur_id:
                other_type, other_id = link.to_type, link.to_id
            else:
                other_type, other_id = link.from_type, link.from_id
            other_key = (other_type, other_id)
            if other_key in visited:
                edges.add(_edge_tuple(link))
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
            edges.add(_edge_tuple(link))
            discovered.append((depth + 1, other_type, other_id, link.relation_type, other_obj))
            queue.append((other_key, depth + 1))

    if not edges:
        missing = [NO_TRACE_LINKS_TOKEN]
    complete = not missing

    nodes = [
        {
            "node_type": node_type,
            "node_id": node_id,
            "label": node_label(node_type, obj),
            "relation_type": relation_type,
            "depth": depth,
            "source_refs": [],
            "confirmed": False,
            "confirmed_by": None,
            "confirmed_at": None,
        }
        for depth, node_type, node_id, relation_type, obj in discovered
    ]
    edge_list = [
        {
            "from_node_id": from_id,
            "to_node_id": to_id,
            "relation_type": relation_type,
            "confidence": confidence,
            "source_refs": [],
        }
        for (from_type, from_id, relation_type, to_type, to_id, confidence) in sorted(edges)
    ]
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
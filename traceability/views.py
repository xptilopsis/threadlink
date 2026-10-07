"""追溯链只读视图（D4-R3；D12-R2 增 depth/direction 参数）。

``GET /trace/serial/<sn>/``：纯 DB、只读、无 LLM、无 AgentRun（R1 边界）。
多项目守卫：跨 Project 命中 >1 → HTTP 409（fail-loud；演示为单项目范围）。
查询参数（D12-R2 / GT-TRACE-006）：``depth``（0=全链，缺省）/ ``direction``（forward|backward，
缺省=无向）；非法或负值 → HTTP 400。
默认渲染 HTML；``?format=json`` 返回与链负载逐字段一致的 JSON。
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

from core.models import InventoryLot
from traceability.chain import VALID_DIRECTIONS, build_trace_chain, serial_not_found_payload


@login_required
def serial_trace(request, sn):
    depth_raw = request.GET.get("depth")
    direction = request.GET.get("direction") or None

    depth = 0
    if depth_raw not in (None, ""):
        try:
            depth = int(depth_raw)
        except (TypeError, ValueError):
            return HttpResponse(status=400)
        if depth < 0:
            return HttpResponse(status=400)
    if direction is not None and direction not in VALID_DIRECTIONS:
        return HttpResponse(status=400)

    lots = list(InventoryLot.objects.filter(serial_number=sn))
    if len(lots) == 0:
        payload = serial_not_found_payload(sn)
    elif len(lots) > 1:
        return HttpResponse(status=409)
    else:
        payload = build_trace_chain(
            lots[0].project_id, "inventory_lot", sn, depth=depth, direction=direction
        )

    if request.GET.get("format") == "json":
        return JsonResponse(payload)
    return render(request, "traceability/chain.html", {"payload": payload})

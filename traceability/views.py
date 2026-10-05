"""追溯链只读视图（D4-R3）。

``GET /trace/serial/<sn>/``：纯 DB、只读、无 LLM、无 AgentRun（R1 边界）。
多项目守卫：跨 Project 命中 >1 → HTTP 409（fail-loud；演示为单项目范围）。
默认渲染 HTML；``?format=json`` 返回与链负载逐字段一致的 JSON。
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

from core.models import InventoryLot
from traceability.chain import build_trace_chain, serial_not_found_payload


@login_required
def serial_trace(request, sn):
    lots = list(InventoryLot.objects.filter(serial_number=sn))
    if len(lots) == 0:
        payload = serial_not_found_payload(sn)
    elif len(lots) > 1:
        return HttpResponse(status=409)
    else:
        payload = build_trace_chain(lots[0].project_id, "inventory_lot", sn)

    if request.GET.get("format") == "json":
        return JsonResponse(payload)
    return render(request, "traceability/chain.html", {"payload": payload})

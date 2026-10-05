"""D5-R2 §5.1：Requirement Agent 契约端点 ``POST /agents/requirement/run/``。

请求 JSON（``interface_contract.md`` §4.1）：``project_id`` / ``document_id`` / ``prompt_id`` /
``prompt_version`` / ``model`` / ``temperature``。成功响应 ``{agent_run, output}``。``@login_required``。
"""

import json
import re
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from agents import llm
from agents.bom_selection import PromptMissingError, run_bom_selection_agent
from agents.models import AgentRun
from agents.requirement import RequirementAgentError, run_requirement_agent
from core.models import Document, Project
from core.selection import Criteria


def _serialize_run(run):
    return {
        "id": run.id,
        "agent_name": run.agent_name,
        "status": run.status,
        "prompt_id": run.prompt_id,
        "prompt_version": run.prompt_version,
        "model": run.model,
        "temperature": str(run.temperature),
        "input_hash": run.input_hash,
        "output_schema_valid": run.output_schema_valid,
        "reference_check_passed": run.reference_check_passed,
        "invalid_references": run.invalid_references,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


@login_required
@require_POST
def requirement_run_view(request):
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    project_id = payload.get("project_id")
    document_id = payload.get("document_id")
    if not project_id or not document_id:
        return JsonResponse({"error": "project_id 与 document_id 必填"}, status=400)

    project = Project.objects.filter(code=str(project_id)).first()
    if project is None and str(project_id).isdigit():
        project = Project.objects.filter(pk=int(project_id)).first()
    if project is None:
        return JsonResponse({"error": f"project 不存在：{project_id}"}, status=404)

    document = Document.objects.filter(project=project, doc_no=str(document_id)).first()
    if document is None and str(document_id).isdigit():
        document = Document.objects.filter(project=project, pk=int(document_id)).first()
    if document is None:
        return JsonResponse({"error": f"document 不存在：{document_id}"}, status=404)

    try:
        summary = run_requirement_agent(
            project,
            document,
            request.user,
            model=payload.get("model"),
            temperature=payload.get("temperature", 0),
        )
    except RequirementAgentError as exc:
        return JsonResponse({"error": str(exc)}, status=422)
    except llm.LLMError as exc:
        return JsonResponse({"error": str(exc), "error_type": exc.category}, status=502)

    body = {"output": summary.get("output"), "summary": summary}
    if summary.get("agent_run_id"):
        run = AgentRun.objects.filter(pk=summary["agent_run_id"]).first()
        if run is not None:
            body["agent_run"] = _serialize_run(run)
    return JsonResponse(body, status=200 if summary.get("ok") else 422)

def _dec(value, default):
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return default


def _criteria_from_constraints(constraints):
    """把契约 §4.2 的 ``constraints``（list[Param 形态]）转成引擎 ``Criteria``。"""

    criteria = Criteria()
    for item in constraints or []:
        name = item.get("name")
        if name == "input_voltage":
            criteria.voltage_min = _dec(item.get("value_min"), criteria.voltage_min)
            criteria.voltage_max = _dec(item.get("value_max"), criteria.voltage_max)
        elif name == "rated_current":
            criteria.current_min = _dec(item.get("value_num"), criteria.current_min)
        elif name == "operating_temp":
            criteria.temp_min = _dec(item.get("value_min"), criteria.temp_min)
            criteria.temp_max = _dec(item.get("value_max"), criteria.temp_max)
        elif name == "ip_rating":
            parsed = re.search(r"IP\s*(\d+)", str(item.get("value_text") or ""), re.IGNORECASE)
            if parsed:
                criteria.ip_min = int(parsed.group(1))
        elif name in ("bom_cost", "unit_cost", "cost_max"):
            criteria.cost_max = _dec(item.get("value_num"), criteria.cost_max)
    return criteria


@login_required
@require_POST
def bom_selection_run_view(request):
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    project_id = payload.get("project_id")
    if not project_id:
        return JsonResponse({"error": "project_id 必填"}, status=400)
    project = Project.objects.filter(code=str(project_id)).first()
    if project is None and str(project_id).isdigit():
        project = Project.objects.filter(pk=int(project_id)).first()
    if project is None:
        return JsonResponse({"error": f"project 不存在：{project_id}"}, status=404)

    criteria = _criteria_from_constraints(payload.get("constraints"))
    try:
        summary = run_bom_selection_agent(
            project,
            criteria,
            request.user,
            model=payload.get("model"),
            temperature=payload.get("temperature", 0.2),
        )
    except PromptMissingError as exc:
        return JsonResponse({"error": str(exc)}, status=422)
    except llm.LLMError as exc:
        return JsonResponse({"error": str(exc), "error_type": exc.category}, status=502)

    body = {"output": summary.get("output"), "summary": summary}
    if summary.get("agent_run_id"):
        run = AgentRun.objects.filter(pk=summary["agent_run_id"]).first()
        if run is not None:
            body["agent_run"] = _serialize_run(run)
    return JsonResponse(body, status=200 if summary.get("ok") else 422)

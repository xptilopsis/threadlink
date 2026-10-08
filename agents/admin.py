from django import forms
from django.contrib import admin, messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect
from django.template import RequestContext, Template
from django.urls import reverse

from agents.models import AgentRun


@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    """AgentRun 只读审计队列（D5-R2 §5.2 最小实现）。

    list = `agent_name/status/prompt_version/created_at`（+ id/model）+ 过滤；detail 全字段只读，
    并附 `output_summary`（卡片标题列表 / 错误负载摘要）。**确认 / 拒绝动作留 R3。**
    """

    list_display = (
        "id",
        "agent_name",
        "status",
        "prompt_version",
        "model",
        "created_at",
        "output_summary",
    )
    list_filter = ("agent_name", "status")
    search_fields = ("prompt_id", "prompt_version", "model")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields] + ["output_summary"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True

    @admin.display(description="输出摘要")
    def output_summary(self, obj):
        data = obj.output_json or {}
        if obj.status == "failed":
            return f"失败：{data.get('error_type', 'unknown')}"
        cards = data.get("cards") or []
        titles = [card.get("title", "") for card in cards if isinstance(card, dict)]
        return f"{len(cards)} 张卡片：" + "；".join(titles[:5])
    actions = ("approve_selected", "reject_selected")

    def _handle(self, request, queryset, action, verb):
        from agents.confirmation import ConfirmationError, approve, reject

        done = skipped = 0
        created = []
        for run in queryset:
            # 按 agent_name 派发（D6-R2 §3.1；bom_selection approve → D6-R3 服务）
            if run.agent_name == "bom_selection" and action == "approve":
                from agents.bom_selection import approve_bom_selection

                try:
                    result = approve_bom_selection(run, request.user)
                    done += 1
                    self.message_user(
                        request,
                        f"#{run.pk} 已批准：BOM {result['bom_no']}，"
                        f"{result['items']} 项，{result['links']} 条替代链接",
                    )
                except ConfirmationError as exc:
                    skipped += 1
                    self.message_user(request, f"#{run.pk} 跳过：{exc}", level=messages.WARNING)
                except Exception as exc:  # noqa: BLE001
                    skipped += 1
                    self.message_user(request, f"#{run.pk} 处置异常：{exc}", level=messages.ERROR)
                continue
            if run.agent_name == "traceability" and action == "approve":
                from agents.traceability import approve_traceability

                try:
                    approve_traceability(run, request.user)
                    done += 1
                    self.message_user(
                        request,
                        f"#{run.pk} 已确认：traceability 纯审计确认（无实体写入）",
                    )
                except ConfirmationError as exc:
                    skipped += 1
                    self.message_user(
                        request, f"#{run.pk} 跳过：{exc}", level=messages.WARNING
                    )
                except Exception as exc:  # noqa: BLE001
                    skipped += 1
                    self.message_user(
                        request, f"#{run.pk} 处置异常：{exc}", level=messages.ERROR
                    )
                continue
            if run.agent_name not in ("requirement", "bom_selection", "traceability"):
                skipped += 1  # 未知 agent_name → 跳过
                continue
            try:
                if action == "approve":
                    created.extend(approve(run, request.user))
                else:
                    reject(run, request.user)
                done += 1
            except ConfirmationError:
                skipped += 1
            except Exception as exc:  # noqa: BLE001
                skipped += 1
                self.message_user(request, f"#{run.pk} 处置异常：{exc}", level=messages.ERROR)
        if done:
            extra = f"，创建需求 {'、'.join(created)}" if created else ""
            self.message_user(request, f"已{verb} {done} 条{extra}")
        if skipped:
            self.message_user(request, f"{skipped} 条跳过", level=messages.WARNING)

    @admin.action(description="批准")
    def approve_selected(self, request, queryset):
        self._handle(request, queryset, "approve", "批准")

    @admin.action(description="拒绝")
    def reject_selected(self, request, queryset):
        self._handle(request, queryset, "reject", "拒绝")

# ---------------------------------------------------------------------------
# D13-R1：演示场景 2 的 criteria 单页表单（Admin 入口，最小实现）
# ---------------------------------------------------------------------------


class BomSelectionCriteriaForm(forms.Form):
    """BOM 选型 criteria 小额表单（演示场景 2 UI 入口）。

    字段对应 ``core.selection.Criteria``；``cost_max`` 留空即不启用（``None``）。
    """

    project = forms.CharField(label="项目代码", initial="DEMO-GW", max_length=64)
    voltage_min = forms.DecimalField(label="输入电压下限 V", initial=9)
    voltage_max = forms.DecimalField(label="输入电压上限 V", initial=36)
    current_min = forms.DecimalField(label="额定电流 ≥ A", initial=5)
    temp_min = forms.DecimalField(label="工作温度下限 °C", initial=-40)
    temp_max = forms.DecimalField(label="工作温度上限 °C", initial=85)
    ip_min = forms.IntegerField(label="防护等级 ≥ IP", initial=65)
    cost_max = forms.DecimalField(
        label="单料成本上限（留空不启用）", required=False
    )


_CRITERIA_TEMPLATE = Template(
    """<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>BOM 选型 criteria</title></head>
<body>
<h1>BOM 选型（criteria）</h1>
{% if error %}<p style="color:#b00">运行失败：{{ error }}</p>{% endif %}
<form method="post">{% csrf_token %}
{{ form.as_p }}
<button type="submit">运行选型</button>
</form>
</body>
</html>"""
)


@login_required
def bom_selection_criteria_view(request):
    """GET 渲染 criteria 表单；POST 调 ``run_bom_selection_agent`` → 重定向 AgentRun 详情。

    失败（project 不存在 / 引擎无候选 / LLM 异常）→ 同页回显错误消息，**不 500**。
    """

    from agents.bom_selection import run_bom_selection_agent
    from core.models import Project
    from core.selection import Criteria

    form = BomSelectionCriteriaForm(request.POST or None)
    error = None
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        project = Project.objects.filter(code=data["project"]).first()
        if project is None:
            error = f"project 不存在：{data['project']}"
        else:
            criteria = Criteria(
                voltage_min=data["voltage_min"],
                voltage_max=data["voltage_max"],
                current_min=data["current_min"],
                temp_min=data["temp_min"],
                temp_max=data["temp_max"],
                ip_min=data["ip_min"],
                cost_max=data["cost_max"],
            )
            try:
                summary = run_bom_selection_agent(project, criteria, request.user)
            except Exception as exc:  # noqa: BLE001 —— 以页面消息呈现，不 500
                error = str(exc)
            else:
                run_id = summary.get("agent_run_id")
                if run_id:
                    return HttpResponseRedirect(
                        reverse("admin:agents_agentrun_change", args=[run_id])
                    )
                error = f"未产生 AgentRun（reason={summary.get('reason', 'unknown')}）"
    context = RequestContext(
        request, {"form": form, "error": error, "title": "BOM 选型 criteria"}
    )
    return HttpResponse(_CRITERIA_TEMPLATE.render(context))

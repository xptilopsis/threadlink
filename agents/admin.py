import json
from typing import ClassVar

from django import forms
from django.contrib import admin, messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe

from agents.models import AgentRun
from core.admin import InlineActionsMixin

# D13 演示导航：admin 首页加「快捷入口」（免手敲地址）
admin.site.index_template = "admin/threadlink_index.html"


@admin.register(AgentRun)
class AgentRunAdmin(InlineActionsMixin, admin.ModelAdmin):
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
    change_list_template = "admin/agents/agentrun/change_list.html"
    change_form_template = "admin/agents/agentrun/change_form.html"

    # input_json / output_json 以「可读卡片」呈现（按 agent_name 分派），
    # 原始 JSON 收进折叠块兜底（不直接铺原始 JSON）。
    _HUMANIZED_FIELD_MAP: ClassVar[dict[str, str]] = {
        "input_json": "input_pretty",
        "output_json": "output_pretty",
    }
    _CARD_STYLE = (
        "border:1px solid var(--border-color,#ccc);border-radius:6px;"
        "padding:8px 10px;margin:6px 0;background:var(--darkened-bg,#f8f8f8);"
        "color:var(--body-fg,#333);line-height:1.5;"
    )
    _MUTED = "color:var(--body-quiet-color,#666);font-size:12px;"
    _TAG_STYLE = (
        "display:inline-block;border:1px solid var(--border-color,#ccc);"
        "border-radius:10px;padding:0 6px;margin:0 4px 4px 0;font-size:12px;"
    )

    @staticmethod
    def _esc(value):
        return escape("" if value is None else str(value))

    def _raw_json(self, value, label="Raw JSON"):
        try:
            text = json.dumps(value, indent=2, ensure_ascii=True, default=str)
        except (TypeError, ValueError):
            text = str(value)
        return (
            '<details style="margin-top:6px;"><summary style="cursor:pointer;'
            + self._MUTED
            + '">'
            + self._esc(label)
            + "</summary><pre style=\"white-space:pre-wrap;word-break:break-word;"
            "max-height:50vh;overflow:auto;margin:4px 0 0;font-size:12px;"
            "background:var(--body-bg,#fff);border:1px solid var(--border-color,#ccc);"
            "border-radius:4px;padding:8px;\">"
            + self._esc(text)
            + "</pre></details>"
        )

    def _refs_html(self, refs):
        if not refs:
            return ""
        items = []
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            txt = f"{ref.get('type', '?')}:{ref.get('id', '?')}"
            if ref.get("locator"):
                txt += f" ({ref['locator']})"
            items.append(f'<span style="{self._TAG_STYLE}">{self._esc(txt)}</span>')
        if not items:
            return ""
        return (
            f'<div style="margin-top:4px;"><span style="{self._MUTED}">Source </span>'
            + "".join(items)
            + "</div>"
        )

    def _params_html(self, params):
        if not params:
            return ""
        rows = []
        for p in params:
            if not isinstance(p, dict):
                continue
            op = p.get("operator") or "eq"
            if op == "range":
                val = f"{p.get('value_min')} ~ {p.get('value_max')}"
            elif op == "gte":
                val = f">= {p.get('value_num')}"
            elif op == "lte":
                val = f"<= {p.get('value_num')}"
            else:
                val = p.get("value_text")
                if val is None:
                    val = p.get("value_num")
            unit = f" {p['unit']}" if p.get("unit") else ""
            rows.append(
                f'<div style="margin:2px 0;">- '
                f'<b>{self._esc(p.get("name"))}</b>: {self._esc(val)}{self._esc(unit)}</div>'
            )
        if not rows:
            return ""
        return (
            f'<div style="margin-top:4px;"><span style="{self._MUTED}">Params</span>'
            + "".join(rows)
            + "</div>"
        )

    def _requirement_html(self, data):
        parts = []
        if data.get("summary"):
            parts.append(f'<div style="{self._MUTED}">{self._esc(data["summary"])}</div>')
        cards = data.get("cards") or data.get("requirement_cards") or []
        parts.append(
            f'<div style="margin:4px 0;"><b>Requirement cards: {len(cards)}</b></div>'
        )
        for i, card in enumerate(cards, 1):
            if not isinstance(card, dict):
                continue
            head = f'{i}. {self._esc(card.get("title"))}'
            if card.get("priority"):
                head += f' <span style="{self._TAG_STYLE}">{self._esc(card["priority"])}</span>'
            if card.get("confidence") is not None:
                head += (
                    f' <span style="{self._MUTED}">confidence '
                    f'{self._esc(card.get("confidence"))}</span>'
                )
            block = [f'<div style="{self._CARD_STYLE}"><b>{head}</b>']
            block.append(f'<div>{self._esc(card.get("content"))}</div>')
            block.append(self._params_html(card.get("params")))
            block.append(self._refs_html(card.get("source_refs")))
            block.append("</div>")
            parts.append("".join(block))
        return "".join(parts)

    def _bom_html(self, data):
        parts = []
        if data.get("summary"):
            parts.append(f'<div style="{self._MUTED}">{self._esc(data["summary"])}</div>')
        cands = data.get("candidates") or []
        head = f'<div style="margin:4px 0;"><b>Candidates: {len(cands)}</b>'
        if data.get("recommended_part_id"):
            head += (
                f' <span style="{self._TAG_STYLE}">recommended '
                f'{self._esc(data["recommended_part_id"])}</span>'
            )
        parts.append(head + "</div>")
        for i, c in enumerate(cands, 1):
            if not isinstance(c, dict):
                continue
            pn = c.get("part_number") or c.get("part_id") or "?"
            block = [
                (
                    f'<div style="{self._CARD_STYLE}"><b>{i}. {self._esc(pn)} '
                    f'{self._esc(c.get("name"))}</b>'
                )
            ]
            meta = []
            if c.get("score") is not None:
                meta.append(f'score {self._esc(c["score"])}')
            if c.get("unit_price") is not None:
                meta.append(
                    f'unit price {self._esc(c["unit_price"])} '
                    f'{self._esc(c.get("currency") or "")}'
                )
            if c.get("lead_time_days") is not None:
                meta.append(f'lead time {self._esc(c["lead_time_days"])} d')
            if c.get("lifecycle_status"):
                meta.append(f'lifecycle {self._esc(c["lifecycle_status"])}')
            if c.get("replaces_part_id"):
                meta.append(f'replaces {self._esc(c["replaces_part_id"])}')
            if meta:
                block.append(f'<div style="{self._MUTED}">' + " | ".join(meta) + "</div>")
            if c.get("rationale"):
                block.append(f'<div>{self._esc(c["rationale"])}</div>')
            block.append(self._refs_html(c.get("source_refs")))
            block.append("</div>")
            parts.append("".join(block))
        return "".join(parts)

    def _trace_html(self, data):
        nodes = data.get("nodes") or []
        edges = data.get("edges") or []
        missing = data.get("missing") or []
        parts = [f'<div style="{self._CARD_STYLE}">']
        parts.append(
            f'<b>root {self._esc(data.get("root"))}</b> | '
            f'found {"yes" if data.get("found") else "no"} | '
            f'complete {"yes" if data.get("complete") else "no"} | '
            f'nodes {len(nodes)} | edges {len(edges)}'
        )
        if data.get("summary"):
            parts.append(f'<div>{self._esc(data["summary"])}</div>')
        if missing:
            parts.append(
                f'<div style="{self._MUTED}">missing '
                f'{self._esc(", ".join(str(m) for m in missing))}</div>'
            )
        parts.append("</div>")
        return "".join(parts)

    def _failed_html(self, data):
        err = data.get("error_type") or data.get("error") or "unknown"
        detail = data.get("detail") or data.get("message") or ""
        html = f'<div style="{self._CARD_STYLE}"><b>Run failed</b> - {self._esc(err)}'
        if detail:
            html += f'<div style="{self._MUTED}">{self._esc(detail)}</div>'
        return html + "</div>"

    @admin.display(description="Output")
    def output_pretty(self, obj):
        data = obj.output_json
        if not isinstance(data, dict):
            return mark_safe(self._raw_json(data))
        if obj.status == "failed":
            body = self._failed_html(data)
        elif "cards" in data or "requirement_cards" in data:
            body = self._requirement_html(data)
        elif "candidates" in data:
            body = self._bom_html(data)
        elif "nodes" in data and "found" in data:
            body = self._trace_html(data)
        else:
            body = ""
        if body:
            return mark_safe(body)
        return mark_safe(self._raw_json(data))

    @admin.display(description="Input")
    def input_pretty(self, obj):
        data = obj.input_json
        if not isinstance(data, dict):
            return mark_safe(self._raw_json(data))
        parts = [f'<div style="{self._CARD_STYLE}">']
        meta = [
            f"{self._esc(key)}={self._esc(data.get(key))}"
            for key in ("prompt_id", "prompt_version", "model", "temperature", "max_tokens")
            if data.get(key) is not None
        ]
        if meta:
            parts.append("<div>" + " | ".join(meta) + "</div>")
        msgs = data.get("messages")
        if isinstance(msgs, list) and msgs:
            parts.append(f'<div style="{self._MUTED}">Messages: {len(msgs)}</div>')
            for m in msgs:
                if not isinstance(m, dict):
                    continue
                role = m.get("role", "?")
                content = m.get("content") or ""
                if role == "user":
                    shown = content if len(content) <= 2000 else content[:2000] + "..."
                    parts.append(
                        '<div><b>user</b></div><pre style="white-space:pre-wrap;'
                        "word-break:break-word;margin:2px 0;font-size:12px;"
                        "background:var(--body-bg,#fff);border:1px solid "
                        'var(--border-color,#ccc);border-radius:4px;padding:6px;">'
                        + self._esc(shown)
                        + "</pre>"
                    )
                else:
                    parts.append(
                        f'<details><summary style="cursor:pointer;{self._MUTED}">'
                        f'{self._esc(role)} ({len(content)} chars)</summary>'
                        '<pre style="white-space:pre-wrap;word-break:break-word;'
                        "max-height:40vh;overflow:auto;margin:2px 0;font-size:12px;"
                        "background:var(--body-bg,#fff);border:1px solid "
                        'var(--border-color,#ccc);border-radius:4px;padding:6px;">'
                        + self._esc(content)
                        + "</pre></details>"
                    )
        parts.append("</div>")
        return mark_safe("".join(parts))

    def _detail_field_names(self):
        return [
            self._HUMANIZED_FIELD_MAP.get(field.name, field.name)
            for field in self.model._meta.fields
        ] + ["output_summary"]

    def get_fields(self, request, obj=None):
        return self._detail_field_names()

    def get_readonly_fields(self, request, obj=None):
        return self._detail_field_names()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True

    @admin.display(description="Output summary")
    def output_summary(self, obj):
        data = obj.output_json or {}
        if obj.status == "failed":
            return f"Failed: {data.get('error_type', 'unknown')}"
        cards = data.get("cards") or []
        titles = [card.get("title", "") for card in cards if isinstance(card, dict)]
        return f"{len(cards)} cards: " + "; ".join(titles[:5])

    actions = ("approve_selected", "reject_selected")

    def inline_actions(self, obj):
        if obj.status != "needs_review":
            return []
        return [
            ("Approve", "approve_selected", "run-approve", False),
            ("Reject", "reject_selected", "run-reject", True),
        ]

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
                        f"#{run.pk} approved: BOM {result['bom_no']}, "
                        f"{result['items']} items, {result['links']} substitute links",
                    )
                except ConfirmationError as exc:
                    skipped += 1
                    self.message_user(
                        request, f"#{run.pk} skipped: {exc}", level=messages.WARNING
                    )
                except Exception as exc:  # noqa: BLE001
                    skipped += 1
                    self.message_user(
                        request, f"#{run.pk} error: {exc}", level=messages.ERROR
                    )
                continue
            if run.agent_name == "traceability" and action == "approve":
                from agents.traceability import approve_traceability

                try:
                    approve_traceability(run, request.user)
                    done += 1
                    self.message_user(
                        request,
                        f"#{run.pk} confirmed: traceability audit-only (no entity write)",
                    )
                except ConfirmationError as exc:
                    skipped += 1
                    self.message_user(
                        request, f"#{run.pk} skipped: {exc}", level=messages.WARNING
                    )
                except Exception as exc:  # noqa: BLE001
                    skipped += 1
                    self.message_user(
                        request, f"#{run.pk} error: {exc}", level=messages.ERROR
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
                self.message_user(
                    request, f"#{run.pk} error: {exc}", level=messages.ERROR
                )
        if done:
            extra = f", created requirements {'; '.join(created)}" if created else ""
            self.message_user(request, f"{verb} {done}{extra}")
        if skipped:
            self.message_user(request, f"{skipped} skipped", level=messages.WARNING)

    @admin.action(description="Approve")
    def approve_selected(self, request, queryset):
        self._handle(request, queryset, "approve", "Approved")

    @admin.action(description="Reject")
    def reject_selected(self, request, queryset):
        self._handle(request, queryset, "reject", "Rejected")

    # ------------------------------------------------------------------ D13 演示动线
    # AgentRun 页「待处理文档」（黄高亮 + 一键需求提取 + 成功后跳转）
    # + 详情页「批准」入口与「批准成功」状态栏。

    PENDING_WINDOW_MINUTES = 10
    BOM_AGENT_HOME = "http://127.0.0.1:8000/agents/bom-selection/form/"

    def _requirement_run_for_doc(self, doc):
        """约定关联（不改 models）：doc_no 出现在 requirement run 的 input/output 即视为已提取。"""
        doc_no = doc.doc_no
        for run in AgentRun.objects.filter(agent_name="requirement").order_by("-id"):
            blob = f"{run.input_json or ''}{run.output_json or ''}"
            if doc_no in blob:
                return run
        return None


    def get_urls(self):
        extra = [
            path(
                "pending-document/<int:doc_id>/extract/",
                self.admin_site.admin_view(self.extract_requirement_view),
                name="agents_agentrun_extract_requirement",
            ),
            path(
                "<int:pk>/approve-now/",
                self.admin_site.admin_view(self.approve_now_view),
                name="agents_agentrun_approve_now",
            ),
        ]
        return extra + super().get_urls()

    def extract_requirement_view(self, request, doc_id):
        """一键需求提取（未批准状态下可用）→ 成功后跳该 AgentRun 详情页。"""
        from agents.requirement import run_requirement_agent
        from core.models import Document

        doc = Document.objects.filter(pk=doc_id).select_related("project").first()
        if doc is None:
            self.message_user(request, "Document not found", level=messages.ERROR)
            return HttpResponseRedirect(reverse("admin:agents_agentrun_changelist"))
        try:
            summary = run_requirement_agent(doc.project, doc, request.user)
        except Exception as exc:  # noqa: BLE001
            self.message_user(
                request, f"Requirement extraction failed: {exc}", level=messages.ERROR
            )
            return HttpResponseRedirect(reverse("admin:agents_agentrun_changelist"))
        run_id = summary.get("agent_run_id")
        if run_id:
            self.message_user(
                request,
                f"{doc.doc_no} extracted: {summary.get('cards')} cards pending review",
                level=messages.SUCCESS,
            )
            return HttpResponseRedirect(
                reverse("admin:agents_agentrun_change", args=[run_id])
            )
        self.message_user(request, "No AgentRun produced", level=messages.WARNING)
        return HttpResponseRedirect(reverse("admin:agents_agentrun_changelist"))

    def approve_now_view(self, request, pk):
        """详情页「批准」入口：复用批量派发逻辑后回到详情页。"""
        run = AgentRun.objects.filter(pk=pk).first()
        if run is None:
            self.message_user(request, "run not found", level=messages.ERROR)
            return HttpResponseRedirect(reverse("admin:agents_agentrun_changelist"))
        self._handle(request, AgentRun.objects.filter(pk=pk), "approve", "Approved")
        return HttpResponseRedirect(reverse("admin:agents_agentrun_change", args=[pk]))

    def changelist_view(self, request, extra_context=None):
        from datetime import timedelta

        from django.utils import timezone as dj_timezone

        from core.models import Document

        extra_context = extra_context or {}
        cutoff = dj_timezone.now() - timedelta(minutes=self.PENDING_WINDOW_MINUTES)
        recent = (
            Document.objects.filter(created_at__gte=cutoff)
            .select_related("project")
            .order_by("-created_at")
        )
        items = []
        for doc in recent:
            run = self._requirement_run_for_doc(doc)
            items.append(
                {
                    "doc": doc,
                    "run_id": run.pk if run else None,
                    "extract_url": reverse(
                        "admin:agents_agentrun_extract_requirement", args=[doc.pk]
                    ),
                    "jump_url": (
                        reverse("admin:agents_agentrun_change", args=[run.pk])
                        if run
                        else None
                    ),
                }
            )
        extra_context["pending_documents"] = items
        extra_context["bom_agent_home"] = self.BOM_AGENT_HOME
        return super().changelist_view(request, extra_context=extra_context)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["bom_agent_home"] = self.BOM_AGENT_HOME
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

# ---------------------------------------------------------------------------
# D13-R1：演示场景 2 的 criteria 单页表单（Admin 入口，最小实现）
# ---------------------------------------------------------------------------


class BomSelectionCriteriaForm(forms.Form):
    """BOM 选型 criteria 小额表单（演示场景 2 UI 入口）。

    字段对应 ``core.selection.Criteria``；``cost_max`` 留空即不启用（``None``）。
    """

    project = forms.CharField(label="Project code", initial="DEMO-GW", max_length=64)
    voltage_min = forms.DecimalField(label="Voltage min (V)", initial=9)
    voltage_max = forms.DecimalField(label="Voltage max (V)", initial=36)
    current_min = forms.DecimalField(label="Current min (A)", initial=5)
    temp_min = forms.DecimalField(label="Temp min (C)", initial=-40)
    temp_max = forms.DecimalField(label="Temp max (C)", initial=85)
    ip_min = forms.IntegerField(label="IP rating min", initial=65)
    cost_max = forms.DecimalField(
        label="Unit cost max (leave blank to disable)", required=False
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
            error = f"project not found: {data['project']}"
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
                error = (
                    f"No AgentRun produced (reason={summary.get('reason', 'unknown')})"
                )
    context = admin.site.each_context(request)
    context.update({"title": "BOM selection criteria", "form": form, "error": error})
    return render(request, "admin/bom_selection_form.html", context)

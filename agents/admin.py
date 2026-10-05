from django.contrib import admin, messages

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
            if run.agent_name not in ("requirement", "bom_selection"):
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

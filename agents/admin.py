from django.contrib import admin

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

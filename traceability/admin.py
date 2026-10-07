"""TraceLink Admin（D4-R1）。

- 端点字段的 choices 由 ``TraceLink`` 模型提供（D2 已从 ``schemas.agent_outputs``
  导入），**本模块不复制任何枚举**。
- 保存前调用 ``resolve_entity`` 校验 from/to 双方，失败 → 表单错误（文案含
  entity_type / 业务编号 / 原因）。
- ``created_by`` 留空时自动取当前用户；``confirmed_by``/``confirmed_at`` 允许人工填
  （四值绑定规则本轮不强制，D7+ 处理）。
"""

from django import forms
from django.contrib import admin

from core.admin import RoleWritePermissionMixin
from traceability.models import TraceLink
from traceability.services import TraceReferenceError, resolve_entity


class TraceLinkAdminForm(forms.ModelForm):
    class Meta:
        model = TraceLink
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        project = cleaned.get("project")
        for side in ("from", "to"):
            entity_type = cleaned.get(f"{side}_type")
            business_no = cleaned.get(f"{side}_id")
            if project and entity_type and business_no:
                try:
                    resolve_entity(project.pk, entity_type, business_no)
                except TraceReferenceError as exc:
                    self.add_error(f"{side}_id", str(exc))
        return cleaned


@admin.register(TraceLink)
class TraceLinkAdmin(RoleWritePermissionMixin, admin.ModelAdmin):
    form = TraceLinkAdminForm

    list_display = (
        "from_type",
        "from_id",
        "to_type",
        "to_id",
        "relation_type",
        "source",
        "confirmed_by",
        "created_at",
    )
    list_filter = ("relation_type", "from_type", "to_type", "source")
    search_fields = ("from_id", "to_id")
    date_hierarchy = "created_at"

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

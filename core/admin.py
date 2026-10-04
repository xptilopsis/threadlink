from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from core.models import (
    Part,
    PartParam,
    Project,
    Requirement,
    RequirementParam,
    Supplier,
    SupplierPart,
    TestCase,
    TestRun,
    User,
)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "status", "created_at")
    search_fields = ("code", "name")
    list_filter = ("status",)
    date_hierarchy = "created_at"


class PartParamInline(admin.TabularInline):
    model = PartParam
    extra = 0


@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = (
        "part_number",
        "name",
        "category",
        "lifecycle_status",
        "supplier_count",
    )
    search_fields = ("part_number", "name", "manufacturer", "mpn")
    list_filter = ("lifecycle_status", "category")
    inlines = [PartParamInline]

    @admin.display(description="供应商数")
    def supplier_count(self, obj):
        return obj.supplier_parts.count()


class SupplierPartInline(admin.TabularInline):
    model = SupplierPart
    extra = 0


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "status", "contact_name")
    search_fields = ("code", "name", "contact_name")
    list_filter = ("status",)
    inlines = [SupplierPartInline]


try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "role", "is_staff", "is_active")
    list_filter = BaseUserAdmin.list_filter + ("role",)

    def get_fieldsets(self, request, obj=None):
        return super().get_fieldsets(request, obj) + (
            ("ThreadLink", {"fields": ("role",)}),
        )

# ---------------------------------------------------------------------------
# D3-R1：Requirement / TestCase / TestRun
# ---------------------------------------------------------------------------


class RequirementParamInline(admin.TabularInline):
    model = RequirementParam
    extra = 0
    fields = (
        "name",
        "operator",
        "value_text",
        "value_num",
        "value_min",
        "value_max",
        "unit",
        "is_mandatory",
    )


@admin.register(Requirement)
class RequirementAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "title",
        "source_type",
        "priority",
        "status",
        "confirmed_by",
        "created_at",
    )
    list_filter = ("source_type", "priority", "status")
    search_fields = ("code", "title")
    date_hierarchy = "created_at"
    inlines = [RequirementParamInline]


class TestRunInline(admin.TabularInline):
    """TestCase 详情页的只读 TestRun 列表（禁增删、字段只读）。"""

    model = TestRun
    extra = 0
    can_delete = False
    fields = ("run_no", "sample_serial", "result", "tested_at", "tester")
    readonly_fields = ("run_no", "sample_serial", "result", "tested_at", "tester")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(TestCase)
class TestCaseAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "test_type", "status")
    list_filter = ("test_type", "status")
    search_fields = ("code", "name")
    date_hierarchy = "created_at"
    inlines = [TestRunInline]


@admin.register(TestRun)
class TestRunAdmin(admin.ModelAdmin):
    list_display = ("run_no", "test_case", "sample_serial", "result", "tested_at", "tester")
    list_filter = ("result", "tested_at")
    search_fields = ("run_no", "sample_serial")

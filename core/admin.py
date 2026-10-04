from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from core.models import Part, PartParam, Project, Supplier, SupplierPart, User


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

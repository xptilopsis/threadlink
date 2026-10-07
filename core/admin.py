import hashlib
import time
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.utils.text import get_valid_filename

from config.settings import resolve_doc_path
from core.models import (
    Bom,
    BomItem,
    Document,
    ECN,
    ECNImpact,
    GitCommit,
    GitRepo,
    InventoryLot,
    Part,
    PartParam,
    Project,
    PurchaseOrder,
    Requirement,
    RequirementParam,
    Supplier,
    SupplierPart,
    TestCase,
    TestRun,
    User,
    WorkOrder,
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


# ---------------------------------------------------------------------------
# D3-R2：Bom 只读树视图 / BomItem / InventoryLot
# ---------------------------------------------------------------------------

BOM_TREE_INDENT_UNIT = "    "
BOM_TREE_CYCLE_MARKER = "[CYCLE: {item_no}]"
BOM_TREE_MAX_DEPTH = 50


def build_bom_tree(items):
    """把同一 BOM 的 BomItem 列表整理为 ``[(depth, item, state)]``。

    规则：父先于子；``visited`` 集合防环（重复节点标 ``state="cycle"``）；
    深度上限 ``BOM_TREE_MAX_DEPTH``。纯函数，只用传入的 ``items``。
    未被根到达的节点（孤儿 / 环起点）从 ``depth=0`` 起补渲染。
    """

    children = {}
    for item in items:
        children.setdefault(item.parent_item_id, []).append(item)

    rows = []
    visited = set()

    def walk(parent_pk, depth):
        if depth > BOM_TREE_MAX_DEPTH:
            return
        for item in children.get(parent_pk, []):
            if item.pk in visited:
                rows.append((depth, item, "cycle"))
                continue
            visited.add(item.pk)
            rows.append((depth, item, "ok"))
            walk(item.pk, depth + 1)

    walk(None, 0)
    for item in items:
        if item.pk in visited:
            continue
        visited.add(item.pk)
        rows.append((0, item, "ok"))
        walk(item.pk, 1)
    return rows


def render_bom_tree(rows):
    """把 ``build_bom_tree`` 结果渲染为 ``<pre>`` 只读文本（缩进 + 环标记）。"""

    lines = []
    for depth, item, state in rows:
        indent = BOM_TREE_INDENT_UNIT * depth
        if state == "cycle":
            lines.append(
                f"{indent}{BOM_TREE_CYCLE_MARKER.format(item_no=item.item_no)} "
                f"{item.item_no}"
            )
            continue
        parent = item.parent_item.item_no if item.parent_item_id else "-"
        part = item.part.part_number if item.part_id else "-"
        lines.append(
            f"{indent}{item.item_no} | {part} | x{item.quantity} | parent={parent}"
        )
    return format_html("<pre>{}</pre>", "\n".join(lines))


@admin.register(Bom)
class BomAdmin(admin.ModelAdmin):
    list_display = ("bom_no", "name", "version", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("bom_no", "name")
    readonly_fields = ("bom_tree",)

    @admin.display(description="BOM 树（只读）")
    def bom_tree(self, obj):
        if obj is None:
            return "-"
        items = list(obj.items.select_related("part", "parent_item").order_by("id"))
        return render_bom_tree(build_bom_tree(items))


@admin.register(BomItem)
class BomItemAdmin(admin.ModelAdmin):
    list_display = ("item_no", "bom", "parent_item", "part", "quantity", "unit", "substitute_group")
    list_filter = ("bom", "part")
    search_fields = ("item_no", "part__part_number")


@admin.register(InventoryLot)
class InventoryLotAdmin(admin.ModelAdmin):
    list_display = (
        "serial_number",
        "part",
        "quantity",
        "status",
        "location",
        "received_at",
        "sourced_po",
    )
    list_filter = ("status",)
    search_fields = ("serial_number", "part__part_number")

    @admin.display(description="来源采购单")
    def sourced_po(self, obj):
        from traceability.models import TraceLink

        targets = TraceLink.objects.filter(
            project=obj.project,
            from_type="inventory_lot",
            from_id=obj.serial_number,
            relation_type="sourced_from",
        ).values_list("to_id", flat=True)
        return ", ".join(targets) or "-"

# ---------------------------------------------------------------------------
# D3-R3：PurchaseOrder / WorkOrder
# ---------------------------------------------------------------------------


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = (
        "po_number",
        "supplier",
        "status",
        "order_date",
        "expected_date",
        "total_amount",
        "currency",
    )
    list_filter = ("status", "supplier")
    search_fields = ("po_number",)
    date_hierarchy = "order_date"


@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    list_display = ("code", "bom", "quantity", "status", "due_date")
    list_filter = ("status",)
    search_fields = ("code",)
    readonly_fields = ("kitting_panel",)

    @admin.display(description="齐套摘要（只读，D11-R1）")
    def kitting_panel(self, obj):
        from core.kitting import analyze_kitting

        if obj is None or obj.pk is None:
            return "（保存后方可计算）"
        try:
            result = analyze_kitting(obj)
        except Exception as exc:  # noqa: BLE001 —— 面板不得 500
            return f"计算失败：{exc}"
        if result["ready"]:
            return "齐套：全部满足"
        details = "、".join(
            f"{s['part_id']}（缺 {s['shortage_qty']}）" for s in result["shortages"]
        )
        return f"缺料 {len(result['shortages'])} 项：{details}"


# ---------------------------------------------------------------------------
# D3-R3：ECN / ECNImpact
# ---------------------------------------------------------------------------


class ECNImpactInline(admin.TabularInline):
    model = ECNImpact
    extra = 0
    fields = ("affected_type", "affected_id", "impact_type", "description")


@admin.register(ECN)
class ECNAdmin(admin.ModelAdmin):
    list_display = ("ecn_number", "title", "status", "effective_date")
    list_filter = ("status",)
    search_fields = ("ecn_number", "title")
    inlines = [ECNImpactInline]


@admin.register(ECNImpact)
class ECNImpactAdmin(admin.ModelAdmin):
    list_display = ("ecn", "affected_type", "affected_id", "impact_type")
    list_filter = ("affected_type", "impact_type")
    search_fields = ("ecn__ecn_number", "affected_id")

# ---------------------------------------------------------------------------
# D4-R2：Document / GitRepo / GitCommit 只读 Admin
# ---------------------------------------------------------------------------


class ReadOnlyModelAdmin(admin.ModelAdmin):
    """列表 / 详情可见，写入路径全关（add/change/delete → False）。"""

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True


class DocumentAdminForm(forms.ModelForm):
    """Document 入库表单（D5-R2 §2）：文件为**表单级上传字段**，非模型字段。"""

    upload = forms.FileField(required=True, label="文件")

    class Meta:
        model = Document
        fields = ("project", "title", "doc_type", "source_path", "uploaded_by", "upload")

    def clean_upload(self):
        upload = self.cleaned_data["upload"]
        if upload.size == 0:
            raise forms.ValidationError("上传文件为空")
        return upload


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """D5-R2 §2：文档**入库**开放（add），**创建后不可改**（change/delete → False）。

    - 上传文件写 ``documents/uploads/<timestamp>-<safe_name>``；
    - ``file_path`` 为 BASE_DIR 相对路径、``checksum`` 为真实 SHA-256、``size_bytes`` 实际大小；
    - ``is_readonly=True``（字典 §19「恒为 true」；语义=创建后内容不可变）；
    - GitRepo / GitCommit 维持全只读（`ReadOnlyModelAdmin`）。
    """

    form = DocumentAdminForm
    list_display = ("doc_no", "title", "doc_type", "is_readonly", "created_at")
    list_filter = ("doc_type", "is_readonly")
    search_fields = ("doc_no", "title")

    GENERATED_FIELDS = (
        "doc_no",
        "file_path",
        "checksum",
        "size_bytes",
        "mime_type",
        "is_readonly",
        "created_at",
    )

    def get_readonly_fields(self, request, obj=None):
        if obj is not None:
            return [field.name for field in self.model._meta.fields]
        return list(self.GENERATED_FIELDS)

    def has_add_permission(self, request):
        return True

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True

    def save_model(self, request, obj, form, change):
        upload = form.cleaned_data.get("upload")
        if upload:
            safe_name = get_valid_filename(Path(upload.name).name)
            relative = f"documents/uploads/{int(time.time())}-{safe_name}"
            destination = resolve_doc_path(relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = upload.read()
            destination.write_bytes(data)
            obj.file_path = relative
            obj.checksum = hashlib.sha256(data).hexdigest()
            obj.size_bytes = len(data)
            obj.is_readonly = True
            if not obj.mime_type:
                obj.mime_type = getattr(upload, "content_type", "") or ""
        super().save_model(request, obj, form, change)

    actions = ("run_requirement_agent_action",)

    @admin.action(description="运行 Requirement Agent（生成需求卡）")
    def run_requirement_agent_action(self, request, queryset):
        from agents.requirement import run_requirement_agent

        for document in queryset:
            try:
                summary = run_requirement_agent(document.project, document, request.user)
            except Exception as exc:  # noqa: BLE001
                self.message_user(
                    request, f"{document.doc_no}：运行失败——{exc}", level=messages.ERROR
                )
                continue
            if summary.get("ok"):
                self.message_user(
                    request, f"{document.doc_no}：{summary['cards']} 张卡片进入待确认"
                )
            else:
                self.message_user(
                    request,
                    f"{document.doc_no}：引用核验失败（{len(summary.get('invalid_references', []))} 条）",
                    level=messages.WARNING,
                )


@admin.register(GitRepo)
class GitRepoAdmin(ReadOnlyModelAdmin):
    list_display = ("name", "local_path", "default_branch", "is_readonly")
    search_fields = ("name", "local_path")


@admin.register(GitCommit)
class GitCommitAdmin(ReadOnlyModelAdmin):
    list_display = ("sha", "repo", "author_name", "committed_at", "message")
    list_filter = ("repo",)
    search_fields = ("sha", "author_name", "message")

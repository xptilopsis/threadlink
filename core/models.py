from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone

from core.numbering import NumberedModel
from schemas.agent_outputs import (
    EntityType,
    LifecycleStatus,
    ParamOperator,
    Priority,
    SourceType,
)


def enum_choices(enum_cls):
    """把 ``schemas.agent_outputs`` 的 ``str`` 枚举转成 Django choices。"""

    return [(member.value, member.value) for member in enum_cls]


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, username, email, password, **extra_fields):
        if not username:
            raise ValueError("The given username must be set")
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ENGINEER)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        ENGINEER = "engineer", "Engineer"
        PROCUREMENT = "procurement", "Procurement"
        TEST = "test", "Test"
        QUALITY = "quality", "Quality"

    role = models.CharField(
        max_length=16,
        choices=Role.choices,
        default=Role.ENGINEER,
    )

    objects = UserManager()


# ---------------------------------------------------------------------------
# 枚举（字典 §1–§22 定义、schemas 未覆盖的部分）
# ---------------------------------------------------------------------------


class ProjectStatus(models.TextChoices):
    ACTIVE = "active", "active"
    ARCHIVED = "archived", "archived"


class SupplierStatus(models.TextChoices):
    ACTIVE = "active", "active"
    INACTIVE = "inactive", "inactive"


class RequirementStatus(models.TextChoices):
    DRAFT = "draft", "draft"
    PENDING_CONFIRMATION = "pending_confirmation", "pending_confirmation"
    CONFIRMED = "confirmed", "confirmed"
    REJECTED = "rejected", "rejected"
    IMPLEMENTED = "implemented", "implemented"


class BomStatus(models.TextChoices):
    DRAFT = "draft", "draft"
    RELEASED = "released", "released"
    OBSOLETE = "obsolete", "obsolete"


class SerialType(models.TextChoices):
    LOT = "lot", "lot"
    SERIAL = "serial", "serial"


class InventoryLotStatus(models.TextChoices):
    AVAILABLE = "available", "available"
    ALLOCATED = "allocated", "allocated"
    CONSUMED = "consumed", "consumed"
    SCRAPPED = "scrapped", "scrapped"


class WorkOrderStatus(models.TextChoices):
    PLANNED = "planned", "planned"
    IN_PROGRESS = "in_progress", "in_progress"
    COMPLETED = "completed", "completed"
    CANCELLED = "cancelled", "cancelled"


class PurchaseOrderStatus(models.TextChoices):
    DRAFT = "draft", "draft"
    OPEN = "open", "open"
    PARTIAL = "partial", "partial"
    RECEIVED = "received", "received"
    CLOSED = "closed", "closed"
    CANCELLED = "cancelled", "cancelled"


class TestType(models.TextChoices):
    ELECTRICAL = "electrical", "electrical"
    THERMAL = "thermal", "thermal"
    EMC = "emc", "emc"
    ENVIRONMENTAL = "environmental", "environmental"
    FUNCTIONAL = "functional", "functional"


class TestCaseStatus(models.TextChoices):
    ACTIVE = "active", "active"
    DEPRECATED = "deprecated", "deprecated"


class TestRunResult(models.TextChoices):
    PASS = "pass", "pass"
    FAIL = "fail", "fail"
    BLOCKED = "blocked", "blocked"
    SKIPPED = "skipped", "skipped"


class ChangeType(models.TextChoices):
    DESIGN = "design", "design"
    MATERIAL = "material", "material"
    PROCESS = "process", "process"
    DOCUMENTATION = "documentation", "documentation"


class ECNStatus(models.TextChoices):
    DRAFT = "draft", "draft"
    REVIEWING = "reviewing", "reviewing"
    APPROVED = "approved", "approved"
    REJECTED = "rejected", "rejected"
    IMPLEMENTED = "implemented", "implemented"


class ImpactType(models.TextChoices):
    AFFECTED = "affected", "affected"
    BLOCKED = "blocked", "blocked"
    REPLACE_REQUIRED = "replace_required", "replace_required"


class DocumentType(models.TextChoices):
    DRAWING = "drawing", "drawing"
    PRD = "prd", "prd"
    SOR = "sor", "sor"
    EMAIL = "email", "email"
    TEST_REPORT = "test_report", "test_report"
    OTHER = "other", "other"


class PartLifecycleStatus(models.TextChoices):
    """Part 物料级生命周期（字典 §3 ∪ `rules/bom_scoring.v1.json` / ADR-0005 消费值）。

    物料级须覆盖规则消费的 `obsolete` / `discontinued`（硬过滤排除），故在
    `schemas.LifecycleStatus` 四值基础上补 `discontinued`；渠道级 `SupplierPart`
    仍用四值 `LifecycleStatus`，二者拆分、互不替代。
    """

    ACTIVE = "active", "active"
    NRND = "nrnd", "nrnd"
    EOL = "eol", "eol"
    OBSOLETE = "obsolete", "obsolete"
    DISCONTINUED = "discontinued", "discontinued"


# ---------------------------------------------------------------------------
# §2 Project
# ---------------------------------------------------------------------------


class Project(models.Model):
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=16, choices=ProjectStatus.choices, default=ProjectStatus.ACTIVE
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_projects",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.code} {self.name}"


# ---------------------------------------------------------------------------
# §3 Part / §4 PartParam
# ---------------------------------------------------------------------------


class Part(NumberedModel):
    number_field = "part_number"
    number_prefix = "PART-"

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="parts"
    )
    part_number = models.CharField(max_length=100)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=64, blank=True)
    manufacturer = models.CharField(max_length=200, blank=True)
    mpn = models.CharField(max_length=200, blank=True)
    lifecycle_status = models.CharField(
        max_length=16,
        choices=PartLifecycleStatus.choices,
        default=PartLifecycleStatus.ACTIVE,
    )
    unit = models.CharField(max_length=16, blank=True)
    is_critical = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "part_number"], name="uq_part_project_number"
            ),
        ]
        indexes = [
            models.Index(
                fields=["project", "lifecycle_status"], name="ix_part_project_lifecycle"
            ),
        ]

    def __str__(self):
        return f"{self.part_number} {self.name}"


class PartParam(models.Model):
    part = models.ForeignKey(
        Part, on_delete=models.CASCADE, related_name="params"
    )
    name = models.CharField(max_length=64)
    value_text = models.CharField(max_length=255, blank=True)
    value_num = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True
    )
    value_min = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True
    )
    value_max = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True
    )
    unit = models.CharField(max_length=16, blank=True)
    is_key = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.part_id}:{self.name}"


# ---------------------------------------------------------------------------
# §5 Supplier / §6 SupplierPart
# ---------------------------------------------------------------------------


class Supplier(NumberedModel):
    number_field = "code"
    number_prefix = "SUP-"

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="suppliers"
    )
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=100, blank=True)
    email = models.CharField(max_length=254, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    status = models.CharField(
        max_length=16, choices=SupplierStatus.choices, default=SupplierStatus.ACTIVE
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "code"], name="uq_supplier_project_code"
            ),
        ]

    def __str__(self):
        return f"{self.code} {self.name}"


class SupplierPart(models.Model):
    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name="supplier_parts"
    )
    part = models.ForeignKey(
        Part, on_delete=models.CASCADE, related_name="supplier_parts"
    )
    supplier_part_number = models.CharField(max_length=100, blank=True)
    unit_price = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True
    )
    currency = models.CharField(max_length=8, default="CNY")
    lead_time_days = models.IntegerField(null=True, blank=True)
    moq = models.IntegerField(null=True, blank=True)
    is_preferred = models.BooleanField(default=False)
    lifecycle_status = models.CharField(
        max_length=16,
        choices=enum_choices(LifecycleStatus),
        default=LifecycleStatus.ACTIVE.value,
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["supplier", "part"], name="uq_supplierpart_supplier_part"
            ),
        ]

    def __str__(self):
        return f"{self.supplier_id}-{self.part_id}"


# ---------------------------------------------------------------------------
# §7 Requirement / §8 RequirementParam
# ---------------------------------------------------------------------------


class Requirement(NumberedModel):
    number_field = "code"
    number_prefix = "REQ-"

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="requirements"
    )
    code = models.CharField(max_length=64)
    title = models.CharField(max_length=300)
    content = models.TextField(blank=True)
    source_type = models.CharField(
        max_length=16, choices=enum_choices(SourceType), default=SourceType.MANUAL.value
    )
    source_ref = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=24,
        choices=RequirementStatus.choices,
        default=RequirementStatus.DRAFT,
    )
    priority = models.CharField(
        max_length=8, choices=enum_choices(Priority), null=True, blank=True
    )
    confidence = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True
    )
    agent_run = models.ForeignKey(
        "agents.AgentRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requirements",
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_requirements",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "code"], name="uq_requirement_project_code"
            ),
        ]

    def __str__(self):
        return f"{self.code} {self.title}"


class RequirementParam(models.Model):
    requirement = models.ForeignKey(
        Requirement, on_delete=models.CASCADE, related_name="params"
    )
    name = models.CharField(max_length=64)
    operator = models.CharField(
        max_length=8, choices=enum_choices(ParamOperator), default=ParamOperator.EQ.value
    )
    value_text = models.CharField(max_length=255, blank=True)
    value_num = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True
    )
    value_min = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True
    )
    value_max = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True
    )
    unit = models.CharField(max_length=16, blank=True)
    is_mandatory = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.requirement_id}:{self.name}"


# ---------------------------------------------------------------------------
# §9 Bom / §10 BomItem
# ---------------------------------------------------------------------------


class Bom(NumberedModel):
    number_field = "bom_no"
    number_prefix = "BOM-"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="boms")
    bom_no = models.CharField(max_length=64)
    name = models.CharField(max_length=200)
    version = models.CharField(max_length=32)
    status = models.CharField(
        max_length=16, choices=BomStatus.choices, default=BomStatus.DRAFT
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_boms",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "bom_no"], name="uq_bom_project_bom_no"
            ),
            models.UniqueConstraint(
                fields=["project", "version"], name="uq_bom_project_version"
            ),
        ]

    def __str__(self):
        return f"{self.bom_no} {self.name}"


class BomItem(NumberedModel):
    number_field = "item_no"
    number_prefix = "BI-"

    bom = models.ForeignKey(Bom, on_delete=models.CASCADE, related_name="items")
    item_no = models.CharField(max_length=64)
    parent_item = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    part = models.ForeignKey(
        Part, on_delete=models.PROTECT, related_name="bom_items"
    )
    quantity = models.DecimalField(max_digits=18, decimal_places=4, default=1)
    unit = models.CharField(max_length=16, blank=True)
    ref_des = models.CharField(max_length=255, blank=True)
    position = models.CharField(max_length=64, blank=True)
    is_critical = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["bom", "item_no"], name="uq_bomitem_bom_item_no"
            ),
        ]

    def number_scope_project(self):
        return self.bom.project if self.bom_id else None

    def number_scope_filter(self, project) -> dict:
        return {"bom__project": project}

    def __str__(self):
        return f"{self.item_no} ({self.bom_id})"


# ---------------------------------------------------------------------------
# §11 InventoryLot
# ---------------------------------------------------------------------------


class InventoryLot(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="inventory_lots"
    )
    part = models.ForeignKey(
        Part, on_delete=models.PROTECT, related_name="inventory_lots"
    )
    serial_type = models.CharField(
        max_length=8, choices=SerialType.choices, default=SerialType.LOT
    )
    serial_number = models.CharField(max_length=100)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    qty_available = models.DecimalField(max_digits=18, decimal_places=4)
    location = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=16,
        choices=InventoryLotStatus.choices,
        default=InventoryLotStatus.AVAILABLE,
    )
    received_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "serial_number"],
                name="uq_inventorylot_project_serial",
            ),
        ]
        indexes = [
            models.Index(
                fields=["part", "status"], name="ix_inventorylot_part_status"
            ),
        ]

    def __str__(self):
        return self.serial_number


# ---------------------------------------------------------------------------
# §12 WorkOrder
# ---------------------------------------------------------------------------


class WorkOrder(NumberedModel):
    number_field = "code"
    number_prefix = "WO-"

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="work_orders"
    )
    code = models.CharField(max_length=64)
    bom = models.ForeignKey(
        Bom, on_delete=models.PROTECT, related_name="work_orders"
    )
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    status = models.CharField(
        max_length=16, choices=WorkOrderStatus.choices, default=WorkOrderStatus.PLANNED
    )
    due_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_work_orders",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "code"], name="uq_workorder_project_code"
            ),
        ]

    def __str__(self):
        return self.code


# ---------------------------------------------------------------------------
# §13 PurchaseOrder
# ---------------------------------------------------------------------------


class PurchaseOrder(NumberedModel):
    number_field = "po_number"
    number_prefix = "PO-"

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="purchase_orders"
    )
    po_number = models.CharField(max_length=64)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name="purchase_orders"
    )
    status = models.CharField(
        max_length=16,
        choices=PurchaseOrderStatus.choices,
        default=PurchaseOrderStatus.DRAFT,
    )
    order_date = models.DateField(null=True, blank=True)
    expected_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=8, default="CNY")
    total_amount = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "po_number"], name="uq_purchaseorder_project_po"
            ),
        ]
        indexes = [
            models.Index(
                fields=["supplier", "status"], name="ix_po_supplier_status"
            ),
        ]

    def __str__(self):
        return self.po_number


# ---------------------------------------------------------------------------
# §14 TestCase / §15 TestRun
# ---------------------------------------------------------------------------


class TestCase(NumberedModel):
    number_field = "code"
    number_prefix = "TC-"

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="test_cases"
    )
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    test_type = models.CharField(
        max_length=32, choices=TestType.choices, blank=True
    )
    precondition = models.TextField(blank=True)
    expected = models.TextField(blank=True)
    status = models.CharField(
        max_length=16, choices=TestCaseStatus.choices, default=TestCaseStatus.ACTIVE
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "code"], name="uq_testcase_project_code"
            ),
        ]

    def __str__(self):
        return self.code


class TestRun(NumberedModel):
    number_field = "run_no"
    number_prefix = "TR-"

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="test_runs"
    )
    test_case = models.ForeignKey(
        TestCase, on_delete=models.CASCADE, related_name="runs"
    )
    run_no = models.CharField(max_length=64)
    sample_serial = models.CharField(max_length=100, blank=True)
    result = models.CharField(max_length=16, choices=TestRunResult.choices)
    tested_at = models.DateTimeField(null=True, blank=True)
    tester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="test_runs",
    )
    data = models.JSONField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "run_no"], name="uq_testrun_project_run_no"
            ),
        ]
        indexes = [
            models.Index(fields=["test_case"], name="ix_testrun_test_case"),
            models.Index(fields=["result"], name="ix_testrun_result"),
        ]

    def __str__(self):
        return self.run_no


# ---------------------------------------------------------------------------
# §16 ECN / §17 ECNImpact
# ---------------------------------------------------------------------------


class ECN(NumberedModel):
    number_field = "ecn_number"
    number_prefix = "ECN-"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="ecns")
    ecn_number = models.CharField(max_length=64)
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    change_type = models.CharField(
        max_length=32, choices=ChangeType.choices, blank=True
    )
    status = models.CharField(
        max_length=16, choices=ECNStatus.choices, default=ECNStatus.DRAFT
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_ecns",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_ecns",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    effective_date = models.DateField(null=True, blank=True)
    agent_run = models.ForeignKey(
        "agents.AgentRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ecns",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "ecn_number"], name="uq_ecn_project_ecn_number"
            ),
        ]

    def __str__(self):
        return self.ecn_number


class ECNImpact(models.Model):
    ecn = models.ForeignKey(ECN, on_delete=models.CASCADE, related_name="impacts")
    affected_type = models.CharField(max_length=32, choices=enum_choices(EntityType))
    affected_id = models.CharField(max_length=64)
    impact_type = models.CharField(
        max_length=32, choices=ImpactType.choices, blank=True
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["ecn"], name="ix_ecnimpact_ecn"),
            models.Index(
                fields=["affected_type", "affected_id"],
                name="ix_ecnimpact_affected",
            ),
        ]

    def __str__(self):
        return f"{self.ecn_id}:{self.affected_type}:{self.affected_id}"


# ---------------------------------------------------------------------------
# §19 Document
# ---------------------------------------------------------------------------


class Document(NumberedModel):
    number_field = "doc_no"
    number_prefix = "DOC-"

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="documents"
    )
    doc_no = models.CharField(max_length=64)
    title = models.CharField(max_length=300)
    doc_type = models.CharField(max_length=32, choices=DocumentType.choices)
    file_path = models.CharField(max_length=500)
    source_path = models.CharField(max_length=500, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    checksum = models.CharField(max_length=64, blank=True)
    is_readonly = models.BooleanField(default=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_documents",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "doc_no"], name="uq_document_project_doc_no"
            ),
        ]
        indexes = [
            models.Index(fields=["project", "doc_type"], name="ix_document_project_type"),
            models.Index(fields=["checksum"], name="ix_document_checksum"),
        ]

    def __str__(self):
        return self.doc_no


# ---------------------------------------------------------------------------
# §20 GitRepo / §21 GitCommit
# ---------------------------------------------------------------------------


class GitRepo(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="git_repos"
    )
    name = models.CharField(max_length=200)
    local_path = models.CharField(max_length=500)
    url = models.CharField(max_length=500, blank=True)
    default_branch = models.CharField(max_length=100, blank=True)
    is_readonly = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"], name="uq_gitrepo_project_name"
            ),
        ]

    def __str__(self):
        return self.name


class GitCommit(models.Model):
    repo = models.ForeignKey(
        GitRepo, on_delete=models.CASCADE, related_name="commits"
    )
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="git_commits"
    )
    sha = models.CharField(max_length=40)
    author_name = models.CharField(max_length=100, blank=True)
    author_email = models.CharField(max_length=254, blank=True)
    committed_at = models.DateTimeField(null=True, blank=True)
    message = models.TextField(blank=True)
    branch = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["repo", "sha"], name="uq_gitcommit_repo_sha"
            ),
        ]
        indexes = [
            models.Index(fields=["committed_at"], name="ix_gitcommit_committed_at"),
        ]

    def __str__(self):
        return self.sha

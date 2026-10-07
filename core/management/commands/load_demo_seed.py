"""演示种子数据导入命令（B 段）。

- 默认读取 ``fixtures/demo_seed.json``；``--flush`` 先清空既有项目域数据。
- 幂等：重复运行结果一致（每次先删除 fixture 同 code 的项目再重建；User 复用）。
- 编号直写：全程 ``numbering_suspended()``，不触发自动编号生成（R8）。
- 顺序调整：因 ``Project.created_by`` 与 ``Requirement/ECN/TraceLink.agent_run``
  的外键依赖，``users`` / ``project`` / ``agent_runs`` 提前到依赖方之前；
  其余保持指令给定的相对顺序。
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_date, parse_datetime

from agents.models import AgentRun
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
from core.numbering import numbering_suspended
from traceability.models import TraceLink

DEFAULT_SEED = Path(settings.BASE_DIR) / "fixtures" / "demo_seed.json"


def _dt(value):
    return parse_datetime(value) if value else None


def _d(value):
    return parse_date(value) if value else None


class Command(BaseCommand):
    help = "从 fixtures/demo_seed.json 导入演示数据（幂等；--flush 清空后重载）。"

    def add_arguments(self, parser):
        parser.add_argument("--seed", default=str(DEFAULT_SEED))
        parser.add_argument("--flush", action="store_true")

    def handle(self, *args, **options):
        seed_path = Path(options["seed"])
        if not seed_path.exists():
            raise CommandError(f"种子文件不存在：{seed_path}")
        data = json.loads(seed_path.read_text(encoding="utf-8"))
        self.index = {}

        with transaction.atomic(), numbering_suspended():
            if options["flush"] or Project.objects.filter(
                code=data["project"]["code"]
            ).exists():
                self._clear()
            counts = self._load(data)

        self.stdout.write(self.style.SUCCESS("演示种子导入完成："))
        for name, count in counts.items():
            self.stdout.write(f"  {name}: {count}")

    # -- helpers -----------------------------------------------------------
    def _remember(self, collection, fixture_id, obj):
        self.index.setdefault(collection, {})[fixture_id] = obj
        return obj

    def _get(self, collection, fixture_id):
        return self.index[collection][fixture_id]

    def _clear(self):
        """按依赖倒序显式清空项目域数据（避免跨路径 PROTECT 误判）。"""
        GitCommit.objects.all().delete()
        TraceLink.objects.all().delete()
        ECNImpact.objects.all().delete()
        ECN.objects.all().delete()
        Document.objects.all().delete()
        TestRun.objects.all().delete()
        TestCase.objects.all().delete()
        RequirementParam.objects.all().delete()
        Requirement.objects.all().delete()
        WorkOrder.objects.all().delete()
        BomItem.objects.all().delete()
        Bom.objects.all().delete()
        PurchaseOrder.objects.all().delete()
        InventoryLot.objects.all().delete()
        SupplierPart.objects.all().delete()
        PartParam.objects.all().delete()
        Part.objects.all().delete()
        Supplier.objects.all().delete()
        GitRepo.objects.all().delete()
        AgentRun.objects.all().delete()
        Project.objects.all().delete()

    def _load(self, data):
        counts = {}
        counts["users"] = self._load_users(data["users"])
        counts["project"] = self._load_project(data["project"])
        counts["agent_runs"] = self._load_agent_runs(data["agent_runs"])
        counts["parts"] = self._load_parts(data["parts"])
        counts["part_params"] = self._load_part_params(data["part_params"])
        counts["suppliers"] = self._load_suppliers(data["suppliers"])
        counts["supplier_parts"] = self._load_supplier_parts(data["supplier_parts"])
        counts["requirements"] = self._load_requirements(data["requirements"])
        counts["requirement_params"] = self._load_requirement_params(
            data["requirement_params"]
        )
        counts["boms"] = self._load_boms(data["boms"])
        counts["bom_items"] = self._load_bom_items(data["bom_items"])
        counts["inventory_lots"] = self._load_inventory_lots(data["inventory_lots"])
        counts["work_orders"] = self._load_work_orders(data["work_orders"])
        counts["purchase_orders"] = self._load_purchase_orders(data["purchase_orders"])
        counts["test_cases"] = self._load_test_cases(data["test_cases"])
        counts["test_runs"] = self._load_test_runs(data["test_runs"])
        counts["ecns"] = self._load_ecns(data["ecns"])
        counts["ecn_impacts"] = self._load_ecn_impacts(data["ecn_impacts"])
        counts["trace_links"] = self._load_trace_links(data["trace_links"])
        counts["documents"] = self._load_documents(data["documents"])
        counts["git_repos"] = self._load_git_repos(data["git_repos"])
        counts["git_commits"] = self._load_git_commits(data["git_commits"])
        return counts

    # -- collections -------------------------------------------------------
    def _load_users(self, rows):
        for row in rows:
            is_admin = row["role"] == "admin"
            user = User.objects.filter(username=row["username"]).first()
            if user is None:
                user = User(
                    username=row["username"],
                    email=row.get("email") or "",
                    first_name=row.get("first_name") or "",
                    last_name=row.get("last_name") or "",
                    role=row["role"],
                    is_active=row.get("is_active", True),
                    is_staff=is_admin,
                    is_superuser=is_admin,
                    date_joined=_dt(row.get("date_joined")),
                )
                user.set_unusable_password()
                user.save()
            else:
                user.role = row["role"]
                user.is_staff = is_admin
                user.is_superuser = is_admin
                user.save(update_fields=["role", "is_staff", "is_superuser"])
            self._remember("users", row["id"], user)

        for row in rows:
            user = self._get("users", row["id"])
            expected = row["role"] == "admin"
            assert user.is_superuser is expected, (
                f"role↔is_superuser 映射错误：{user.username} role={row['role']} "
                f"is_superuser={user.is_superuser}"
            )
            assert user.is_staff is expected, (
                f"role↔is_staff 映射错误：{user.username} role={row['role']} "
                f"is_staff={user.is_staff}"
            )
        return len(rows)

    def _load_project(self, row):
        project = Project.objects.create(
            code=row["code"],
            name=row["name"],
            description=row.get("description") or "",
            status=row["status"],
            created_by=self._get("users", row["created_by_id"]),
            created_at=_dt(row["created_at"]),
            updated_at=_dt(row["updated_at"]),
        )
        self._remember("project", row["id"], project)
        return 1

    def _load_agent_runs(self, rows):
        for row in rows:
            run = AgentRun.objects.create(
                project=self._get("project", row["project_id"]),
                agent_name=row["agent_name"],
                status=row["status"],
                prompt_id=row["prompt_id"],
                prompt_version=row["prompt_version"],
                model=row["model"],
                temperature=row["temperature"],
                input_json=row["input_json"],
                input_hash=row["input_hash"],
                output_json=row.get("output_json"),
                output_schema_valid=row.get("output_schema_valid"),
                reference_check_passed=row.get("reference_check_passed"),
                invalid_references=row.get("invalid_references"),
                references=row.get("references"),
                confirmed_by=(
                    self._get("users", row["confirmed_by_id"])
                    if row.get("confirmed_by_id")
                    else None
                ),
                confirmed_at=_dt(row.get("confirmed_at")),
                error=row.get("error") or "",
                created_at=_dt(row["created_at"]),
            )
            self._remember("agent_runs", row["id"], run)
        return len(rows)

    def _load_parts(self, rows):
        for row in rows:
            part = Part.objects.create(
                project=self._get("project", row["project_id"]),
                part_number=row["part_number"],
                name=row["name"],
                description=row.get("description") or "",
                category=row.get("category") or "",
                manufacturer=row.get("manufacturer") or "",
                mpn=row.get("mpn") or "",
                lifecycle_status=row["lifecycle_status"],
                unit=row.get("unit") or "",
                is_critical=row.get("is_critical", False),
                created_at=_dt(row["created_at"]),
                updated_at=_dt(row["updated_at"]),
            )
            self._remember("parts", row["id"], part)
        return len(rows)

    def _load_part_params(self, rows):
        for row in rows:
            obj = PartParam.objects.create(
                part=self._get("parts", row["part_id"]),
                name=row["name"],
                value_text=row.get("value_text") or "",
                value_num=row.get("value_num"),
                value_min=row.get("value_min"),
                value_max=row.get("value_max"),
                unit=row.get("unit") or "",
                is_key=row.get("is_key", False),
                created_at=_dt(row["created_at"]),
            )
            self._remember("part_params", row["id"], obj)
        return len(rows)

    def _load_suppliers(self, rows):
        for row in rows:
            supplier = Supplier.objects.create(
                project=self._get("project", row["project_id"]),
                code=row["code"],
                name=row["name"],
                contact_name=row.get("contact_name") or "",
                email=row.get("email") or "",
                phone=row.get("phone") or "",
                status=row["status"],
                created_at=_dt(row["created_at"]),
                updated_at=_dt(row["updated_at"]),
            )
            self._remember("suppliers", row["id"], supplier)
        return len(rows)

    def _load_supplier_parts(self, rows):
        for row in rows:
            obj = SupplierPart.objects.create(
                supplier=self._get("suppliers", row["supplier_id"]),
                part=self._get("parts", row["part_id"]),
                supplier_part_number=row.get("supplier_part_number") or "",
                unit_price=row.get("unit_price"),
                currency=row.get("currency") or "CNY",
                lead_time_days=row.get("lead_time_days"),
                moq=row.get("moq"),
                is_preferred=row.get("is_preferred", False),
                lifecycle_status=row.get("lifecycle_status", "active"),
                created_at=_dt(row["created_at"]),
                updated_at=_dt(row["updated_at"]),
            )
            self._remember("supplier_parts", row["id"], obj)
        return len(rows)

    def _load_requirements(self, rows):
        for row in rows:
            requirement = Requirement.objects.create(
                project=self._get("project", row["project_id"]),
                code=row["code"],
                title=row["title"],
                content=row.get("content") or "",
                source_type=row["source_type"],
                source_ref=row.get("source_ref") or "",
                status=row["status"],
                priority=row.get("priority"),
                confidence=row.get("confidence"),
                agent_run=(
                    self._get("agent_runs", row["agent_run_id"])
                    if row.get("agent_run_id")
                    else None
                ),
                confirmed_by=(
                    self._get("users", row["confirmed_by_id"])
                    if row.get("confirmed_by_id")
                    else None
                ),
                confirmed_at=_dt(row.get("confirmed_at")),
                created_at=_dt(row["created_at"]),
                updated_at=_dt(row["updated_at"]),
            )
            self._remember("requirements", row["id"], requirement)
        return len(rows)

    def _load_requirement_params(self, rows):
        for row in rows:
            obj = RequirementParam.objects.create(
                requirement=self._get("requirements", row["requirement_id"]),
                name=row["name"],
                operator=row["operator"],
                value_text=row.get("value_text") or "",
                value_num=row.get("value_num"),
                value_min=row.get("value_min"),
                value_max=row.get("value_max"),
                unit=row.get("unit") or "",
                is_mandatory=row.get("is_mandatory", True),
                created_at=_dt(row["created_at"]),
            )
            self._remember("requirement_params", row["id"], obj)
        return len(rows)

    def _load_boms(self, rows):
        for row in rows:
            bom = Bom.objects.create(
                project=self._get("project", row["project_id"]),
                bom_no=row["bom_no"],
                name=row["name"],
                version=row["version"],
                status=row["status"],
                created_by=self._get("users", row["created_by_id"]),
                created_at=_dt(row["created_at"]),
                updated_at=_dt(row["updated_at"]),
            )
            self._remember("boms", row["id"], bom)
        return len(rows)

    def _load_bom_items(self, rows):
        for row in rows:
            obj = BomItem.objects.create(
                bom=self._get("boms", row["bom_id"]),
                item_no=row["item_no"],
                parent_item=None,
                part=self._get("parts", row["part_id"]),
                quantity=row["quantity"],
                unit=row.get("unit") or "",
                ref_des=row.get("ref_des") or "",
                position=row.get("position") or "",
                is_critical=row.get("is_critical", False),
                notes=row.get("notes") or "",
                created_at=_dt(row["created_at"]),
                updated_at=_dt(row["updated_at"]),
            )
            self._remember("bom_items", row["id"], obj)
        for row in rows:
            if row.get("parent_item_id"):
                obj = self._get("bom_items", row["id"])
                obj.parent_item = self._get("bom_items", row["parent_item_id"])
                obj.save(update_fields=["parent_item"])
        return len(rows)

    def _load_inventory_lots(self, rows):
        for row in rows:
            obj = InventoryLot.objects.create(
                project=self._get("project", row["project_id"]),
                part=self._get("parts", row["part_id"]),
                serial_type=row["serial_type"],
                serial_number=row["serial_number"],
                quantity=row["quantity"],
                qty_available=row["qty_available"],
                location=row.get("location") or "",
                status=row["status"],
                received_at=_dt(row.get("received_at")),
                created_at=_dt(row["created_at"]),
                updated_at=_dt(row["updated_at"]),
            )
            self._remember("inventory_lots", row["id"], obj)
        return len(rows)

    def _load_work_orders(self, rows):
        for row in rows:
            obj = WorkOrder.objects.create(
                project=self._get("project", row["project_id"]),
                code=row["code"],
                bom=self._get("boms", row["bom_id"]),
                quantity=row["quantity"],
                status=row["status"],
                due_date=_d(row.get("due_date")),
                created_by=(
                    self._get("users", row["created_by_id"])
                    if row.get("created_by_id")
                    else None
                ),
                created_at=_dt(row["created_at"]),
                updated_at=_dt(row["updated_at"]),
            )
            self._remember("work_orders", row["id"], obj)
        return len(rows)

    def _load_purchase_orders(self, rows):
        for row in rows:
            obj = PurchaseOrder.objects.create(
                project=self._get("project", row["project_id"]),
                po_number=row["po_number"],
                supplier=self._get("suppliers", row["supplier_id"]),
                status=row["status"],
                order_date=_d(row.get("order_date")),
                expected_date=_d(row.get("expected_date")),
                currency=row.get("currency") or "CNY",
                total_amount=row.get("total_amount"),
                notes=row.get("notes") or "",
                created_at=_dt(row["created_at"]),
                updated_at=_dt(row["updated_at"]),
            )
            self._remember("purchase_orders", row["id"], obj)
        return len(rows)

    def _load_test_cases(self, rows):
        for row in rows:
            obj = TestCase.objects.create(
                project=self._get("project", row["project_id"]),
                code=row["code"],
                name=row["name"],
                description=row.get("description") or "",
                test_type=row.get("test_type") or "",
                precondition=row.get("precondition") or "",
                expected=row.get("expected") or "",
                status=row["status"],
                created_at=_dt(row["created_at"]),
                updated_at=_dt(row["updated_at"]),
            )
            self._remember("test_cases", row["id"], obj)
        return len(rows)

    def _load_test_runs(self, rows):
        for row in rows:
            obj = TestRun.objects.create(
                project=self._get("project", row["project_id"]),
                test_case=self._get("test_cases", row["test_case_id"]),
                run_no=row["run_no"],
                sample_serial=row.get("sample_serial") or "",
                result=row["result"],
                tested_at=_dt(row.get("tested_at")),
                tester=(
                    self._get("users", row["tester_id"])
                    if row.get("tester_id")
                    else None
                ),
                data=row.get("data"),
                notes=row.get("notes") or "",
                created_at=_dt(row["created_at"]),
                updated_at=_dt(row["updated_at"]),
            )
            self._remember("test_runs", row["id"], obj)
        return len(rows)

    def _load_ecns(self, rows):
        for row in rows:
            obj = ECN.objects.create(
                project=self._get("project", row["project_id"]),
                ecn_number=row["ecn_number"],
                title=row["title"],
                description=row.get("description") or "",
                change_type=row.get("change_type") or "",
                status=row["status"],
                requested_by=self._get("users", row["requested_by_id"]),
                approved_by=(
                    self._get("users", row["approved_by_id"])
                    if row.get("approved_by_id")
                    else None
                ),
                approved_at=_dt(row.get("approved_at")),
                effective_date=_d(row.get("effective_date")),
                agent_run=(
                    self._get("agent_runs", row["agent_run_id"])
                    if row.get("agent_run_id")
                    else None
                ),
                created_at=_dt(row["created_at"]),
                updated_at=_dt(row["updated_at"]),
            )
            self._remember("ecns", row["id"], obj)
        return len(rows)

    def _load_ecn_impacts(self, rows):
        for row in rows:
            obj = ECNImpact.objects.create(
                ecn=self._get("ecns", row["ecn_id"]),
                affected_type=row["affected_type"],
                affected_id=row["affected_id"],
                impact_type=row.get("impact_type") or "",
                description=row.get("description") or "",
                created_at=_dt(row["created_at"]),
            )
            self._remember("ecn_impacts", row["id"], obj)
        return len(rows)

    def _load_trace_links(self, rows):
        for row in rows:
            obj = TraceLink.objects.create(
                project=self._get("project", row["project_id"]),
                from_type=row["from_type"],
                from_id=row["from_id"],
                to_type=row["to_type"],
                to_id=row["to_id"],
                relation_type=row["relation_type"],
                source=row["source"],
                confidence=row.get("confidence"),
                agent_run=(
                    self._get("agent_runs", row["agent_run_id"])
                    if row.get("agent_run_id")
                    else None
                ),
                confirmed_by=(
                    self._get("users", row["confirmed_by_id"])
                    if row.get("confirmed_by_id")
                    else None
                ),
                confirmed_at=_dt(row.get("confirmed_at")),
                evidence=row.get("evidence"),
                metadata=row.get("metadata"),
                created_at=_dt(row["created_at"]),
            )
            self._remember("trace_links", row["id"], obj)
        return len(rows)

    def _load_documents(self, rows):
        for row in rows:
            obj = Document.objects.create(
                project=self._get("project", row["project_id"]),
                doc_no=row["doc_no"],
                title=row["title"],
                doc_type=row["doc_type"],
                file_path=row["file_path"],
                source_path=row.get("source_path") or "",
                mime_type=row.get("mime_type") or "",
                size_bytes=row.get("size_bytes"),
                checksum=row.get("checksum") or "",
                is_readonly=row.get("is_readonly", True),
                uploaded_by=(
                    self._get("users", row["uploaded_by_id"])
                    if row.get("uploaded_by_id")
                    else None
                ),
                created_at=_dt(row["created_at"]),
            )
            self._remember("documents", row["id"], obj)
        return len(rows)

    def _load_git_repos(self, rows):
        for row in rows:
            obj = GitRepo.objects.create(
                project=self._get("project", row["project_id"]),
                name=row["name"],
                local_path=row["local_path"],
                url=row.get("url") or "",
                default_branch=row.get("default_branch") or "",
                is_readonly=row.get("is_readonly", True),
                created_at=_dt(row["created_at"]),
                updated_at=_dt(row["updated_at"]),
            )
            self._remember("git_repos", row["id"], obj)
        return len(rows)

    def _load_git_commits(self, rows):
        for row in rows:
            obj = GitCommit.objects.create(
                repo=self._get("git_repos", row["repo_id"]),
                project=self._get("project", row["project_id"]),
                sha=row["sha"],
                author_name=row.get("author_name") or "",
                author_email=row.get("author_email") or "",
                committed_at=_dt(row.get("committed_at")),
                message=row.get("message") or "",
                branch=row.get("branch") or "",
                created_at=_dt(row["created_at"]),
            )
            self._remember("git_commits", row["id"], obj)
        return len(rows)
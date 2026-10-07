"""``manage.py bom_expand <bom_no> [--qty N] [--hierarchy]`` — BOM 多级展开（只读、零 LLM）。"""

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from core.bom_expand import BomExpandError, expand_bom
from core.models import Bom


class Command(BaseCommand):
    help = "展开 BOM（多级），输出层级缩进表 + totals。"

    def add_arguments(self, parser):
        parser.add_argument("bom_no")
        parser.add_argument("--project", default="DEMO-GW")
        parser.add_argument("--qty", default="1")
        parser.add_argument(
            "--hierarchy",
            action="store_true",
            help="展开全部层级（默认仅顶层，GT-BOM-001）",
        )

    def handle(self, *args, **options):
        bom = Bom.objects.filter(
            project__code=options["project"], bom_no=options["bom_no"]
        ).first()
        if bom is None:
            raise CommandError(f"BOM 不存在：{options['bom_no']}")

        try:
            result = expand_bom(
                bom,
                quantity=Decimal(options["qty"]),
                include_hierarchy=options["hierarchy"],
            )
        except BomExpandError as exc:
            raise CommandError(f"{exc.code}: {exc}") from exc

        for warning in result["warnings"]:
            self.stdout.write(f"[warning] {warning}")

        for line in result["lines"]:
            indent = "  " * line["depth"]
            self.stdout.write(
                f"{indent}{line['item_no']} {line['part_number']} ×{line['required_qty']}"
                f" (depth={line['depth']}, parent={line['parent_item_no']}, refs={line['ref_des']})"
            )

        self.stdout.write("--- totals ---")
        for total in result["totals"]:
            self.stdout.write(f"{total['part_number']}: {total['required_qty']}")
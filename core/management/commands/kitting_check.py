"""``manage.py kitting_check <wo_code>`` — 工单齐套检查（只读、零 LLM）。"""

from django.core.management.base import BaseCommand, CommandError

from core.kitting import analyze_kitting
from core.models import WorkOrder


class Command(BaseCommand):
    help = "检查工单齐套：缺料表 + 最晚到货日 + 替代项。"

    def add_arguments(self, parser):
        parser.add_argument("wo_code")
        parser.add_argument("--project", default="DEMO-GW")

    def handle(self, *args, **options):
        wo = WorkOrder.objects.filter(
            project__code=options["project"], code=options["wo_code"]
        ).first()
        if wo is None:
            raise CommandError(f"工单不存在：{options['wo_code']}")

        result = analyze_kitting(wo)
        self.stdout.write(
            f"工单 {result['work_order']} / BOM {result['bom_no']} / 数量 {result['quantity']}"
        )
        self.stdout.write(f"齐套：{'是' if result['ready'] else '否'}")

        if not result["shortages"]:
            self.stdout.write("缺料清单为空")
            return
        for shortage in result["shortages"]:
            self.stdout.write(
                f"缺料 {shortage['part_id']}: 需求 {shortage['required_qty']} / "
                f"可用 {shortage['available_qty']} / 缺口 {shortage['shortage_qty']} / "
                f"在途 {shortage['in_transit_qty']} / 最晚到货 {shortage['latest_arrival_date']} / "
                f"insufficient={shortage['insufficient']} / flags={shortage['risk_flags']}"
            )
            for alt in shortage["alternatives"]:
                self.stdout.write(
                    f"    替代 {alt['part_id']}: 可用 {alt['available_qty']} / "
                    f"在途 {alt['in_transit_qty']} / 到货 {alt['shortest_arrival_date']} / "
                    f"sufficient={alt['sufficient']}"
                )
"""``manage.py ecn_impact <ecn_no>`` — ECN 影响投影（只读、零写，D11-R2）。"""

from django.core.management.base import BaseCommand, CommandError

from core.ecn import project_ecn_impact
from core.models import ECN


class Command(BaseCommand):
    help = "ECN 影响投影（只读）：分类清单 + unresolved + consistency。"

    def add_arguments(self, parser):
        parser.add_argument("ecn_no")
        parser.add_argument("--project", default="DEMO-GW")

    def handle(self, *args, **options):
        ecn = ECN.objects.filter(
            project__code=options["project"], ecn_number=options["ecn_no"]
        ).first()
        if ecn is None:
            raise CommandError(f"ECN 不存在：{options['ecn_no']}")

        result = project_ecn_impact(ecn)
        self.stdout.write(
            f"ECN {result['ecn']} / status={result['status']} / "
            f"effective={result['effective']} / warnings={result['warnings']}"
        )
        for key, items in result["impacts"].items():
            self.stdout.write(f"[{key}] {len(items)}")
            for item in items:
                self.stdout.write(
                    f"  {item['affected_id']} ({item['impact_type']}) {item['label']}"
                )
        for item in result["unresolved"]:
            self.stdout.write(f"[unresolved] {item['affected_type']}:{item['affected_id']}")
        for hint in result["consistency"]:
            self.stdout.write(f"[consistency] {hint}")
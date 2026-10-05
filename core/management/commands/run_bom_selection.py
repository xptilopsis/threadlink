"""D6-R2：``run_bom_selection`` — 运行 BOM 选型解释管道（引擎权威 + LLM 解释）。

用法示例：

    python manage.py run_bom_selection --project DEMO-GW

5 项 criteria 均可经参数覆盖（``--voltage-min/--voltage-max/--current-min/--temp-min/--temp-max/--ip-min``）；
``--cost-max`` 默认不启用（``None``）。输出 run id + 候选摘要。
"""

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from agents.bom_selection import run_bom_selection_agent
from core.models import Project
from core.selection import Criteria


class Command(BaseCommand):
    help = "运行 BOM 选型解释管道（引擎权威 + LLM 解释）。"

    def add_arguments(self, parser):
        parser.add_argument("--project", default="DEMO-GW")
        parser.add_argument("--voltage-min", type=Decimal, default=Decimal(9))
        parser.add_argument("--voltage-max", type=Decimal, default=Decimal(36))
        parser.add_argument("--current-min", type=Decimal, default=Decimal(5))
        parser.add_argument("--temp-min", type=Decimal, default=Decimal(-40))
        parser.add_argument("--temp-max", type=Decimal, default=Decimal(85))
        parser.add_argument("--ip-min", type=int, default=65)
        parser.add_argument("--cost-max", type=Decimal, default=None)
        parser.add_argument("--model", default=None)
        parser.add_argument("--temperature", type=float, default=0.2)

    def handle(self, *args, **options):
        project = Project.objects.filter(code=options["project"]).first()
        if project is None:
            raise CommandError(f"project 不存在：{options['project']}")

        criteria = Criteria(
            voltage_min=options["voltage_min"],
            voltage_max=options["voltage_max"],
            current_min=options["current_min"],
            temp_min=options["temp_min"],
            temp_max=options["temp_max"],
            ip_min=options["ip_min"],
            cost_max=options["cost_max"],
        )
        summary = run_bom_selection_agent(
            project,
            criteria,
            None,
            model=options["model"],
            temperature=options["temperature"],
        )
        self.stdout.write(
            f"ok={summary.get('ok')} run={summary.get('agent_run_id')} "
            f"candidates={summary.get('candidates')} recommended={summary.get('recommended')}"
        )
        for candidate in (summary.get("output") or {}).get("candidates", []):
            self.stdout.write(
                f"  {candidate['part_number']} score={candidate['score']} "
                f"price={candidate['unit_price']} lead={candidate['lead_time_days']} "
                f"| {candidate['rationale'][:80]}"
            )
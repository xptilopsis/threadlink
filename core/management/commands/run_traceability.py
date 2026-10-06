"""D7-R1：``run_traceability`` — 运行追溯链解释管道（DB 权威链 + LLM 文案/引用建议）。

用法示例：

    python manage.py run_traceability SN-DEMO-001 --project DEMO-GW

未命中时明确输出「未命中，无 run 产生」，**不产生 AgentRun**（GT-TRACE-003）。
"""

from django.core.management.base import BaseCommand, CommandError

from agents.traceability import run_traceability_agent
from core.models import Project
from traceability.services import AmbiguousReferenceError


class Command(BaseCommand):
    help = "运行追溯链解释管道（DB 权威链 + LLM 文案/引用建议）。"

    def add_arguments(self, parser):
        parser.add_argument("serial", help="序列号 / 批次号（如 SN-DEMO-001）")
        parser.add_argument("--project", default="DEMO-GW")
        parser.add_argument("--query-type", default="serial")
        parser.add_argument("--model", default=None)
        parser.add_argument("--temperature", type=float, default=0.0)

    def handle(self, *args, **options):
        project = Project.objects.filter(code=options["project"]).first()
        if project is None:
            raise CommandError(f"project 不存在：{options['project']}")

        try:
            summary = run_traceability_agent(
                project,
                options["serial"],
                None,
                query_type=options["query_type"],
                model=options["model"],
                temperature=options["temperature"],
            )
        except AmbiguousReferenceError as exc:
            raise CommandError(str(exc)) from exc

        if not summary.get("found"):
            self.stdout.write("未命中，无 run 产生")
            return

        self.stdout.write(
            f"ok={summary.get('ok')} run={summary.get('agent_run_id')} "
            f"found={summary.get('found')}"
        )
        if summary.get("summary"):
            self.stdout.write(summary["summary"])
        for item in summary.get("invalid_references") or []:
            self.stdout.write(
                f"  核验失败：{item['entity_type']}:{item['entity_id']} ({item['reason']})"
            )
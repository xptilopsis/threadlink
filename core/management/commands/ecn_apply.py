"""``manage.py ecn_apply <ecn_no> [--username admin]`` — 应用 ECN（唯一写路径，D11-R2）。"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.ecn import EcnApplyError, apply_ecn
from core.models import ECN


class Command(BaseCommand):
    help = "应用 ECN（写回 BomItem.part + 确认 affects 边）。"

    def add_arguments(self, parser):
        parser.add_argument("ecn_no")
        parser.add_argument("--project", default="DEMO-GW")
        parser.add_argument("--username", default="admin")

    def handle(self, *args, **options):
        ecn = ECN.objects.filter(
            project__code=options["project"], ecn_number=options["ecn_no"]
        ).first()
        if ecn is None:
            raise CommandError(f"ECN 不存在：{options['ecn_no']}")
        user = get_user_model().objects.filter(username=options["username"]).first()
        if user is None:
            raise CommandError(f"用户不存在：{options['username']}")

        try:
            result = apply_ecn(ecn, user)
        except EcnApplyError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            f"ECN {result['ecn']} 已应用：新建边 {result['created_edges']}、"
            f"补确认 {result['confirmed_edges']}、写回 {result['rewritten']} "
            f"（status={result['ecn_status']}）"
        )
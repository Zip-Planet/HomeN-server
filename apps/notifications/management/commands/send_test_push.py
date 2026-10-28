"""특정 유저의 활성 기기로 테스트 푸시를 보내는 커맨드 (백엔드 검증용).

예: `uv run python manage.py send_test_push --user 3 --dry-run`
"""

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.notifications.fcm import PushNotConfiguredError
from apps.notifications.services import send_push_to_user
from apps.users.models import User


class Command(BaseCommand):
    help = "유저의 활성 기기 전부에 테스트 푸시를 보냅니다."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--user", type=int, required=True, help="수신 유저 PK")
        parser.add_argument("--title", default="HomeN 테스트 알림", help="알림 제목")
        parser.add_argument("--body", default="푸시 설정이 정상적으로 동작하고 있어요.", help="알림 본문")
        parser.add_argument("--dry-run", action="store_true", help="실제 전달 없이 FCM 검증만 수행")

    def handle(self, *args, **options) -> None:
        user = User.objects.filter(pk=options["user"]).first()
        if user is None:
            raise CommandError(f"유저를 찾을 수 없습니다: id={options['user']}")

        try:
            result = send_push_to_user(
                user=user, title=options["title"], body=options["body"], dry_run=options["dry_run"]
            )
        except PushNotConfiguredError as e:
            raise CommandError(str(e)) from e

        self.stdout.write(
            self.style.SUCCESS(
                f"테스트 푸시 완료 — sent={result.sent} failed={result.failed} deactivated={result.deactivated}"
            )
        )

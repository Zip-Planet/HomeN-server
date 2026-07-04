"""분담안 자동 확정 + 만료 전환 커맨드.

매주 월요일 00:00 (Asia/Seoul) 에 cron 으로 실행한다:

    0 0 * * 1  cd /app && uv run python manage.py finalize_assignments

- 시작된 주차의 proposed 분담안 중 확정 조건을 만족하는 것을 자동 확정한다
  (confirmed_by=None). 불만족은 proposed 로 유지 — 관리자가 재생성/수동 확정.
- 종료된 주차의 confirmed 분담안을 expired(히스토리) 로 전환한다.

멱등 — 중복 실행 안전.
"""

from django.core.management.base import BaseCommand

from apps.homes import services


class Command(BaseCommand):
    help = "시작된 주차의 proposed 분담안을 자동 확정하고, 지난 주차의 confirmed 를 expired 로 전환합니다."

    def handle(self, *args, **options) -> None:
        confirmed, skipped = services.auto_confirm_due_assignments()
        expired = services.expire_past_assignments()
        self.stdout.write(
            self.style.SUCCESS(
                f"분담안 정리 완료: 자동 확정 {confirmed}건, 확정 보류 {skipped}건, 만료 전환 {expired}건"
            )
        )

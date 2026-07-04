"""다음 주차 분담안 자동 생성 커맨드.

매주 일요일 21:05 (Asia/Seoul) 에 cron 으로 실행한다:

    5 21 * * 0  cd /app && uv run python manage.py generate_assignments

관리자가 수동 생성해 둔 주차는 스킵되므로 중복 생성이 없다 (멱등).
"""

from django.core.management.base import BaseCommand

from apps.homes import services


class Command(BaseCommand):
    help = "모든 활성 집에 다음 주차 분담안을 자동 생성합니다 (이미 있으면 스킵)."

    def handle(self, *args, **options) -> None:
        created, skipped = services.generate_weekly_assignments()
        self.stdout.write(self.style.SUCCESS(f"분담안 자동 생성 완료: 생성 {created}건, 스킵 {skipped}건"))

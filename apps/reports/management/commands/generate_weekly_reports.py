"""주간 리포트 자동 생성 커맨드 (매주 일요일 21:00, cron: `0 21 * * 0`).

멱등 — 같은 주차에 중복 실행돼도 집계를 덮어쓸 뿐 중복 생성되지 않는다.
"""

from django.core.management.base import BaseCommand

from apps.reports.services import generate_weekly_reports


class Command(BaseCommand):
    help = "이번 주차 주간 리포트를 모든 활성 집에 대해 생성합니다 (일요일 21:00)."

    def handle(self, *args, **options) -> None:
        created, skipped = generate_weekly_reports()
        self.stdout.write(
            self.style.SUCCESS(f"주간 리포트 생성 완료 — 생성/갱신 {created}건, 스킵 {skipped}건")
        )

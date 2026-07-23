"""조율 카드 만료 처리 커맨드 (cron 예: `0 0 * * *` — 매일 자정).

대상 집안일 날짜의 다음 날 23:59 가 지난 대기 카드를 만료 상태로 바꾼다.
"""

from django.core.management.base import BaseCommand

from apps.boards.services import expire_board_requests


class Command(BaseCommand):
    help = "응답 기한이 지난 도움/교환 요청을 만료 처리합니다."

    def handle(self, *args, **options) -> None:
        helps, swaps = expire_board_requests()
        self.stdout.write(
            self.style.SUCCESS(f"조율 카드 만료 완료 — 도움 {helps}건, 교환 {swaps}건")
        )

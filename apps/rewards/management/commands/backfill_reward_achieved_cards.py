"""구버전 리워드 달성 카드 백필 커맨드 (1회성, 멱등).

`claimed_by` 가 이름 문자열이던 시절에 발행된 `reward_achieved` 봇 카드에
수령자 객체와 해당 주차 획득 포인트(`claimed_by_point`)를 채워 넣는다.
"""

from django.core.management.base import BaseCommand

from apps.rewards.services import backfill_reward_achieved_cards


class Command(BaseCommand):
    help = "구버전 형식의 리워드 달성 봇 카드 payload 를 현재 형식으로 갱신합니다."

    def handle(self, *args, **options) -> None:
        updated = backfill_reward_achieved_cards()
        self.stdout.write(self.style.SUCCESS(f"리워드 달성 카드 백필 완료 — {updated}건"))

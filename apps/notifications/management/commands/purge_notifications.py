"""보관 기간(7일)이 지난 알림 삭제 커맨드 (cron 예: `0 4 * * *`)."""

from django.core.management.base import BaseCommand

from apps.notifications.services import purge_expired_notifications


class Command(BaseCommand):
    help = "발생 후 7일이 지난 알림을 삭제합니다."

    def handle(self, *args, **options) -> None:
        deleted = purge_expired_notifications()
        self.stdout.write(self.style.SUCCESS(f"만료 알림 삭제 완료 — {deleted}건"))

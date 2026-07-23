from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """알림 도메인 앱.

    인앱 알림함(N1_NotificationInbox)과 푸시 설정(T5_My)을 담당한다.
    푸시 발송 인프라는 미정이므로 발송 지점만 TODO 로 표시하고, 지금은 알림
    레코드 적재까지만 수행한다.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"

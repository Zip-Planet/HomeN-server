from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """알림 도메인 앱.

    인앱 알림함(N1_NotificationInbox), 푸시 설정(T5_My), FCM 기기 등록·푸시 발송을
    담당한다. 알림 이벤트와 푸시 발송의 연결은 아직 하지 않았다 (`services.notify` 의
    TODO 참고).
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"

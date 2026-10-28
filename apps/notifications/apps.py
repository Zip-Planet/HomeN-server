from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """알림 도메인 앱.

    인앱 알림함(N1_NotificationInbox), 푸시 설정(T5_My), FCM 기기 등록·푸시 발송을
    담당한다. 알림 이벤트(`services.notify`)는 레코드 적재 후 커밋 시점에 같은 내용의
    푸시를 설정이 켜진 수신자에게 보낸다.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"

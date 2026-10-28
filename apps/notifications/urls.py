"""알림 URL 매핑.

`config.urls` 에서 다음과 같이 마운트된다.

- `path("api/v1/notifications/", include(notification_urlpatterns))`
- `path("api/v1/users/me/devices/", include(device_urlpatterns))`
  (푸시 기기는 "내 계정의 기기" 이므로 URL 은 users/me 아래에 붙는다)
- `path("api/v1/homes/mine/assignments/nudge/", AssignmentNudgeView.as_view())`
  (분담안 재촉은 알림 도메인 동작이지만 URL 은 분담안 흐름에 붙는다)
"""

from django.urls import path

from apps.notifications.views import (
    DeviceRegisterView,
    DeviceUnregisterView,
    NotificationListView,
    NotificationReadView,
    NotificationSettingView,
    PushTestView,
)

notification_urlpatterns = [
    path("", NotificationListView.as_view()),
    path("settings/", NotificationSettingView.as_view()),
    path("test/", PushTestView.as_view()),
    path("<int:notification_id>/read/", NotificationReadView.as_view()),
]

device_urlpatterns = [
    path("", DeviceRegisterView.as_view()),
    path("unregister/", DeviceUnregisterView.as_view()),
]

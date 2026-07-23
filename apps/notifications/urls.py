"""알림 URL 매핑.

`config.urls` 에서 다음과 같이 마운트된다.

- `path("api/v1/notifications/", include(notification_urlpatterns))`
- `path("api/v1/homes/mine/assignments/nudge/", AssignmentNudgeView.as_view())`
  (분담안 재촉은 알림 도메인 동작이지만 URL 은 분담안 흐름에 붙는다)
"""

from django.urls import path

from apps.notifications.views import (
    NotificationListView,
    NotificationReadView,
    NotificationSettingView,
)

notification_urlpatterns = [
    path("", NotificationListView.as_view()),
    path("settings/", NotificationSettingView.as_view()),
    path("<int:notification_id>/read/", NotificationReadView.as_view()),
]

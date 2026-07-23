from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.rewards.urls import reward_urlpatterns
from apps.reports.urls import report_urlpatterns
from apps.notifications.urls import notification_urlpatterns
from apps.notifications.views import AssignmentNudgeView
from apps.homes.urls import home_urlpatterns, starter_pack_urlpatterns
from apps.users.urls import auth_urlpatterns, user_urlpatterns

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include(auth_urlpatterns)),
    path("api/v1/users/", include(user_urlpatterns)),
    path("api/v1/homes/mine/rewards/", include(reward_urlpatterns)),
    path("api/v1/homes/mine/reports/", include(report_urlpatterns)),
    path("api/v1/homes/mine/assignments/nudge/", AssignmentNudgeView.as_view()),
    path("api/v1/notifications/", include(notification_urlpatterns)),
    path("api/v1/homes/", include(home_urlpatterns)),
    path("api/v1/starter-packs/", include(starter_pack_urlpatterns)),
    # Swagger
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

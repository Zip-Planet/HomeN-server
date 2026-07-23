"""주간 리포트 URL 매핑.

`config.urls` 에서 `path("api/v1/homes/mine/reports/", include(report_urlpatterns))`
로 마운트된다.
"""

from django.urls import path

from apps.reports.views import WeeklyReportView

report_urlpatterns = [
    path("weekly/", WeeklyReportView.as_view()),
]

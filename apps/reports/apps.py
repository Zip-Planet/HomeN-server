from django.apps import AppConfig


class ReportsConfig(AppConfig):
    """주간 리포트 도메인 앱.

    매주 일요일 21:00 에 그 주차의 집안일 수행 결과를 스냅샷으로 굳혀 둔다.
    이후 원본(집안일/분담안)이 바뀌어도 지난 리포트는 흔들리지 않는다.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reports"

from django.apps import AppConfig


class BoardsConfig(AppConfig):
    """집안 보드(FairBoard) 도메인 앱.

    보드는 두 종류의 카드가 시간순으로 섞인 피드다.
    - **봇 카드**: 시스템이 발행 (분담안 생성/확정, 주간 리포트, 리워드 달성).
    - **조율 카드**: 구성원이 발행 (도움 요청, 교환 요청).

    조율 카드 수락은 확정 분담안의 담당자(`AssignmentItem.assignee`)를 실제로
    바꾼다 — 보드는 안내창이 아니라 배정을 움직이는 도구다.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.boards"

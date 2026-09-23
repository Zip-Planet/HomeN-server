"""주간 리포트 조회 (읽기 전용).

조회할 때마다 그 시점의 완료 현황으로 실시간 집계한다. 화면(R1_WeeklyReport)이
언제 열어도 지금 기준의 "이번 주 진행률" 을 보여줘야 하기 때문이다.
일요일 21:00 스냅샷(`services.generate_report`)은 보드 봇 카드·알림 발행용이며 조회에는 쓰지 않는다.
"""

from datetime import date

from django.utils import timezone

from apps.homes.models import Home
from apps.reports.models import WeeklyReport
from apps.reports.services import build_report_payload, find_report_target


def get_weekly_report(*, home: Home, week_start: date) -> WeeklyReport | None:
    """한 집·한 주차의 리포트를 조회 시점 기준으로 집계해 돌려줍니다.

    `confirmed`/`expired` 분담안으로 실시간 집계한 **미저장** 인스턴스를 반환한다
    (`generated_at` 은 집계 시각). 저장·알림 등 부수 효과는 없다. 분담안이 없으면 None.

    Args:
        home: 대상 집.
        week_start: 대상 주차의 월요일 날짜.

    Returns:
        미저장 WeeklyReport, 또는 분담안이 없으면 None.
    """
    assignment = find_report_target(home=home, week_start=week_start)
    if assignment is None:
        return None

    return WeeklyReport(
        home=home, week_start=week_start, generated_at=timezone.now(), **build_report_payload(assignment)
    )

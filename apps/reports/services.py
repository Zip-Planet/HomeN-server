"""주간 리포트 생성.

매주 일요일 21:00(관리 커맨드 `generate_weekly_reports`)에 그 주차 분담안의
수행 결과를 집계해 스냅샷으로 저장한다. 화면(R1_WeeklyReport)의 빈 상태 문구
"리포트는 매주 일요일 저녁 9시에 자동으로 생성돼요" 가 이 스케줄이다.
"""

from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from apps.homes.models import Home, HomeMember, WeeklyAssignment
from apps.homes.selectors import get_week_completions
from apps.homes.services import week_start_of
from apps.reports.models import WeeklyReport


def _percent(part: int, whole: int) -> int:
    return round(part * 100 / whole) if whole > 0 else 0


def build_report_payload(assignment: WeeklyAssignment) -> dict:
    """분담안 한 건에서 리포트 집계값을 계산합니다 (저장은 하지 않음).

    - 구성원 통계는 **배정 기준**(assigned) 과 **완료 기준**(completed) 을 함께 담는다.
      화면이 `완료 · 7/7건` 처럼 둘 다 보여주기 때문이다.
    - 완료 포인트는 실제 완료자(`ChoreCompletion.completed_by`) 기준으로 합산한다
      (도움 카드로 담당자가 바뀔 수 있으므로 배정 담당자와 다를 수 있다).
    - 하이라이트는 집안일명 기준 완료/미완료 횟수 최대값이다.

    Args:
        assignment: 대상 분담안 (items prefetch 가정).

    Returns:
        `WeeklyReport` 필드에 대응하는 딕셔너리.
    """
    items = list(assignment.items.all())
    completions = get_week_completions(assignment)

    assigned_by_user: dict[int, int] = {}
    completed_by_user: dict[int, int] = {}
    points_by_user: dict[int, int] = {}
    user_by_id = {}

    done_by_name: dict[str, int] = {}
    missed_by_name: dict[str, int] = {}
    completed_count = 0

    for item in items:
        if item.assignee is not None:
            assigned_by_user[item.assignee_id] = assigned_by_user.get(item.assignee_id, 0) + 1
            user_by_id[item.assignee_id] = item.assignee

        item_date = assignment.week_start + timedelta(days=item.weekday)
        completion = completions.get((item.home_chore_id, item_date))
        if completion is None:
            missed_by_name[item.chore_name] = missed_by_name.get(item.chore_name, 0) + 1
            continue

        completed_count += 1
        done_by_name[item.chore_name] = done_by_name.get(item.chore_name, 0) + 1

        completer = completion.completed_by
        if completer is None:
            continue
        completed_by_user[completer.id] = completed_by_user.get(completer.id, 0) + 1
        points_by_user[completer.id] = points_by_user.get(completer.id, 0) + item.point
        user_by_id[completer.id] = completer

    # 배정도 완료도 없는 구성원까지 0건으로 노출한다 (화면이 전원을 보여줌).
    for member in HomeMember.objects.select_related("user").filter(home=assignment.home):
        user_by_id.setdefault(member.user_id, member.user)

    member_stats = [
        {
            "uid": str(user.uid),
            "name": user.name,
            "profile_image": user.profile_image,
            "assigned_count": assigned_by_user.get(user_id, 0),
            "completed_count": completed_by_user.get(user_id, 0),
            "point": points_by_user.get(user_id, 0),
        }
        for user_id, user in user_by_id.items()
    ]
    member_stats.sort(key=lambda row: (-row["point"], -row["completed_count"], row["name"]))

    mvp_user = None
    if points_by_user:
        top_id = max(points_by_user, key=lambda uid: (points_by_user[uid], completed_by_user[uid]))
        mvp_user = user_by_id[top_id]

    def _top(counter: dict[str, int]) -> dict | None:
        if not counter:
            return None
        name = max(counter, key=lambda key: (counter[key], key))
        return {"name": name, "count": counter[name]}

    return {
        "total_count": len(items),
        "completed_count": completed_count,
        "progress_rate": _percent(completed_count, len(items)),
        "mvp_user": mvp_user,
        "mvp_name": mvp_user.name if mvp_user else "",
        "mvp_point": points_by_user.get(mvp_user.id, 0) if mvp_user else 0,
        "mvp_completed_count": completed_by_user.get(mvp_user.id, 0) if mvp_user else 0,
        "member_stats": member_stats,
        "most_done": _top(done_by_name),
        "most_missed": _top(missed_by_name),
    }


def generate_report(*, home: Home, week_start: date) -> WeeklyReport | None:
    """한 집·한 주차의 리포트를 생성(또는 갱신)합니다.

    해당 주차에 분담안이 없으면 리포트를 만들지 않는다 (화면은 "주간 리포트가
    없어요" 빈 상태). 이미 있으면 최신 집계로 덮어써 멱등성을 보장한다.

    Args:
        home: 대상 집.
        week_start: 대상 주차의 월요일 날짜.

    Returns:
        생성/갱신된 WeeklyReport, 또는 분담안이 없으면 None.
    """
    assignment = (
        WeeklyAssignment.objects.prefetch_related("items__assignee")
        .filter(home=home, week_start=week_start)
        .exclude(status=WeeklyAssignment.Status.PROPOSED)
        .first()
    )
    if assignment is None:
        return None

    payload = build_report_payload(assignment)
    with transaction.atomic():
        report, _created = WeeklyReport.objects.update_or_create(
            home=home, week_start=week_start, defaults=payload
        )

    _announce_report(report)
    return report


def _announce_report(report: WeeklyReport) -> None:
    """주간 리포트 도착을 보드 봇 카드와 알림으로 알립니다."""
    from apps.boards.models import BotCardKind
    from apps.boards.services import publish_bot_card
    from apps.notifications.models import NotificationCategory
    from apps.notifications.services import notify_home

    publish_bot_card(
        home=report.home,
        kind=BotCardKind.WEEKLY_REPORT,
        week_start=report.week_start,
        payload={
            "progress_rate": report.progress_rate,
            "completed_count": report.completed_count,
            "total_count": report.total_count,
            "mvp_name": report.mvp_name,
            "mvp_point": report.mvp_point,
        },
    )
    notify_home(
        home=report.home,
        category=NotificationCategory.REPORT,
        title="이번 주 리포트가 도착했어요",
        body="이번 주 진행률과 Top 멤버를 확인해요.",
        deep_link=f"report:{report.week_start}",
    )


def generate_weekly_reports(*, today: date | None = None) -> tuple[int, int]:
    """모든 활성 집에 대해 이번 주차 리포트를 생성합니다 (매주 일요일 21:00).

    Args:
        today: 기준 날짜 (테스트용 주입). None 이면 서버 로컬 날짜.

    Returns:
        (생성/갱신 건수, 스킵 건수) 튜플.
    """
    week_start = week_start_of(today or timezone.localdate())
    created = skipped = 0
    for home in Home.objects.filter(status=Home.Status.ACTIVE):
        if generate_report(home=home, week_start=week_start) is None:
            skipped += 1
        else:
            created += 1
    return created, skipped

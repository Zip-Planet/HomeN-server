from datetime import date, timedelta

from django.db.models import QuerySet
from django.utils import timezone

from apps.homes.models import (
    AssignmentItem,
    Chore,
    ChoreCompletion,
    Home,
    HomeChore,
    HomeChoreNote,
    HomeImageType,
    HomeMember,
    StarterPack,
    WeeklyAssignment,
)
from apps.users.models import User


def get_home_image_choices() -> list[dict]:
    """선택 가능한 집 이미지 enum 목록을 반환합니다.

    Returns:
        [{"id": 1}, {"id": 2}, ...] 형식의 딕셔너리 목록.
    """
    return [{"id": value} for value, _ in HomeImageType.choices]


def get_user_home(user: User) -> Home | None:
    """유저가 속한 집을 반환합니다. 없으면 None을 반환합니다.

    Args:
        user: 조회할 User 인스턴스.

    Returns:
        유저가 속한 Home 인스턴스 또는 None.
    """
    try:
        membership = (
            HomeMember.objects
            .select_related("home")
            .prefetch_related("home__members__user")
            .get(user=user)
        )
        return membership.home
    except HomeMember.DoesNotExist:
        return None


def get_user_membership(user: User) -> HomeMember | None:
    """유저의 집 멤버십을 반환합니다. 없으면 None을 반환합니다.

    Args:
        user: 조회할 User 인스턴스.

    Returns:
        유저의 HomeMember 인스턴스 또는 None.
    """
    return HomeMember.objects.select_related("home").filter(user=user).first()


def get_home_by_invite_code(code: str) -> Home | None:
    """초대코드로 활성 집을 조회합니다. 없으면 None을 반환합니다.

    Args:
        code: 6자리 초대코드 (대소문자 무관).

    Returns:
        해당 Home 인스턴스 또는 None.
    """
    try:
        return (
            Home.objects.prefetch_related("members__user")
            .get(invite_code=code.upper(), status=Home.Status.ACTIVE)
        )
    except Home.DoesNotExist:
        return None


def get_starter_packs() -> QuerySet[StarterPack]:
    """모든 스타터팩 목록을 반환합니다."""
    return StarterPack.objects.all()


def get_home_chores(home: Home) -> QuerySet[HomeChore]:
    """집에 배정된 **활성** 집안일 목록을 반환합니다.

    삭제(비활성화)된 집안일은 목록에서 제외된다 — 히스토리 보존을 위해 row 는
    남아있지만 리스트/분담안 대상이 아니다.

    Args:
        home: 조회할 Home 인스턴스.

    Returns:
        HomeChore QuerySet (chore 관계 prefetch 포함).
    """
    return HomeChore.objects.select_related("chore").filter(home=home, is_active=True).order_by("id")


def get_user_home_chore(user: User, home_chore_id: int) -> HomeChore | None:
    """유저의 집에 속한 HomeChore 한 건을 반환합니다. 없거나 다른 집이면 None.

    삭제(비활성화)된 집안일도 반환한다 — 상세 화면에서 "삭제된 집안일" 안내를
    위해 조회는 허용하며, 응답의 `is_active` 로 구분한다.

    Args:
        user: 호출 유저.
        home_chore_id: 조회할 HomeChore PK.

    Returns:
        본인 집의 HomeChore (chore prefetch 포함) 또는 None.
    """
    membership = get_user_membership(user)
    if membership is None:
        return None
    return (
        HomeChore.objects.select_related("chore")
        .filter(id=home_chore_id, home=membership.home)
        .first()
    )


def get_starter_pack_chores(starter_pack_id: int) -> QuerySet[Chore]:
    """특정 스타터팩의 집안일 목록을 반환합니다.

    Args:
        starter_pack_id: 조회할 StarterPack PK.

    Returns:
        해당 스타터팩의 Chore QuerySet.
    """
    return Chore.objects.filter(starter_pack_id=starter_pack_id).order_by("id")


def get_weekly_progress(home_chore: HomeChore, today: date | None = None) -> list[dict]:
    """이번 주(월~일) 7일치 요일별 진행상태 배열을 반환합니다.

    상태값:
    - ``completed``: 그 요일에 해당하는 이번 주 날짜에 ChoreCompletion 이 존재.
        ``completed_by`` 가 함께 채워짐 (탈퇴 유저면 None).
    - ``incomplete``: 이번 주 분담안에 배정됐거나 ``chore.repeat_days`` 에 포함된
        요일이지만 완료 이력이 없음.
    - ``not_scheduled``: 배정도 반복 요일도 아닌 날.

    ``assignee`` 는 이번 주 분담안(`AssignmentItem`)의 담당자다 — 상세 화면이
    요일별로 "담당자 + 완료/미완료" 를 노출하기 때문이다. 분담안이 없는 주차나
    배정되지 않은 요일은 None 이며, 이때 상태는 ``repeat_days`` 로 판단한다.
    담당자와 실제 완료자(``completed_by``)는 다를 수 있다 (도움 카드로 대신 수행).

    Args:
        home_chore: 대상 HomeChore (관계 로딩은 호출 측 책임 — chore prefetch 가정).
        today: 기준 날짜 (테스트용 주입). None 이면 서버 로컬 날짜를 사용.

    Returns:
        7개 dict 의 리스트 (0=월 ~ 6=일). 각 원소는 ``{"weekday", "label",
        "status", "assignee", "completed_by"}`` 키를 가진다.
    """
    today = today or timezone.localdate()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    completions_by_date = {
        c.date: c
        for c in home_chore.completions.select_related("completed_by").filter(
            date__range=(monday, sunday)
        )
    }
    repeat_days = set(home_chore.chore.repeat_days)
    assignee_by_weekday = {
        item.weekday: item.assignee
        for item in AssignmentItem.objects.select_related("assignee").filter(
            home_chore=home_chore, assignment__week_start=monday
        )
    }

    progress: list[dict] = []
    for weekday in range(7):
        target_date = monday + timedelta(days=weekday)
        completion = completions_by_date.get(target_date)
        if completion is not None:
            status_value = "completed"
            completed_by = _serialize_completed_by(completion.completed_by)
        elif weekday in assignee_by_weekday or weekday in repeat_days:
            status_value = "incomplete"
            completed_by = None
        else:
            status_value = "not_scheduled"
            completed_by = None

        progress.append({
            "weekday": weekday,
            "label": Chore.Weekday(weekday).label,
            "status": status_value,
            "assignee": _serialize_completed_by(assignee_by_weekday.get(weekday)),
            "completed_by": completed_by,
        })

    return progress


def _serialize_completed_by(user: User | None) -> dict | None:
    if user is None:
        return None
    return {
        "uid": str(user.uid),
        "name": user.name,
        "profile_image": user.profile_image,
    }


def get_home_chore_notes(user: User, home_chore_id: int) -> QuerySet[HomeChoreNote] | None:
    """유저의 집에 속한 HomeChore 의 메모 목록을 반환합니다.

    Args:
        user: 호출 유저.
        home_chore_id: 대상 HomeChore PK.

    Returns:
        메모 QuerySet (id 오름차순, author prefetch 포함). 본인 집의 chore 가
        아니면 None.
    """
    membership = get_user_membership(user)
    if membership is None:
        return None
    if not HomeChore.objects.filter(id=home_chore_id, home=membership.home).exists():
        return None
    return (
        HomeChoreNote.objects.select_related("author")
        .filter(home_chore_id=home_chore_id)
        .order_by("id")
    )


def get_week_assignment(home: Home, week_start: date) -> WeeklyAssignment | None:
    """특정 주차의 분담안을 반환합니다. 없으면 None.

    한 집·한 주차에는 분담안이 최대 1건만 존재한다 (proposed/confirmed 각각
    partial unique + 상태 전이가 같은 row 에서 일어남).

    Args:
        home: 대상 Home 인스턴스.
        week_start: 주차의 월요일 날짜.

    Returns:
        items(+assignee) 를 prefetch 한 WeeklyAssignment 또는 None.
    """
    return (
        WeeklyAssignment.objects
        .prefetch_related("items__assignee")
        .filter(home=home, week_start=week_start)
        .first()
    )


def get_completed_item_keys(assignment: WeeklyAssignment) -> set[tuple[int, date]]:
    """분담안 주차에 완료된 (home_chore_id, date) 키 집합을 반환합니다.

    분담안 항목의 완료 여부는 별도 컬럼 없이 기존 `ChoreCompletion` 과 조인해
    계산한다 — 항목의 실행 날짜는 week_start + weekday.

    Args:
        assignment: 대상 분담안 (items prefetch 가정).

    Returns:
        완료된 (home_chore_id, 완료 날짜) 튜플 집합.
    """
    week_start = assignment.week_start
    week_end = week_start + timedelta(days=6)
    home_chore_ids = {item.home_chore_id for item in assignment.items.all() if item.home_chore_id}
    completions = ChoreCompletion.objects.filter(
        home_chore_id__in=home_chore_ids, date__range=(week_start, week_end)
    ).values_list("home_chore_id", "date")
    return set(completions)


def get_week_completions(assignment: WeeklyAssignment) -> dict[tuple[int, date], ChoreCompletion]:
    """분담안 주차의 완료 이력을 (home_chore_id, date) 키로 매핑해 반환합니다.

    `get_completed_item_keys` 와 달리 완료자(`completed_by`) 까지 필요할 때 사용한다
    — 기여도/MVP 집계는 배정 담당자가 아니라 **실제 완료자** 기준이어야 하기
    때문이다 (도움 카드로 담당자가 바뀔 수 있다).

    Args:
        assignment: 대상 분담안 (items prefetch 가정).

    Returns:
        {(home_chore_id, 완료 날짜): ChoreCompletion} 딕셔너리.
    """
    week_start = assignment.week_start
    week_end = week_start + timedelta(days=6)
    home_chore_ids = {item.home_chore_id for item in assignment.items.all() if item.home_chore_id}
    completions = ChoreCompletion.objects.select_related("completed_by").filter(
        home_chore_id__in=home_chore_ids, date__range=(week_start, week_end)
    )
    return {(c.home_chore_id, c.date): c for c in completions}


def _serialize_member(user: User | None) -> dict | None:
    """대시보드/리포트 공통 멤버 표현 `{uid, name, profile_image}`."""
    if user is None:
        return None
    return {"uid": str(user.uid), "name": user.name, "profile_image": user.profile_image}


def _percent(part: int, whole: int) -> int:
    """0으로 나누기를 방지한 백분율(반올림 정수)."""
    if whole <= 0:
        return 0
    return round(part * 100 / whole)


def summarize_week_assignment(
    assignment: WeeklyAssignment | None, *, user: User
) -> dict:
    """한 주차 분담안의 진행률·기여도·MVP 를 집계합니다.

    - 진행률: 완료 항목 수 / 전체 항목 수.
    - 기여도: 내가 완료한 포인트 / 집 전체 완료 포인트 (완료자 기준).
    - MVP: 완료 포인트가 가장 높은 구성원 (동점이면 완료 건수가 많은 쪽).

    Args:
        assignment: 대상 분담안. None 이면 0값 요약을 반환한다.
        user: 기여도 계산 기준 유저.

    Returns:
        `{week_start, status, total_count, completed_count, progress_rate,
        my_contribution_rate, mvp}` 딕셔너리.
    """
    empty = {
        "week_start": None,
        "status": None,
        "total_count": 0,
        "completed_count": 0,
        "progress_rate": 0,
        "my_contribution_rate": 0,
        "mvp": None,
    }
    if assignment is None:
        return empty

    items = list(assignment.items.all())
    completions = get_week_completions(assignment)

    completed_count = 0
    points_by_user: dict[int, int] = {}
    counts_by_user: dict[int, int] = {}
    user_by_id: dict[int, User] = {}

    for item in items:
        completion = completions.get((item.home_chore_id, assignment.week_start + timedelta(days=item.weekday)))
        if completion is None:
            continue
        completed_count += 1
        completer = completion.completed_by
        if completer is None:
            continue
        points_by_user[completer.id] = points_by_user.get(completer.id, 0) + item.point
        counts_by_user[completer.id] = counts_by_user.get(completer.id, 0) + 1
        user_by_id[completer.id] = completer

    total_points = sum(points_by_user.values())
    mvp = None
    if points_by_user:
        top_id = max(points_by_user, key=lambda uid: (points_by_user[uid], counts_by_user[uid]))
        mvp = {
            **_serialize_member(user_by_id[top_id]),
            "point": points_by_user[top_id],
            "completed_count": counts_by_user[top_id],
        }

    return {
        "week_start": assignment.week_start,
        "status": assignment.status,
        "total_count": len(items),
        "completed_count": completed_count,
        "progress_rate": _percent(completed_count, len(items)),
        "my_contribution_rate": _percent(points_by_user.get(user.id, 0), total_points),
        "mvp": mvp,
    }


def get_home_dashboard(*, user: User, today: date | None = None) -> dict | None:
    """홈 대시보드(T1_HomeDashboard) 집계를 한 번에 반환합니다.

    화면 구성: 이번 주 진행률 / 기여도 / 우리집 MVP / 다음 주 분담안 상태 라벨 /
    이번 주 항목 목록(멤버 필터 탭).

    Args:
        user: 조회 유저.
        today: 기준 날짜 (테스트용 주입). None 이면 서버 로컬 날짜.

    Returns:
        대시보드 딕셔너리. 집이 없으면 None.
    """
    today = today or timezone.localdate()
    membership = get_user_membership(user)
    if membership is None:
        return None

    home = membership.home
    this_week_start = today - timedelta(days=today.weekday())
    next_week_start = this_week_start + timedelta(days=7)

    this_week = get_week_assignment(home, this_week_start)
    next_week = WeeklyAssignment.objects.filter(home=home, week_start=next_week_start).first()

    return {
        "home": {
            "id": home.id,
            "name": home.name,
            "image": home.image,
            "member_count": HomeMember.objects.filter(home=home).count(),
        },
        "this_week": {
            **summarize_week_assignment(this_week, user=user),
            "week_start": this_week_start,
            "assignment_id": this_week.id if this_week else None,
        },
        "next_week": {
            "week_start": next_week_start,
            "assignment_id": next_week.id if next_week else None,
            "status": next_week.status if next_week else None,
        },
        "assignment": this_week,
    }


def get_assignment_changes(assignment: WeeklyAssignment) -> dict:
    """분담안 생성 시점 이후의 집안일 변경을 항목 단위로 계산합니다.

    분담안 항목은 생성 시점 **스냅샷**이라, 이후 추가된 집안일은 항목 자체가
    없고 수정된 집안일은 스냅샷과 원본이 어긋난다. 화면(T3A 제안됨)은 이를
    행 단위 `NEW` / `UPDATE` 배지로 노출하므로 다음 3종을 구분해 돌려준다.

    - ``new_entries``: 생성 이후 추가돼 분담안에 없는 (집안일, 요일) 행 — `NEW`.
    - ``updated_item_ids``: 스냅샷과 현재 원본이 다른 항목 — `UPDATE`.
      (이름/카테고리/난이도/포인트 변경, 또는 반복 요일에서 빠진 요일)
    - ``removed_item_ids``: 원본이 삭제(비활성화)된 항목.

    Args:
        assignment: 대상 분담안 (items prefetch 가정).

    Returns:
        `{has_changes, new_entries, updated_item_ids, removed_item_ids}` 딕셔너리.
    """
    items = list(assignment.items.all())
    home_chores = {
        hc.id: hc
        for hc in HomeChore.objects.select_related("chore").filter(home=assignment.home)
    }

    updated_item_ids: list[int] = []
    removed_item_ids: list[int] = []
    covered: set[tuple[int, int]] = set()

    for item in items:
        home_chore = home_chores.get(item.home_chore_id) if item.home_chore_id else None
        if home_chore is None or not home_chore.is_active:
            removed_item_ids.append(item.id)
            continue

        covered.add((home_chore.id, item.weekday))
        chore = home_chore.chore
        snapshot_changed = (
            item.chore_name != chore.name
            or item.category != chore.category
            or item.difficulty != chore.difficulty
            or item.point != chore.point
            or item.weekday not in set(chore.repeat_days)
        )
        if snapshot_changed:
            updated_item_ids.append(item.id)

    new_entries: list[dict] = []
    for home_chore in home_chores.values():
        if not home_chore.is_active:
            continue
        chore = home_chore.chore
        for weekday in sorted(set(chore.repeat_days)):
            if (home_chore.id, weekday) in covered:
                continue
            new_entries.append({
                "home_chore_id": home_chore.id,
                "chore_name": chore.name,
                "category": chore.category,
                "difficulty": chore.difficulty,
                "point": chore.point,
                "weekday": weekday,
            })

    return {
        "has_changes": bool(new_entries or updated_item_ids or removed_item_ids),
        "new_entries": new_entries,
        "updated_item_ids": updated_item_ids,
        "removed_item_ids": removed_item_ids,
    }


MAX_HISTORY_WEEKS = 4
"""히스토리 화면에서 되돌아볼 수 있는 최대 주차 수 (T3C_PlanHistory)."""


def get_assignment_history(
    *, home: Home, weeks_ago: int = 1, today: date | None = None
) -> dict:
    """과거 주차 분담안 히스토리를 반환합니다 (최대 4주 전).

    화면은 `1주 전 >` 셀렉터로 주차를 고르고 그 주차의 분담안을 보여준다.
    한 번의 호출로 셀렉터 목록(`weeks`)과 선택된 주차의 분담안(`selected`)을
    함께 돌려준다. 분담안이 없는 주차는 `assignment_id`/`selected` 가 None 이며
    화면은 "해당 주차의 분담안 기록이 없어요" 를 노출한다.

    Args:
        home: 대상 집.
        weeks_ago: 선택된 과거 주차 (1=지난 주 ~ 4=4주 전).
        today: 기준 날짜 (테스트용 주입). None 이면 서버 로컬 날짜.

    Returns:
        `{weeks: [{week_start, weeks_ago, assignment_id, status}], selected}` 딕셔너리.
        `selected` 는 WeeklyAssignment 인스턴스 또는 None.
    """
    today = today or timezone.localdate()
    this_week_start = today - timedelta(days=today.weekday())

    week_starts = [this_week_start - timedelta(weeks=n) for n in range(1, MAX_HISTORY_WEEKS + 1)]
    assignments = {
        a.week_start: a
        for a in WeeklyAssignment.objects.prefetch_related("items__assignee").filter(
            home=home, week_start__in=week_starts
        )
    }

    weeks = [
        {
            "week_start": week_start,
            "weeks_ago": n,
            "assignment_id": assignments[week_start].id if week_start in assignments else None,
            "status": assignments[week_start].status if week_start in assignments else None,
        }
        for n, week_start in enumerate(week_starts, start=1)
    ]

    return {
        "weeks": weeks,
        "selected": assignments.get(this_week_start - timedelta(weeks=weeks_ago)),
    }

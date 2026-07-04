from datetime import date, timedelta

from django.db.models import QuerySet
from django.utils import timezone

from apps.homes.models import (
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
    - ``incomplete``: ``chore.repeat_days`` 에 포함된 요일이지만 이번 주 완료 이력 없음.
    - ``not_scheduled``: ``chore.repeat_days`` 에 포함되지 않은 요일.

    Args:
        home_chore: 대상 HomeChore (관계 로딩은 호출 측 책임 — chore prefetch 가정).
        today: 기준 날짜 (테스트용 주입). None 이면 서버 로컬 날짜를 사용.

    Returns:
        7개 dict 의 리스트 (0=월 ~ 6=일). 각 원소는 ``{"weekday", "label",
        "status", "completed_by"}`` 키를 가진다.
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

    progress: list[dict] = []
    for weekday in range(7):
        target_date = monday + timedelta(days=weekday)
        completion = completions_by_date.get(target_date)
        if completion is not None:
            status_value = "completed"
            completed_by = _serialize_completed_by(completion.completed_by)
        elif weekday in repeat_days:
            status_value = "incomplete"
            completed_by = None
        else:
            status_value = "not_scheduled"
            completed_by = None

        progress.append({
            "weekday": weekday,
            "label": Chore.Weekday(weekday).label,
            "status": status_value,
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

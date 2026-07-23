"""리워드 읽기 전용 쿼리.

포인트 잔액은 별도 컬럼 없이 계산한다 — **획득 포인트**(집안일 완료 이력의
분담안 스냅샷 포인트 합) 에서 **사용 포인트**(수령한 리워드의 `claimed_point`
합) 를 뺀 값이다. 완료를 취소하면 자동으로 잔액도 줄어들도록 파생값으로 둔다.
"""

from datetime import timedelta

from django.db.models import QuerySet, Sum

from apps.homes.models import AssignmentItem, ChoreCompletion, Home, HomeMember
from apps.rewards.models import Reward, RewardClaim
from apps.users.models import User


def get_earned_points(*, user: User) -> int:
    """유저가 집안일 완료로 획득한 누적 포인트를 반환합니다.

    완료 이력(`ChoreCompletion`)과 같은 (집안일, 날짜) 의 분담안 항목을 이어
    그 시점 스냅샷 포인트를 합산한다. 분담안 항목이 없는 완료(과거 데이터 등)는
    0점으로 취급한다.

    Args:
        user: 대상 유저.

    Returns:
        누적 획득 포인트.
    """
    completions = ChoreCompletion.objects.filter(completed_by=user).values_list("home_chore_id", "date")
    if not completions:
        return 0

    items = AssignmentItem.objects.select_related("assignment").filter(
        home_chore_id__in={home_chore_id for home_chore_id, _ in completions}
    )
    point_by_key = {
        (item.home_chore_id, item.assignment.week_start + timedelta(days=item.weekday)): item.point
        for item in items
    }
    return sum(point_by_key.get(key, 0) for key in completions)


def get_spent_points(*, user: User) -> int:
    """유저가 리워드 수령으로 사용한 누적 포인트를 반환합니다."""
    return RewardClaim.objects.filter(claimed_by=user).aggregate(total=Sum("claimed_point"))["total"] or 0


def get_point_balance(*, user: User) -> int:
    """유저의 현재 리워드 포인트 잔액 (획득 − 사용). 음수는 0으로 절삭한다."""
    return max(get_earned_points(user=user) - get_spent_points(user=user), 0)


def get_home_rewards(home: Home) -> QuerySet[Reward]:
    """집의 리워드 목록을 반환합니다 (수령 이력 prefetch 포함)."""
    return (
        Reward.objects.select_related("created_by", "claim__claimed_by")
        .filter(home=home)
        .order_by("id")
    )


def get_member_progress(*, reward: Reward) -> list[dict]:
    """리워드 상세의 "구성원 현황" — 구성원별 보유 포인트·달성률·순위.

    보유 포인트 내림차순으로 정렬해 1등부터 순위를 매긴다 (동점은 같은 순서로
    나열되며 순위는 목록 인덱스를 따른다).

    Args:
        reward: 대상 리워드.

    Returns:
        `[{rank, uid, name, profile_image, point, achievement_rate}]` 목록.
    """
    members = HomeMember.objects.select_related("user").filter(home=reward.home)
    rows = [
        {
            "uid": str(m.user.uid),
            "name": m.user.name,
            "profile_image": m.user.profile_image,
            "point": get_point_balance(user=m.user),
        }
        for m in members
    ]
    rows.sort(key=lambda r: -r["point"])

    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
        row["achievement_rate"] = (
            min(round(row["point"] * 100 / reward.goal_point), 100) if reward.goal_point else 0
        )
    return rows


def get_reward_status(*, reward: Reward, user: User) -> str:
    """리워드 상태를 계산합니다 — `claimed` / `claimable` / `in_progress`.

    - `claimed`: 이미 수령됨 (집당 1회).
    - `claimable`: 미수령 + 요청 유저의 잔액이 목표 포인트 이상.
    - `in_progress`: 그 외.
    """
    if hasattr(reward, "claim"):
        return "claimed"
    if get_point_balance(user=user) >= reward.goal_point:
        return "claimable"
    return "in_progress"


def get_user_reward(*, user: User, reward_id: int) -> Reward | None:
    """요청 유저의 집에 속한 리워드 한 건을 반환합니다. 없거나 다른 집이면 None."""
    membership = HomeMember.objects.select_related("home").filter(user=user).first()
    if membership is None:
        return None
    return (
        Reward.objects.select_related("created_by", "claim__claimed_by")
        .filter(id=reward_id, home=membership.home)
        .first()
    )

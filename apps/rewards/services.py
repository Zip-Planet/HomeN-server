"""리워드 쓰기 오케스트레이션.

정책 요약 (Figma T4_RewardMain / W1_RewardDetail / W2_RewardCreateEdit):
- 리워드는 같은 집 구성원이면 누구나 등록할 수 있고, 작성자(`created_by`)를 남긴다.
- 수령은 **집당 1회** — 한 번 수령되면 잠기고 "받기 완료된 리워드예요" 가 된다.
- 수령하려면 요청자의 포인트 잔액이 목표 포인트 이상이어야 한다.
- 수령 시점의 목표 포인트를 스냅샷(`claimed_point`)으로 남겨 이후 수정에 흔들리지 않게 한다.
"""

from django.db import transaction

from apps.homes.selectors import get_user_membership
from apps.rewards.models import Reward, RewardClaim
from apps.rewards.selectors import get_point_balance
from apps.users.models import User


class RewardError(Exception):
    """리워드 관련 오류의 공통 부모. `code` 는 API 에러 코드로 노출된다."""

    code = "reward_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class RewardNotFoundError(RewardError):
    """리워드가 없거나 본인 집의 것이 아닐 때 발생합니다 (404)."""

    code = "not_found"


class HomeRequiredError(RewardError):
    """집에 속하지 않은 유저가 리워드를 다룰 때 발생합니다 (404)."""

    code = "not_found"


class RewardAlreadyClaimedError(RewardError):
    """이미 수령된 리워드를 수령·수정·삭제하려 할 때 발생합니다 (409)."""

    code = "already_claimed"


class NotEnoughPointsError(RewardError):
    """잔액이 목표 포인트에 미치지 못할 때 발생합니다 (400)."""

    code = "not_enough_points"


def _get_home(user: User):
    membership = get_user_membership(user)
    if membership is None:
        raise HomeRequiredError("속한 집이 없습니다.")
    return membership.home


def _get_reward_in_user_home(*, user: User, reward_id: int) -> Reward:
    home = _get_home(user)
    reward = (
        Reward.objects.select_related("created_by")
        .filter(id=reward_id, home=home)
        .first()
    )
    if reward is None:
        raise RewardNotFoundError("리워드를 찾을 수 없습니다.")
    return reward


def create_reward(*, user: User, name: str, goal_point: int) -> Reward:
    """리워드를 등록합니다 (같은 집 구성원이면 누구나).

    Args:
        user: 등록하는 User.
        name: 리워드 이름.
        goal_point: 목표 포인트.

    Returns:
        생성된 Reward 인스턴스.

    Raises:
        HomeRequiredError: 속한 집이 없는 경우.
    """
    home = _get_home(user)
    return Reward.objects.create(home=home, name=name, goal_point=goal_point, created_by=user)


def update_reward(*, user: User, reward_id: int, fields: dict) -> Reward:
    """리워드를 부분 수정합니다. 이미 수령된 리워드는 수정할 수 없습니다.

    Args:
        user: 호출 유저.
        reward_id: 대상 리워드 PK.
        fields: 변경할 필드 부분 dict (name / goal_point).

    Returns:
        최신 상태의 Reward 인스턴스.

    Raises:
        RewardNotFoundError: 본인 집의 리워드가 아닌 경우.
        RewardAlreadyClaimedError: 이미 수령된 경우.
    """
    reward = _get_reward_in_user_home(user=user, reward_id=reward_id)
    if RewardClaim.objects.filter(reward=reward).exists():
        raise RewardAlreadyClaimedError("이미 수령된 리워드는 수정할 수 없습니다.")

    updates = {k: v for k, v in fields.items() if k in ("name", "goal_point")}
    if not updates:
        return reward

    for key, value in updates.items():
        setattr(reward, key, value)
    reward.save(update_fields=[*updates.keys(), "updated_at"])
    return reward


def delete_reward(*, user: User, reward_id: int) -> None:
    """리워드를 삭제합니다. 이미 수령된 리워드는 이력 보존을 위해 삭제할 수 없습니다.

    Raises:
        RewardNotFoundError: 본인 집의 리워드가 아닌 경우.
        RewardAlreadyClaimedError: 이미 수령된 경우.
    """
    reward = _get_reward_in_user_home(user=user, reward_id=reward_id)
    if RewardClaim.objects.filter(reward=reward).exists():
        raise RewardAlreadyClaimedError("이미 수령된 리워드는 삭제할 수 없습니다.")
    reward.delete()


def claim_reward(*, user: User, reward_id: int) -> RewardClaim:
    """리워드를 수령합니다 (집당 1회, 잔액이 목표 포인트 이상일 때).

    Args:
        user: 수령하는 User.
        reward_id: 대상 리워드 PK.

    Returns:
        생성된 RewardClaim 인스턴스.

    Raises:
        RewardNotFoundError: 본인 집의 리워드가 아닌 경우.
        RewardAlreadyClaimedError: 이미 수령된 경우.
        NotEnoughPointsError: 잔액이 목표 포인트 미만인 경우.
    """
    reward = _get_reward_in_user_home(user=user, reward_id=reward_id)

    with transaction.atomic():
        if RewardClaim.objects.filter(reward=reward).exists():
            raise RewardAlreadyClaimedError("이미 수령된 리워드입니다.")

        balance = get_point_balance(user=user)
        if balance < reward.goal_point:
            raise NotEnoughPointsError(
                f"포인트가 부족합니다. (보유 {balance}P / 목표 {reward.goal_point}P)"
            )

        claim = RewardClaim.objects.create(
            reward=reward, claimed_by=user, claimed_point=reward.goal_point
        )

    _announce_claim(claim)
    return claim


def _announce_claim(claim: RewardClaim) -> None:
    """리워드 달성을 보드 봇 카드와 알림으로 알립니다."""
    from django.utils import timezone

    from apps.boards.models import BotCardKind
    from apps.boards.services import publish_bot_card
    from apps.homes.services import week_start_of
    from apps.notifications.models import NotificationCategory
    from apps.notifications.services import notify_home

    reward = claim.reward
    publish_bot_card(
        home=reward.home,
        kind=BotCardKind.REWARD_ACHIEVED,
        week_start=week_start_of(timezone.localdate()),
        payload={
            "reward_name": reward.name,
            "goal_point": claim.claimed_point,
            "claimed_by": claim.claimed_by.name if claim.claimed_by else "",
        },
    )
    notify_home(
        home=reward.home,
        category=NotificationCategory.REWARD,
        title=f"리워드가 수령됐어요 ({claim.claimed_by.name if claim.claimed_by else ''})",
        body=f"구성원이 {reward.name} 리워드를 받았어요",
        deep_link=f"reward:{reward.id}",
    )

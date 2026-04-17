import secrets
import string
from typing import Any

from django.db import transaction

from apps.homes.models import Chore, Home, HomeChore, HomeMember, Reward
from apps.users.models import User


class HomeError(Exception):
    """집 관련 일반 오류."""


class AlreadyHasHomeError(HomeError):
    """이미 집이 있는 유저가 집을 생성하거나 참여하려 할 때 발생합니다."""


class HomeNotFoundError(HomeError):
    """초대코드에 해당하는 집이 없을 때 발생합니다."""


# ──────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────


def _generate_invite_code() -> str:
    """중복되지 않는 6자리 초대코드를 생성합니다.

    Returns:
        대문자 영문+숫자 조합 6자리 문자열.
    """
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(6))
        if not Home.objects.filter(invite_code=code).exists():
            return code


# ──────────────────────────────────────────
# 집 생성
# ──────────────────────────────────────────


def create_home(
    *,
    user: User,
    name: str,
    image_id: int,
    chores: list[int],
    rewards: list[dict[str, Any]],
) -> Home:
    """집을 생성하고 요청 유저를 관리자로 등록합니다.

    집안일 ID 목록과 리워드 목록을 함께 받아 하나의 트랜잭션으로 처리합니다.
    빈 리스트를 전달하면 해당 항목은 생성하지 않습니다.

    Args:
        user: 집을 생성하는 User 인스턴스.
        name: 집 이름.
        image_id: 선택된 집 이미지 enum 값.
        chores: 추가할 Chore PK 목록. 빈 리스트면 집안일을 생성하지 않습니다.
        rewards: [{"name": ..., "goal_point": ...}, ...] 형식의 리워드 목록. 빈 리스트면 생성하지 않습니다.

    Returns:
        생성된 Home 인스턴스.

    Raises:
        AlreadyHasHomeError: 이미 집이 있는 경우.
        HomeError: 존재하지 않는 집안일 ID가 포함된 경우.
    """
    if HomeMember.objects.filter(user=user).exists():
        raise AlreadyHasHomeError("이미 속한 집이 있습니다.")

    with transaction.atomic():
        home = Home.objects.create(
            name=name,
            image=image_id,
            invite_code=_generate_invite_code(),
            status=Home.Status.ACTIVE,
        )
        HomeMember.objects.create(home=home, user=user, role=HomeMember.Role.ADMIN)

        if chores:
            chore_ids = list(dict.fromkeys(chores))  # 순서 유지 중복 제거
            chore_objs = list(Chore.objects.filter(pk__in=chore_ids))
            if len(chore_objs) != len(chore_ids):
                raise HomeError("존재하지 않는 집안일이 포함되어 있습니다.")
            HomeChore.objects.bulk_create([HomeChore(home=home, chore=c) for c in chore_objs])

        if rewards:
            Reward.objects.bulk_create(
                [Reward(home=home, name=r["name"], goal_point=r["goal_point"]) for r in rewards]
            )

    return home


# ──────────────────────────────────────────
# 집 참여
# ──────────────────────────────────────────


def join_home(*, user: User, invite_code: str) -> HomeMember:
    """초대코드로 집에 구성원으로 참여합니다.

    Args:
        user: 참여할 User 인스턴스.
        invite_code: 6자리 초대코드.

    Returns:
        생성된 HomeMember 인스턴스.

    Raises:
        AlreadyHasHomeError: 이미 집이 있는 경우.
        HomeNotFoundError: 초대코드에 해당하는 활성 집이 없는 경우.
    """
    if HomeMember.objects.filter(user=user).exists():
        raise AlreadyHasHomeError("이미 속한 집이 있습니다. 기존 집에서 나간 후 참여해 주세요.")

    try:
        home = Home.objects.get(invite_code=invite_code.upper(), status=Home.Status.ACTIVE)
    except Home.DoesNotExist:
        raise HomeNotFoundError("유효하지 않은 초대코드입니다.")

    return HomeMember.objects.create(home=home, user=user, role=HomeMember.Role.MEMBER)

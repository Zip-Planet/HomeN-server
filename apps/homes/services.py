import secrets
import string
from typing import Any

from django.db import transaction

from apps.homes.models import Chore, Home, HomeChore, HomeImage, HomeMember, Reward, StarterPack
from apps.users.models import User


class HomeError(Exception):
    """집 관련 일반 오류."""


class AlreadyHasHomeError(HomeError):
    """이미 집이 있는 유저가 집을 생성하거나 참여하려 할 때 발생합니다."""


class HomeNotFoundError(HomeError):
    """초대코드에 해당하는 집이 없을 때 발생합니다."""


class HomePermissionError(HomeError):
    """관리자가 아닌 유저가 관리자 전용 작업을 시도할 때 발생합니다."""


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


def _assert_is_admin(home: Home, user: User) -> None:
    """유저가 해당 집의 관리자인지 확인합니다.

    Args:
        home: 확인할 Home 인스턴스.
        user: 확인할 User 인스턴스.

    Raises:
        HomePermissionError: 관리자가 아닌 경우.
    """
    if not HomeMember.objects.filter(home=home, user=user, role=HomeMember.Role.ADMIN).exists():
        raise HomePermissionError("관리자만 수행할 수 있는 작업입니다.")


# ──────────────────────────────────────────
# 집 생성 플로우
# ──────────────────────────────────────────


def create_home(*, user: User, name: str, image_id: int) -> Home:
    """집을 생성하고 요청 유저를 관리자로 등록합니다 (1단계).

    Args:
        user: 집을 생성하는 User 인스턴스.
        name: 집 이름.
        image_id: 선택된 HomeImage PK.

    Returns:
        생성된 Home 인스턴스.

    Raises:
        AlreadyHasHomeError: 이미 집이 있는 경우.
        HomeError: 이미지가 존재하지 않는 경우.
    """
    if HomeMember.objects.filter(user=user).exists():
        raise AlreadyHasHomeError("이미 속한 집이 있습니다.")

    try:
        image = HomeImage.objects.get(pk=image_id)
    except HomeImage.DoesNotExist:
        raise HomeError("존재하지 않는 이미지입니다.")

    with transaction.atomic():
        home = Home.objects.create(
            name=name,
            image=image,
            invite_code=_generate_invite_code(),
        )
        HomeMember.objects.create(home=home, user=user, role=HomeMember.Role.ADMIN)

    return home


def add_starter_pack_chores(*, home: Home, user: User, starter_pack_id: int) -> list[Chore]:
    """스타터팩의 집안일 전체를 집에 추가합니다 (2단계).

    기존에 등록된 집안일은 모두 교체됩니다.

    Args:
        home: 대상 Home 인스턴스.
        user: 요청하는 User 인스턴스.
        starter_pack_id: 선택된 StarterPack PK.

    Returns:
        추가된 Chore 인스턴스 목록.

    Raises:
        HomePermissionError: 관리자가 아닌 경우.
        HomeError: 스타터팩이 존재하지 않는 경우.
    """
    _assert_is_admin(home, user)

    try:
        starter_pack = StarterPack.objects.prefetch_related("chores").get(pk=starter_pack_id)
    except StarterPack.DoesNotExist:
        raise HomeError("존재하지 않는 스타터팩입니다.")

    chores = list(starter_pack.chores.all())

    with transaction.atomic():
        home.home_chores.all().delete()
        HomeChore.objects.bulk_create([HomeChore(home=home, chore=chore) for chore in chores])
        home.creation_step = Home.CreationStep.CHORES
        home.save(update_fields=["creation_step", "updated_at"])

    return chores


def add_rewards(*, home: Home, user: User, rewards_data: list[dict[str, Any]]) -> list[Reward]:
    """리워드를 일괄 등록하고 집 생성을 완료합니다 (3단계).

    Args:
        home: 대상 Home 인스턴스.
        user: 요청하는 User 인스턴스.
        rewards_data: [{"name": ..., "goal_point": ...}, ...] 형식의 목록.

    Returns:
        생성된 Reward 인스턴스 목록.

    Raises:
        HomePermissionError: 관리자가 아닌 경우.
    """
    _assert_is_admin(home, user)

    with transaction.atomic():
        rewards = Reward.objects.bulk_create(
            [Reward(home=home, name=r["name"], goal_point=r["goal_point"]) for r in rewards_data]
        )
        home.creation_step = Home.CreationStep.REWARDS
        home.status = Home.Status.ACTIVE
        home.save(update_fields=["creation_step", "status", "updated_at"])

    return rewards


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
        home = Home.objects.get(invite_code=invite_code, status=Home.Status.ACTIVE)
    except Home.DoesNotExist:
        raise HomeNotFoundError("유효하지 않은 초대코드입니다.")

    return HomeMember.objects.create(home=home, user=user, role=HomeMember.Role.MEMBER)

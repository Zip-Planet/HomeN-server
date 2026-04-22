import secrets
import string
from typing import Any

from django.db import transaction

from apps.homes.models import Chore, Home, HomeChore, HomeMember, Reward
from apps.homes.selectors import get_user_membership
from apps.users.models import User


class HomeError(Exception):
    """집 관련 일반 오류."""


class AlreadyHasHomeError(HomeError):
    """이미 집이 있는 유저가 집을 생성하거나 참여하려 할 때 발생합니다."""


class HomeNotFoundError(HomeError):
    """초대코드에 해당하는 집이 없을 때 발생합니다."""


class NotHomeAdminError(HomeError):
    """관리자가 아닌 유저가 관리자 전용 작업을 시도할 때 발생합니다."""


class HomeHasMembersError(HomeError):
    """집에 구성원이 있어 삭제할 수 없을 때 발생합니다."""


class AdminCannotLeaveError(HomeError):
    """관리자가 양도 없이 집을 나가려 할 때 발생합니다."""


class TransferAdminTargetError(HomeError):
    """관리자 양도 대상이 올바르지 않을 때 발생합니다."""


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
    chores: list[dict[str, Any]],
    rewards: list[dict[str, Any]],
) -> Home:
    """집을 생성하고 요청 유저를 관리자로 등록합니다.

    집안일 목록과 리워드 목록을 함께 받아 하나의 트랜잭션으로 처리합니다.
    빈 리스트를 전달하면 해당 항목은 생성하지 않습니다.

    Args:
        user: 집을 생성하는 User 인스턴스.
        name: 집 이름.
        image_id: 선택된 집 이미지 enum 값.
        chores: [{"name": ..., "image": ..., "points": ..., "repeat_days": ..., "difficulty": ...}, ...]
            형식의 집안일 목록. 빈 리스트면 생성하지 않습니다.
        rewards: [{"name": ..., "goal_point": ...}, ...] 형식의 리워드 목록. 빈 리스트면 생성하지 않습니다.

    Returns:
        생성된 Home 인스턴스.

    Raises:
        AlreadyHasHomeError: 이미 집이 있는 경우.
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
            chore_objs = Chore.objects.bulk_create([
                Chore(
                    category=c["category"],
                    name=c["name"],
                    description=c.get("description", ""),
                    repeat_days=c["repeat_days"],
                    difficulty=c["difficulty"],
                )
                for c in chores
            ])
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


# ──────────────────────────────────────────
# 집 삭제
# ──────────────────────────────────────────


def delete_home(*, user: User) -> None:
    """유저가 속한 집을 삭제합니다. 관리자 전용이며 다른 구성원이 없어야 합니다.

    집을 삭제하면 모든 집안일, 리워드가 함께 삭제됩니다.
    단, 향후 구현될 집안일 완료 이력은 유저 FK에 SET_NULL을 사용해 보존합니다.

    Args:
        user: 삭제를 요청한 User 인스턴스.

    Raises:
        NotHomeAdminError: 관리자가 아니거나 집에 속하지 않은 경우.
        HomeHasMembersError: 집에 구성원(관리자 외)이 남아있는 경우.
    """
    membership = get_user_membership(user)
    if membership is None or membership.role != HomeMember.Role.ADMIN:
        raise NotHomeAdminError("관리자만 집을 삭제할 수 있습니다.")

    has_members = HomeMember.objects.filter(home=membership.home, role=HomeMember.Role.MEMBER).exists()
    if has_members:
        raise HomeHasMembersError("구성원이 있는 경우 집을 삭제할 수 없습니다. 구성원이 모두 나간 후 삭제해 주세요.")

    membership.home.delete()


# ──────────────────────────────────────────
# 집 나가기
# ──────────────────────────────────────────


def leave_home(*, user: User) -> None:
    """집을 나갑니다. 구성원만 가능하며 관리자는 양도 후 나갈 수 있습니다.

    Args:
        user: 나가려는 User 인스턴스.

    Raises:
        HomeNotFoundError: 속한 집이 없는 경우.
        AdminCannotLeaveError: 관리자가 양도 없이 나가려는 경우.
    """
    membership = get_user_membership(user)
    if membership is None:
        raise HomeNotFoundError("속한 집이 없습니다.")
    if membership.role == HomeMember.Role.ADMIN:
        raise AdminCannotLeaveError("관리자는 먼저 다른 구성원에게 관리자를 양도해야 합니다.")
    membership.delete()


# ──────────────────────────────────────────
# 관리자 양도
# ──────────────────────────────────────────


def transfer_admin(*, user: User, target_uid: str) -> None:
    """집 관리자 권한을 같은 집의 구성원에게 양도합니다.

    Args:
        user: 현재 관리자인 User 인스턴스.
        target_uid: 관리자를 넘겨받을 구성원의 uid (UUID 문자열).

    Raises:
        NotHomeAdminError: 요청자가 관리자가 아닌 경우.
        TransferAdminTargetError: 대상이 같은 집의 구성원이 아닌 경우.
    """
    my_membership = get_user_membership(user)
    if my_membership is None or my_membership.role != HomeMember.Role.ADMIN:
        raise NotHomeAdminError("관리자만 관리자를 양도할 수 있습니다.")

    try:
        target_membership = HomeMember.objects.get(
            home=my_membership.home,
            user__uid=target_uid,
            role=HomeMember.Role.MEMBER,
        )
    except HomeMember.DoesNotExist:
        raise TransferAdminTargetError("해당 유저는 같은 집의 구성원이 아닙니다.")

    with transaction.atomic():
        my_membership.role = HomeMember.Role.MEMBER
        my_membership.save(update_fields=["role"])
        target_membership.role = HomeMember.Role.ADMIN
        target_membership.save(update_fields=["role"])

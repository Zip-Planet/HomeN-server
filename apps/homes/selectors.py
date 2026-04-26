from django.db.models import QuerySet

from apps.homes.models import Chore, Home, HomeChore, HomeImageType, HomeMember, StarterPack
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
    """집에 배정된 집안일 목록을 반환합니다.

    Args:
        home: 조회할 Home 인스턴스.

    Returns:
        HomeChore QuerySet (chore 관계 prefetch 포함).
    """
    return HomeChore.objects.select_related("chore").filter(home=home).order_by("id")


def get_starter_pack_chores(starter_pack_id: int) -> QuerySet[Chore]:
    """특정 스타터팩의 집안일 목록을 반환합니다.

    Args:
        starter_pack_id: 조회할 StarterPack PK.

    Returns:
        해당 스타터팩의 Chore QuerySet.
    """
    return Chore.objects.filter(starter_pack_id=starter_pack_id).order_by("id")

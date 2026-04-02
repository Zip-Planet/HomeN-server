from django.db.models import QuerySet

from apps.homes.models import Chore, Home, HomeImage, HomeMember, StarterPack
from apps.users.models import User


def get_home_images() -> QuerySet[HomeImage]:
    """모든 프리셋 집 이미지를 반환합니다."""
    return HomeImage.objects.all()


def get_user_home(user: User) -> Home | None:
    """유저가 속한 집을 반환합니다. 없으면 None을 반환합니다.

    Args:
        user: 조회할 User 인스턴스.

    Returns:
        유저가 속한 Home 인스턴스 또는 None.
    """
    try:
        membership = HomeMember.objects.select_related("home__image").get(user=user)
        return membership.home
    except HomeMember.DoesNotExist:
        return None


def get_home_by_invite_code(code: str) -> Home | None:
    """초대코드로 활성 집을 조회합니다. 없으면 None을 반환합니다.

    Args:
        code: 6자리 초대코드.

    Returns:
        해당 Home 인스턴스 또는 None.
    """
    try:
        return (
            Home.objects.select_related("image")
            .prefetch_related("members__user")
            .get(invite_code=code, status=Home.Status.ACTIVE)
        )
    except Home.DoesNotExist:
        return None


def get_starter_packs() -> QuerySet[StarterPack]:
    """모든 스타터팩 목록을 반환합니다."""
    return StarterPack.objects.all()


def get_starter_pack_chores(starter_pack_id: int) -> QuerySet[Chore]:
    """특정 스타터팩의 집안일 목록을 반환합니다.

    Args:
        starter_pack_id: 조회할 StarterPack PK.

    Returns:
        해당 스타터팩의 Chore QuerySet.
    """
    return Chore.objects.filter(starter_pack_id=starter_pack_id).order_by("id")

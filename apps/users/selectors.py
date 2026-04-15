from apps.users.models import SocialAccount, UserProfileImage


def get_social_account(provider: str, provider_id: str) -> SocialAccount | None:
    """provider와 provider_id로 소셜 계정을 조회합니다.

    Args:
        provider: 소셜 제공자 이름 ('kakao' 또는 'apple').
        provider_id: 제공자가 발급한 고유 유저 ID.

    Returns:
        SocialAccount 인스턴스. 없으면 None.
    """
    return SocialAccount.objects.select_related("user").filter(provider=provider, provider_id=provider_id).first()


def get_profile_image_choices() -> list[dict]:
    """선택 가능한 프로필 이미지 enum 목록을 반환합니다.

    Returns:
        [{"id": 1}, {"id": 2}, ...] 형식의 딕셔너리 목록.
    """
    return [{"id": value} for value, _ in UserProfileImage.choices]

from apps.users.models import SocialAccount


def get_social_account(provider: str, provider_id: str) -> SocialAccount | None:
    """provider와 provider_id로 소셜 계정을 조회합니다.

    Args:
        provider: 소셜 제공자 이름 ('kakao' 또는 'apple').
        provider_id: 제공자가 발급한 고유 유저 ID.

    Returns:
        SocialAccount 인스턴스. 없으면 None.
    """
    return SocialAccount.objects.select_related("user").filter(provider=provider, provider_id=provider_id).first()

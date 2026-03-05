import time

import jwt
import requests
from django.conf import settings
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import SocialAccount, User
from apps.users.selectors import get_social_account


class SocialLoginError(Exception):
    pass


# ──────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────

def _issue_tokens(user: User) -> dict[str, str]:
    """유저에게 JWT access/refresh 토큰을 발급합니다.

    Args:
        user: 인증된 User 인스턴스.

    Returns:
        'access'와 'refresh' 토큰 문자열을 담은 딕셔너리.
    """
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def _get_or_create_social_user(*, provider: str, provider_id: str) -> User:
    """소셜 계정으로 기존 유저를 조회하거나 신규 유저를 생성합니다.

    Args:
        provider: 소셜 제공자 이름 ('kakao' 또는 'apple').
        provider_id: 제공자가 발급한 고유 유저 ID.

    Returns:
        소셜 계정에 연결된 User 인스턴스.
    """
    social = get_social_account(provider, provider_id)
    if social:
        return social.user

    with transaction.atomic():
        user = User.objects.create_user()
        SocialAccount.objects.create(user=user, provider=provider, provider_id=provider_id)
    return user


# ──────────────────────────────────────────
# 카카오
# ──────────────────────────────────────────

def _exchange_kakao_code(code: str) -> dict:
    """카카오 인가 코드를 access_token으로 교환합니다.

    Args:
        code: 카카오로부터 받은 인가 코드.

    Returns:
        'access_token'을 포함한 토큰 응답 딕셔너리.

    Raises:
        SocialLoginError: 토큰 교환에 실패한 경우.
    """
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.KAKAO_REST_API_KEY,
        "redirect_uri": settings.KAKAO_REDIRECT_URI,
        "code": code,
    }
    if settings.KAKAO_CLIENT_SECRET:
        data["client_secret"] = settings.KAKAO_CLIENT_SECRET

    response = requests.post(
        "https://kauth.kakao.com/oauth/token",
        data=data,
        timeout=10,
    )
    data = response.json()
    if "access_token" not in data:
        raise SocialLoginError(f"카카오 토큰 교환 실패: {data.get('error_description', data)}")
    return data


def _get_kakao_user_info(access_token: str) -> dict:
    """카카오 API에서 유저 프로필을 조회합니다.

    Args:
        access_token: 카카오 access_token.

    Returns:
        카카오 유저 정보 딕셔너리.

    Raises:
        SocialLoginError: 요청에 실패한 경우.
    """
    response = requests.get(
        "https://kapi.kakao.com/v2/user/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if response.status_code != 200:
        raise SocialLoginError(f"카카오 사용자 정보 조회 실패: {response.status_code} {response.text}")
    return response.json()


def kakao_login(*, code: str) -> dict[str, str]:
    """카카오 OAuth2로 유저를 인증하고 JWT 토큰을 반환합니다.

    Args:
        code: 카카오로부터 받은 인가 코드.

    Returns:
        'access'와 'refresh' JWT 토큰 문자열을 담은 딕셔너리.

    Raises:
        SocialLoginError: 카카오 로그인 플로우 중 오류가 발생한 경우.
    """
    token_data = _exchange_kakao_code(code)
    user_info = _get_kakao_user_info(token_data["access_token"])

    provider_id = str(user_info["id"])

    user = _get_or_create_social_user(provider=SocialAccount.KAKAO, provider_id=provider_id)
    return _issue_tokens(user)


# ──────────────────────────────────────────
# 애플
# ──────────────────────────────────────────

def _generate_apple_client_secret() -> str:
    """애플 client_secret으로 사용할 서명된 JWT를 생성합니다.

    애플은 Apple Developer 콘솔에 등록된 개인키로 ES256 서명된
    JWT를 client_secret으로 요구합니다.

    Returns:
        서명된 JWT 문자열.
    """
    now = int(time.time())
    payload = {
        "iss": settings.APPLE_TEAM_ID,
        "iat": now,
        "exp": now + 86400 * 180,  # 최대 6개월
        "aud": "https://appleid.apple.com",
        "sub": settings.APPLE_CLIENT_ID,
    }
    return jwt.encode(
        payload,
        settings.APPLE_PRIVATE_KEY,
        algorithm="ES256",
        headers={"kid": settings.APPLE_KEY_ID},
    )


def _exchange_apple_code(code: str, client_secret: str) -> dict:
    """애플 인가 코드를 토큰으로 교환합니다.

    Args:
        code: 애플로부터 받은 인가 코드.
        client_secret: 서명된 JWT client_secret.

    Returns:
        'id_token'을 포함한 토큰 응답 딕셔너리.

    Raises:
        SocialLoginError: 토큰 교환에 실패한 경우.
    """
    response = requests.post(
        "https://appleid.apple.com/auth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": settings.APPLE_CLIENT_ID,
            "client_secret": client_secret,
            "redirect_uri": settings.APPLE_REDIRECT_URI,
            "code": code,
        },
        timeout=10,
    )
    data = response.json()
    if "id_token" not in data:
        raise SocialLoginError(f"Apple 토큰 교환 실패: {data.get('error', data)}")
    return data


def _decode_apple_id_token(id_token: str) -> dict:
    """애플 id_token JWT를 디코딩하여 유저 정보를 추출합니다.

    서명 검증은 생략합니다. 운영 환경에서는
    https://appleid.apple.com/auth/keys 의 공개키로 검증해야 합니다.

    Args:
        id_token: 애플로부터 받은 JWT id_token.

    Returns:
        'sub'를 포함한 디코딩된 페이로드 딕셔너리.
    """
    return jwt.decode(id_token, options={"verify_signature": False})


def apple_login(*, code: str) -> dict[str, str]:
    """Apple Sign In으로 유저를 인증하고 JWT 토큰을 반환합니다.

    Args:
        code: 애플로부터 받은 인가 코드.

    Returns:
        'access'와 'refresh' JWT 토큰 문자열을 담은 딕셔너리.

    Raises:
        SocialLoginError: 애플 로그인 플로우 중 오류가 발생한 경우.
    """
    client_secret = _generate_apple_client_secret()
    token_data = _exchange_apple_code(code, client_secret)
    user_info = _decode_apple_id_token(token_data["id_token"])

    provider_id = user_info["sub"]

    user = _get_or_create_social_user(provider=SocialAccount.APPLE, provider_id=provider_id)
    return _issue_tokens(user)

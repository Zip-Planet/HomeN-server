"""유저 / 인증 컨텍스트 시리얼라이저.

본 모듈은 다음의 흐름들을 위한 입출력 스키마를 모아둔다.

- **소셜 로그인** (`POST /api/v1/auth/kakao`, `POST /api/v1/auth/apple`)
  : 인가 코드(`code`)로 access/refresh 토큰을 발급. 신규 가입 시 자동 회원 생성.
- **로그아웃** (`POST /api/v1/auth/logout`)
  : 보유 중인 refresh 토큰을 SimpleJWT 블랙리스트에 등록.
- **토큰 갱신** (`POST /api/v1/auth/token/refresh`)
  : refresh 토큰으로 access 토큰을 재발급.
- **프로필 조회 / 수정 / 탈퇴** (`/api/v1/users/me/`)
  : 닉네임·프로필 이미지 변경 및 회원 탈퇴.

FE 컨벤션: 모든 필드는 snake_case 로 노출된다 (DRF 기본). 응답 시리얼라이저는
`drf-spectacular` 의 자동 스키마 추출을 위해 `help_text` 와 함께 명시적으로 정의되어 있다.
"""

import re

from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers

from apps.users.models import UserProfileImage


# ── 소셜 로그인 요청 ──────────────────────────────────────────────────────────


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "카카오 인가 코드",
            summary="카카오 OAuth2 인가 코드 예시",
            value={"code": "abc123XYZ_kakao_authorization_code"},
            request_only=True,
        ),
    ]
)
class KakaoLoginSerializer(serializers.Serializer):
    """카카오 소셜 로그인 요청.

    카카오 OAuth2 인가 코드(authorization code)를 받는다. 서버는 이 코드를 가지고
    카카오 토큰 엔드포인트에서 access 토큰을 교환한 뒤, 사용자 정보를 조회해
    `SocialAccount` 와 매칭되는 `User` 를 찾거나 새로 생성한다.
    """

    code = serializers.CharField(
        help_text="카카오 OAuth2 콜백으로 전달된 일회용 인가 코드(authorization code).",
    )


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "애플 인가 코드",
            summary="애플 Sign In 인가 코드 예시",
            value={"code": "c1.0.abcdef.0.apple_authorization_code"},
            request_only=True,
        ),
    ]
)
class AppleLoginSerializer(serializers.Serializer):
    """애플 소셜 로그인 요청.

    애플 Sign In 인가 코드를 받는다. 서버는 Apple 의 token 엔드포인트에서 id_token
    (JWT) 을 교환한 뒤 `sub` 를 provider_id 로 사용해 `SocialAccount` 와 매칭되는
    `User` 를 찾거나 새로 생성한다. 탈퇴 시 token revocation 을 위해 refresh_token
    도 함께 저장된다.
    """

    code = serializers.CharField(
        help_text="애플 Sign In 콜백으로 전달된 일회용 인가 코드.",
    )


# ── 토큰 / 로그인 응답 ────────────────────────────────────────────────────────


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "신규 유저",
            summary="최초 가입 직후 — 닉네임/이미지 미설정, 집 없음",
            value={
                "access": "eyJhbGciOiJIUzI1NiIs...",
                "refresh": "eyJhbGciOiJIUzI1NiIs...",
                "is_profile_set": False,
                "has_home": False,
            },
            response_only=True,
        ),
        OpenApiExample(
            "기존 유저",
            summary="프로필 + 집 보유 — 바로 메인 진입 가능",
            value={
                "access": "eyJhbGciOiJIUzI1NiIs...",
                "refresh": "eyJhbGciOiJIUzI1NiIs...",
                "is_profile_set": True,
                "has_home": True,
            },
            response_only=True,
        ),
    ]
)
class TokenOutputSerializer(serializers.Serializer):
    """소셜 로그인 성공 시 응답.

    FE 는 `is_profile_set` 으로 온보딩(닉네임/이미지 설정) 단계 여부를,
    `has_home` 으로 집 생성/참여 화면 진입 여부를 결정한다.
    """

    access = serializers.CharField(
        help_text="JWT 액세스 토큰 (기본 만료 1시간, `SIMPLE_JWT.ACCESS_TOKEN_LIFETIME`).",
    )
    refresh = serializers.CharField(
        help_text="JWT 리프레시 토큰 (기본 만료 7일). 로그아웃 시 블랙리스트에 등록.",
    )
    is_profile_set = serializers.BooleanField(
        help_text="닉네임과 프로필 이미지가 모두 설정되었는지 여부. False 면 온보딩 필요.",
    )
    has_home = serializers.BooleanField(
        help_text="집 관리자 또는 구성원으로 소속된 집이 있는지 여부.",
    )


# ── 유저 프로필 ───────────────────────────────────────────────────────────────


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "온보딩 완료 + 집 관리자",
            value={
                "uid": "8f3e2b1a-1234-4abc-9def-1234567890ab",
                "name": "홍길동",
                "profile_image": 3,
                "is_profile_set": True,
                "has_home": True,
                "home_role": 1,
            },
            response_only=True,
        ),
        OpenApiExample(
            "신규 가입 직후",
            value={
                "uid": "8f3e2b1a-1234-4abc-9def-1234567890ab",
                "name": "",
                "profile_image": None,
                "is_profile_set": False,
                "has_home": False,
                "home_role": None,
            },
            response_only=True,
        ),
    ]
)
class UserProfileOutputSerializer(serializers.Serializer):
    """현재 로그인 유저의 프로필 응답.

    `home_role` 은 `HomeMember.Role` enum 정수값이다 (1=관리자, 2=구성원).
    집에 속하지 않은 경우 `home_role` 과 `profile_image` 는 null 일 수 있다.
    """

    uid = serializers.UUIDField(
        help_text="유저 고유 식별자(UUID). 클라이언트와의 모든 매칭은 이 값으로 수행한다.",
    )
    name = serializers.CharField(
        help_text="닉네임. 한글·영문·숫자 1~8자. 온보딩 전에는 빈 문자열일 수 있다.",
    )
    profile_image = serializers.IntegerField(
        allow_null=True,
        help_text="프로필 이미지 enum 값(1~8). 미설정 시 null.",
    )
    is_profile_set = serializers.BooleanField(
        help_text="닉네임과 프로필 이미지가 모두 설정되었는지 여부.",
    )
    has_home = serializers.BooleanField(
        help_text="집 관리자 또는 구성원에 속해있는지 여부.",
    )
    home_role = serializers.IntegerField(
        allow_null=True,
        help_text="현재 속한 집에서의 역할 (1=관리자, 2=구성원). 집이 없으면 null.",
    )


class ProfileImageIdSerializer(serializers.Serializer):
    """선택 가능한 프로필 이미지 enum 한 건.

    `GET /api/v1/users/profile-images/` 가 반환하는 배열의 각 원소.
    FE 는 이 `id` 를 그대로 `UserProfileUpdate.profile_image` 로 전송한다.
    """

    id = serializers.IntegerField(
        help_text="프로필 이미지 enum ID. `UserProfileImage` 의 정수 choice 와 동일.",
    )


# ── 닉네임 중복 확인 ───────────────────────────────────────────────────────────


@extend_schema_serializer(
    examples=[
        OpenApiExample("사용 가능", value={"is_available": True}, response_only=True),
        OpenApiExample("이미 사용 중", value={"is_available": False}, response_only=True),
    ]
)
class NicknameAvailabilitySerializer(serializers.Serializer):
    """닉네임 사용 가능 여부 응답.

    온보딩 화면에서 PATCH `/users/me/` 전에 사전 검증하는 데 사용된다.
    형식 검증(특수문자 등) 은 PATCH 시점에 수행되며, 본 응답은 **존재 여부만** 반영한다.
    """

    is_available = serializers.BooleanField(
        help_text="닉네임을 사용할 수 있으면 True (다른 유저가 점유하지 않음).",
    )


# ── 로그아웃 ──────────────────────────────────────────────────────────────────


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "로그아웃 요청",
            value={"refresh": "eyJhbGciOiJIUzI1NiIs..."},
            request_only=True,
        ),
    ]
)
class LogoutSerializer(serializers.Serializer):
    """로그아웃 요청.

    클라이언트가 보유한 refresh 토큰을 SimpleJWT 의 블랙리스트(`token_blacklist`)
    에 등록해 재사용을 차단한다. access 토큰은 만료 시까지 자체 폐기되지 않으므로,
    민감한 변경 직후에는 짧은 access 만료 시간(`ACCESS_TOKEN_LIFETIME`)에 의존한다.
    """

    refresh = serializers.CharField(
        help_text="블랙리스트에 등록할 refresh 토큰. 이미 만료/블랙된 토큰이면 400.",
    )


# ── 프로필 수정 ───────────────────────────────────────────────────────────────


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "닉네임 + 이미지 변경",
            value={"name": "홍길동", "profile_image": 2},
            request_only=True,
        ),
    ]
)
class UserProfileUpdateSerializer(serializers.Serializer):
    """유저 프로필 수정 요청.

    온보딩(최초 설정)과 변경 모두 동일 엔드포인트를 사용한다. 닉네임은 중복이
    허용되지 않으며(`unique_user_name_when_set` 제약), 서비스 레이어에서 충돌 시
    `ProfileUpdateError` 가 발생해 400 으로 매핑된다.
    """

    name = serializers.CharField(
        max_length=8,
        help_text="닉네임. 한글·영문·숫자 1~8자, 공백/특수문자 불가, 전역 유일.",
    )
    profile_image = serializers.ChoiceField(
        choices=UserProfileImage.choices,
        help_text="프로필 이미지 enum 값. `/users/profile-images/` 로 노출되는 목록 중 하나.",
    )

    def validate_name(self, value: str) -> str:
        """닉네임에 특수문자가 포함되지 않았는지 검증합니다."""
        if not re.match(r"^[가-힣a-zA-Z0-9]+$", value):
            raise serializers.ValidationError("닉네임은 한글, 영문, 숫자만 사용할 수 있습니다.")
        return value

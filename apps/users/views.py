"""유저 / 인증 컨트롤러.

본 모듈은 다음의 API 묶음을 제공한다.

- **Auth** : 카카오/애플 소셜 로그인, 로그아웃, (urls.py 에서 확장되는) 토큰 갱신.
- **Users** : 본인 프로필 조회·수정·탈퇴, 선택 가능한 프로필 이미지 목록.

모든 핸들러는 다음 약속을 따른다.

- 요청은 명시적인 `*Serializer` 로 검증한다 (`raise_exception=True`).
- 도메인 예외는 서비스 레이어에서 발생시키며, 컨트롤러는 이를 DRF 의 표준 예외
  (`AuthenticationFailed`, `ValidationError`, `PermissionDenied`) 로 매핑해
  `common.exceptions.custom_exception_handler` 가 일관된 응답을 만들도록 한다.
- swagger 노출은 `@extend_schema` 로 명시한다 — summary/description/responses 모두.
"""

from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users import selectors, services
from apps.users.serializers import (
    AppleLoginSerializer,
    KakaoLoginSerializer,
    LogoutSerializer,
    NicknameAvailabilitySerializer,
    ProfileImageIdSerializer,
    TokenOutputSerializer,
    UserProfileOutputSerializer,
    UserProfileUpdateSerializer,
)
from common.error_responses import ErrorResponseSerializer, error_example


# ── 소셜 로그인 ──────────────────────────────────────────────────────────────


class KakaoLoginView(APIView):
    """카카오 소셜 로그인.

    FE 는 카카오 OAuth2 콜백으로 받은 `code` 를 그대로 전달한다. 신규 유저인 경우
    `SocialAccount` 와 `User` 가 함께 생성되며, 이후 호출에서는 동일 `provider_id`
    로 기존 유저를 재사용한다.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="카카오 소셜 로그인",
        description=(
            "카카오 OAuth2 인가 코드(code)를 받아 access/refresh JWT 를 발급한다.\n\n"
            "**플로우**\n"
            "1. FE 가 카카오 로그인 페이지로 리다이렉트 → 콜백으로 `code` 수신.\n"
            "2. 본 엔드포인트에 `code` 전달 → 서버가 카카오 토큰/유저 API 호출.\n"
            "3. `provider_id` 로 `SocialAccount` 조회 → 없으면 신규 `User` 생성.\n"
            "4. access(1h) + refresh(7d) 발급. `is_profile_set` / `has_home` 로 다음 화면 결정.\n\n"
            "**에러**\n"
            "- 400: `code` 누락 또는 빈 문자열.\n"
            "- 401: 카카오 토큰 교환 실패, 사용자 정보 조회 실패, 만료된 코드.\n"
        ),
        request=KakaoLoginSerializer,
        responses={
            200: OpenApiResponse(
                response=TokenOutputSerializer,
                description="로그인 성공 — 토큰 + 온보딩/집 보유 플래그 반환.",
            ),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="`code` 누락 등 입력 유효성 실패."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="카카오 인증 실패."),
        },
        examples=[
            OpenApiExample("정상 요청", value={"code": "abc123XYZ_kakao_authorization_code"}, request_only=True),
            OpenApiExample(
                "신규 가입 직후",
                value={
                    "access": "eyJhbGciOiJIUzI1NiIs...access...",
                    "refresh": "eyJhbGciOiJIUzI1NiIs...refresh...",
                    "is_profile_set": False,
                    "has_home": False,
                },
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "재로그인 — 프로필 + 집 있음",
                value={
                    "access": "eyJhbGciOiJIUzI1NiIs...access...",
                    "refresh": "eyJhbGciOiJIUzI1NiIs...refresh...",
                    "is_profile_set": True,
                    "has_home": True,
                },
                response_only=True,
                status_codes=["200"],
            ),
            error_example(code="invalid", message="code 필드는 필수입니다.", name="code 누락"),
            error_example(code="authentication_failed", message="카카오 토큰 교환 실패: invalid_grant", name="카카오 인증 실패"),
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = KakaoLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = services.kakao_login(**serializer.validated_data)
        except services.SocialLoginError as e:
            raise AuthenticationFailed(str(e)) from e

        return Response(TokenOutputSerializer(result).data, status=status.HTTP_200_OK)


class AppleLoginView(APIView):
    """애플 소셜 로그인.

    Apple 의 token 엔드포인트와 id_token(JWT) 검증을 거쳐 `sub` 를 provider_id 로
    사용한다. Apple 의 refresh_token 은 탈퇴 시 token revocation 에 사용되므로
    `SocialAccount.refresh_token` 컬럼에 저장한다.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="애플 소셜 로그인",
        description=(
            "Apple Sign In 인가 코드를 받아 access/refresh JWT 를 발급한다.\n\n"
            "**플로우**\n"
            "1. FE 가 Apple Sign In 콜백에서 `code` 를 수신.\n"
            "2. 본 엔드포인트로 `code` 전달 → 서버가 Apple `/auth/token` 호출.\n"
            "3. id_token 의 `sub` 로 `SocialAccount` 조회 → 없으면 신규 `User` 생성.\n"
            "4. Apple refresh_token 은 `SocialAccount.refresh_token` 에 저장 (탈퇴 시 revocation 용).\n"
            "5. JWT access(1h) + refresh(7d) 발급.\n\n"
            "**에러**\n"
            "- 400: `code` 누락.\n"
            "- 401: Apple 토큰 교환 실패, id_token 검증 실패.\n"
        ),
        request=AppleLoginSerializer,
        responses={
            200: OpenApiResponse(response=TokenOutputSerializer, description="로그인 성공 — 토큰 + 온보딩/집 보유 플래그 반환."),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="`code` 누락 등 입력 유효성 실패."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="Apple 인증 실패 (만료/위조 코드, id_token 검증 실패 등)."),
        },
        examples=[
            OpenApiExample(
                "정상 요청",
                value={"code": "c1.0.abcdef.0.apple_authorization_code"},
                request_only=True,
            ),
            OpenApiExample(
                "신규 가입 직후",
                value={
                    "access": "eyJhbGciOiJIUzI1NiIs...access...",
                    "refresh": "eyJhbGciOiJIUzI1NiIs...refresh...",
                    "is_profile_set": False,
                    "has_home": False,
                },
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "재로그인 — 프로필 + 집 있음",
                value={
                    "access": "eyJhbGciOiJIUzI1NiIs...access...",
                    "refresh": "eyJhbGciOiJIUzI1NiIs...refresh...",
                    "is_profile_set": True,
                    "has_home": True,
                },
                response_only=True,
                status_codes=["200"],
            ),
            error_example(code="invalid", message="code 필드는 필수입니다.", name="code 누락"),
            error_example(code="authentication_failed", message="Apple 토큰 교환 실패: invalid_client", name="Apple 인증 실패"),
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = AppleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = services.apple_login(**serializer.validated_data)
        except services.SocialLoginError as e:
            raise AuthenticationFailed(str(e)) from e

        return Response(TokenOutputSerializer(result).data, status=status.HTTP_200_OK)


# ── 로그아웃 ──────────────────────────────────────────────────────────────────


class LogoutView(APIView):
    """현재 로그인 세션 종료.

    SimpleJWT 의 `token_blacklist` 앱을 사용해 refresh 토큰을 폐기한다. access
    토큰은 만료 시까지 유효하므로 짧은 `ACCESS_TOKEN_LIFETIME` 으로 노출을
    최소화한다.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Auth"],
        summary="로그아웃 (refresh 토큰 블랙리스트 등록)",
        description=(
            "보유 중인 refresh 토큰을 블랙리스트에 등록해 추가 갱신을 차단한다.\n\n"
            "이미 만료되었거나 블랙리스트에 등록된 토큰을 다시 보내면 400 을 반환한다.\n"
            "access 토큰 자체의 무효화는 지원하지 않으며, 짧은 만료시간으로 대응한다."
        ),
        request=LogoutSerializer,
        responses={
            204: OpenApiResponse(description="로그아웃 처리 완료 — 응답 본문 없음."),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="유효하지 않은 토큰 또는 이미 블랙된 토큰."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락 또는 만료."),
        },
        examples=[
            OpenApiExample(
                "정상 요청",
                value={"refresh": "eyJhbGciOiJIUzI1NiIs...refresh..."},
                request_only=True,
            ),
            error_example(code="invalid_token", message="Token is invalid or expired", name="유효하지 않은 토큰"),
            error_example(code="authentication_failed", message="Authentication credentials were not provided.", name="인증 실패"),
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            services.logout_user(refresh_token=serializer.validated_data["refresh"])
        except services.LogoutError as e:
            raise ValidationError({"invalid_token": str(e)}) from e

        return Response(status=status.HTTP_204_NO_CONTENT)


# ── 본인 프로필 ──────────────────────────────────────────────────────────────


class UserMeView(APIView):
    """본인 프로필 조회 · 수정 · 탈퇴.

    하나의 엔드포인트(`/users/me/`) 에 HTTP 메서드별로 다른 동작을 매핑한다.
    - GET: 현재 유저 프로필.
    - PATCH: 닉네임/프로필 이미지 변경 (온보딩과 변경 공용).
    - DELETE: 회원 탈퇴 (집 관리자는 양도 또는 집 삭제 후 가능).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Users"],
        summary="내 프로필 조회",
        description=(
            "현재 access 토큰의 유저 정보를 반환한다.\n"
            "신규 가입 직후에는 `name` 이 빈 문자열, `profile_image`/`home_role` 이 null 일 수 있다."
        ),
        responses={
            200: OpenApiResponse(response=UserProfileOutputSerializer, description="조회 성공."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
        },
        examples=[
            OpenApiExample(
                "온보딩 미완료 (신규 가입 직후)",
                value={
                    "uid": "8f3e2b1a-1234-4abc-9def-1234567890ab",
                    "name": "",
                    "profile_image": None,
                    "home_role": None,
                },
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "온보딩 완료 + 집 보유 (관리자)",
                value={
                    "uid": "8f3e2b1a-1234-4abc-9def-1234567890ab",
                    "name": "홍길동",
                    "profile_image": 3,
                    "home_role": "admin",
                },
                response_only=True,
                status_codes=["200"],
            ),
            error_example(code="authentication_failed", message="Authentication credentials were not provided.", name="인증 실패"),
        ],
    )
    def get(self, request: Request) -> Response:
        return Response(UserProfileOutputSerializer(request.user).data)

    @extend_schema(
        tags=["Users"],
        summary="내 프로필 수정 (온보딩 / 변경 공용)",
        description=(
            "닉네임과 프로필 이미지를 함께 갱신한다.\n\n"
            "**검증**\n"
            "- 닉네임: 한글·영문·숫자 1~8자, 공백/특수문자 불가.\n"
            "- 닉네임 전역 유일 — 이미 사용 중이면 400 (`duplicate_nickname`).\n"
            "- 프로필 이미지: `UserProfileImage` choice 정수만 허용.\n"
        ),
        request=UserProfileUpdateSerializer,
        responses={
            200: OpenApiResponse(response=UserProfileOutputSerializer, description="변경 후 최신 프로필."),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="유효성 검사 실패 또는 닉네임 중복."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
        },
        examples=[
            OpenApiExample("정상 요청", value={"name": "홍길동", "profile_image": 3}, request_only=True),
            OpenApiExample(
                "변경 성공",
                value={
                    "uid": "8f3e2b1a-1234-4abc-9def-1234567890ab",
                    "name": "홍길동",
                    "profile_image": 3,
                    "home_role": "member",
                },
                response_only=True,
                status_codes=["200"],
            ),
            error_example(code="invalid", message="닉네임은 한글·영문·숫자 1~8자만 허용됩니다.", name="형식 위반"),
            error_example(code="duplicate_nickname", message="이미 사용 중인 닉네임입니다.", name="닉네임 중복"),
            error_example(code="authentication_failed", message="Authentication credentials were not provided.", name="인증 실패"),
        ],
    )
    def patch(self, request: Request) -> Response:
        serializer = UserProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = services.update_profile(user=request.user, **serializer.validated_data)
        except services.ProfileUpdateError as e:
            raise ValidationError({"duplicate_nickname": str(e)}) from e

        return Response(UserProfileOutputSerializer(user).data)

    @extend_schema(
        tags=["Users"],
        summary="회원 탈퇴",
        description=(
            "현재 유저를 탈퇴 처리한다.\n\n"
            "**선결 조건**\n"
            "- 집 관리자는 직접 탈퇴할 수 없다. 다음 중 하나가 필요하다.\n"
            "  - 다른 구성원에게 관리자 양도 (`POST /homes/mine/transfer-admin/`).\n"
            "  - 또는 본인 집 삭제 (`DELETE /homes/mine/` — 구성원이 없을 때만 가능).\n"
            "- 위반 시 403 `home_admin_cannot_withdraw`.\n\n"
            "**부수 효과**\n"
            "- Apple 가입자: 저장된 refresh_token 으로 token revocation 호출.\n"
            "- 카카오 가입자: 별도 revocation 없이 로컬 정리.\n"
        ),
        responses={
            204: OpenApiResponse(description="탈퇴 완료 — 응답 본문 없음."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="집 관리자는 양도 또는 집 삭제 후 탈퇴 가능."),
        },
        examples=[
            error_example(code="authentication_failed", message="Authentication credentials were not provided.", name="인증 실패"),
            error_example(
                code="home_admin_cannot_withdraw",
                message="집 관리자는 직접 탈퇴할 수 없습니다. 관리자를 양도하거나 집을 삭제해주세요.",
                name="관리자 탈퇴 불가",
            ),
        ],
    )
    def delete(self, request: Request) -> Response:
        try:
            services.withdraw_user(user=request.user)
        except services.HomeAdminWithdrawalError as e:
            raise PermissionDenied({"home_admin_cannot_withdraw": str(e)}) from e
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── 프리셋 ──────────────────────────────────────────────────────────────────


class ProfileImageListView(APIView):
    """선택 가능한 프로필 이미지 enum 목록.

    인증 없이 호출 가능 — 회원가입 전 온보딩 미리보기에도 사용된다.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Users"],
        summary="프리셋 프로필 이미지 목록 조회",
        description=(
            "선택 가능한 프로필 이미지 enum 정수 목록을 반환한다.\n"
            "FE 는 응답의 `id` 를 그대로 `PATCH /users/me/` 의 `profile_image` 로 전송한다."
        ),
        responses={
            200: OpenApiResponse(response=ProfileImageIdSerializer(many=True), description="enum ID 배열."),
        },
        examples=[
            OpenApiExample(
                "전체 enum 목록",
                value=[{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}, {"id": 5}],
                response_only=True,
                status_codes=["200"],
            ),
        ],
    )
    def get(self, request: Request) -> Response:
        return Response(selectors.get_profile_image_choices())


# ── 닉네임 중복 확인 ───────────────────────────────────────────────────────────


class NicknameAvailabilityView(APIView):
    """온보딩 시 닉네임 사전 중복 확인.

    PATCH `/users/me/` 호출 전에 `is_available` 을 미리 보여주기 위함.
    형식 검증(특수문자 등) 은 PATCH 단계에 위임한다 — 본 응답은 존재 여부만 반영.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Users"],
        summary="닉네임 사용 가능 여부 확인",
        description=(
            "주어진 닉네임을 다른 유저가 점유 중인지 확인한다.\n\n"
            "- 사용 가능 → `200 + {\"is_available\": true}`\n"
            "- 이미 사용 중 → `200 + {\"is_available\": false}`\n"
            "- 형식 검증(한글·영문·숫자 1~8자) 은 본 API 가 아니라 `PATCH /users/me/` 시점에 수행.\n"
        ),
        responses={
            200: OpenApiResponse(
                response=NicknameAvailabilitySerializer,
                description="사용 가능 여부.",
            ),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
        },
        examples=[
            OpenApiExample(
                "사용 가능",
                value={"is_available": True},
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "이미 사용 중",
                value={"is_available": False},
                response_only=True,
                status_codes=["200"],
            ),
            error_example(code="authentication_failed", message="Authentication credentials were not provided.", name="인증 실패"),
        ],
    )
    def get(self, request: Request, nickname: str) -> Response:
        return Response({"is_available": selectors.is_nickname_available(nickname)})

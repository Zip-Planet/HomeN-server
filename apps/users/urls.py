"""유저 / 인증 URL 매핑.

`config.urls` 에서 다음과 같이 마운트된다.

- `path("api/v1/auth/", include(auth_urlpatterns))`
- `path("api/v1/users/", include(user_urlpatterns))`

`TokenRefreshView` (SimpleJWT 제공) 는 본 프로젝트의 swagger 태깅 규칙에 맞추기 위해
`@extend_schema` 로 래핑되어 노출된다.
"""

from django.urls import path
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework_simplejwt.views import TokenRefreshView

from apps.users.views import (
    AppleLoginView,
    KakaoLoginView,
    LogoutView,
    NicknameAvailabilityView,
    ProfileImageListView,
    UserMeView,
)
from common.error_responses import ErrorResponseSerializer, error_example

# SimpleJWT 의 TokenRefreshView 는 외부 라이브러리이므로 swagger 메타데이터를 데코레이터로 덧붙인다.
# - tags: 본 프로젝트의 "Auth" 그룹으로 묶기 위해 명시.
# - description: refresh 토큰 회전(rotation) 동작 여부와 access/refresh 응답 구조를 기재.
TokenRefreshView = extend_schema(
    tags=["Auth"],
    summary="액세스 토큰 갱신 (refresh → 새 access)",
    description=(
        "## 🔥 설명\n"
        "보유 중인 refresh 토큰으로 새 access 토큰을 발급한다. refresh 회전(rotation) 여부는 "
        "`SIMPLE_JWT` 설정에 의존한다.\n\n"
        "## 🔐 인증\n"
        "없음 (refresh 토큰 자체로 검증).\n\n"
        "## 📥 요청\n"
        "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| body | `refresh` | string | ✓ | JWT refresh 토큰 |\n\n"
        "## 📤 응답 (200)\n"
        "| 위치 | 필드 | 타입 | 설명 |\n"
        "| --- | --- | --- | --- |\n"
        "| body | `access` | string | 신규 access 토큰 |\n"
        "| body | `refresh` | string | (회전 ON 시) 신규 refresh 토큰 |\n\n"
        "## ❌ 에러\n"
        "| status | code | 의미 |\n"
        "| --- | --- | --- |\n"
        "| 400 | `invalid` | refresh 형식 오류 |\n"
        "| 401 | `token_not_valid` | refresh 만료/위조/블랙리스트 |\n\n"
        "## 💻 예제\n"
        "**요청:**\n"
        "```bash\n"
        "curl -X POST '{host}/api/v1/auth/token/refresh/' \\\n"
        "     -H 'Content-Type: application/json' \\\n"
        "     -d '{\"refresh\":\"eyJhbGciOiJIUzI1NiIs...\"}'\n"
        "```\n\n"
        "**응답 (200):**\n"
        "```json\n"
        "{\"access\": \"eyJhbGciOiJIUzI1NiIs...new_access...\"}\n"
        "```\n"
    ),
    responses={
        200: OpenApiResponse(
            description="신규 access 토큰 (회전 설정 시 refresh 도 함께 반환).",
        ),
        400: OpenApiResponse(response=ErrorResponseSerializer, description="refresh 형식 오류."),
        401: OpenApiResponse(response=ErrorResponseSerializer, description="refresh 만료/위조/블랙리스트."),
    },
    examples=[
        OpenApiExample("정상 요청", value={"refresh": "eyJhbGciOiJIUzI1NiIs...refresh..."}, request_only=True),
        OpenApiExample(
            "갱신 성공 (회전 OFF)",
            value={"access": "eyJhbGciOiJIUzI1NiIs...new_access..."},
            response_only=True,
            status_codes=["200"],
        ),
        OpenApiExample(
            "갱신 성공 (회전 ON)",
            value={
                "access": "eyJhbGciOiJIUzI1NiIs...new_access...",
                "refresh": "eyJhbGciOiJIUzI1NiIs...new_refresh...",
            },
            response_only=True,
            status_codes=["200"],
        ),
        error_example(code="invalid", message="refresh 필드는 필수입니다.", name="refresh 누락"),
        error_example(
            code="token_not_valid",
            message="Token is invalid or expired",
            name="만료/블랙리스트",
        ),
    ],
)(TokenRefreshView)


auth_urlpatterns = [
    path("kakao/", KakaoLoginView.as_view(), name="kakao-login"),
    path("apple/", AppleLoginView.as_view(), name="apple-login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
]

user_urlpatterns = [
    path("me/", UserMeView.as_view(), name="user-me"),
    path("profile-images/", ProfileImageListView.as_view(), name="profile-image-list"),
    path("nicknames/<str:nickname>/", NicknameAvailabilityView.as_view(), name="nickname-availability"),
]

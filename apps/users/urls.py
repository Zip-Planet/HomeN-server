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

from apps.users.views import AppleLoginView, KakaoLoginView, LogoutView, ProfileImageListView, UserMeView

# SimpleJWT 의 TokenRefreshView 는 외부 라이브러리이므로 swagger 메타데이터를 데코레이터로 덧붙인다.
# - tags: 본 프로젝트의 "Auth" 그룹으로 묶기 위해 명시.
# - description: refresh 토큰 회전(rotation) 동작 여부와 access/refresh 응답 구조를 기재.
TokenRefreshView = extend_schema(
    tags=["Auth"],
    summary="액세스 토큰 갱신 (refresh → 새 access)",
    description=(
        "보유 중인 refresh 토큰으로 새 access 토큰을 발급한다.\n\n"
        "**플로우**\n"
        "1. FE 가 만료/임박한 access 를 감지하면 본 엔드포인트로 refresh 전송.\n"
        "2. 서버는 refresh 의 유효성/블랙리스트 여부를 검증.\n"
        "3. 신규 access 토큰을 응답으로 반환 (refresh 회전 여부는 `SIMPLE_JWT` 설정에 의존).\n\n"
        "**에러**\n"
        "- 400: refresh 형식이 잘못됨.\n"
        "- 401: refresh 가 만료/위조되었거나 블랙리스트에 등록됨.\n"
    ),
    responses={
        200: OpenApiResponse(
            description="신규 access 토큰 (회전 설정 시 refresh 도 함께 반환).",
        ),
        400: OpenApiResponse(description="refresh 형식 오류."),
        401: OpenApiResponse(description="refresh 만료/위조/블랙리스트."),
    },
    examples=[
        OpenApiExample("정상 요청", value={"refresh": "eyJhbGciOiJIUzI1NiIs..."}, request_only=True),
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
]

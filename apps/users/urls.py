from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework_simplejwt.views import TokenRefreshView

from apps.users.views import AppleLoginView, KakaoLoginView, LogoutView, ProfileImageListView, UserMeView

TokenRefreshView = extend_schema(tags=["Auth"], summary="액세스 토큰 갱신")(TokenRefreshView)

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

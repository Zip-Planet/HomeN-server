from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.users.views import AppleLoginView, KakaoLoginView, ProfileImageListView, UserMeView

auth_urlpatterns = [
    path("kakao/", KakaoLoginView.as_view(), name="kakao-login"),
    path("apple/", AppleLoginView.as_view(), name="apple-login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
]

user_urlpatterns = [
    path("me/", UserMeView.as_view(), name="user-me"),
    path("profile-images/", ProfileImageListView.as_view(), name="profile-image-list"),
]

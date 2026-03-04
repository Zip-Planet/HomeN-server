from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.users.views import AppleLoginView, KakaoLoginView

urlpatterns = [
    path("kakao/", KakaoLoginView.as_view(), name="kakao-login"),
    path("apple/", AppleLoginView.as_view(), name="apple-login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
]

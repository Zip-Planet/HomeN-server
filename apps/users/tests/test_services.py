from unittest.mock import patch

import pytest

from apps.homes.models import HomeMember
from apps.homes.tests.factories import HomeMemberFactory
from apps.users.models import SocialAccount, User, UserProfileImage
from apps.users.services import HomeAdminWithdrawalError, LogoutError, ProfileUpdateError, SocialLoginError, apple_login, kakao_login, logout_user, update_profile, withdraw_user
from apps.users.tests.factories import SocialAccountFactory, UserFactory

KAKAO_USER_INFO = {
    "id": 123456789,
    "kakao_account": {},
}

APPLE_ID_TOKEN_PAYLOAD = {
    "sub": "apple.user.id.001",
}


@pytest.mark.django_db
class TestKakaoLogin:
    @patch("apps.users.services._exchange_kakao_code")
    @patch("apps.users.services._get_kakao_user_info")
    def test_creates_new_user_on_first_login(self, mock_user_info, mock_exchange):
        mock_exchange.return_value = {"access_token": "fake-token"}
        mock_user_info.return_value = KAKAO_USER_INFO

        result = kakao_login(code="auth-code")

        assert User.objects.count() == 1
        assert SocialAccount.objects.filter(provider="kakao", provider_id="123456789").exists()
        assert "access" in result
        assert "refresh" in result
        assert result["is_profile_set"] is False

    @patch("apps.users.services._exchange_kakao_code")
    @patch("apps.users.services._get_kakao_user_info")
    def test_returns_existing_user_on_second_login(self, mock_user_info, mock_exchange):
        mock_exchange.return_value = {"access_token": "fake-token"}
        mock_user_info.return_value = KAKAO_USER_INFO
        existing_user = UserFactory()
        SocialAccountFactory(user=existing_user, provider="kakao", provider_id="123456789")

        kakao_login(code="auth-code")

        assert User.objects.count() == 1

    @patch("apps.users.services._exchange_kakao_code")
    def test_raises_on_token_exchange_failure(self, mock_exchange):
        mock_exchange.side_effect = SocialLoginError("카카오 토큰 교환 실패")

        with pytest.raises(SocialLoginError):
            kakao_login(code="bad-code")

    @patch("apps.users.services.requests.post")
    def test_exchange_uses_request_redirect_uri(self, mock_post):
        """FE가 보낸 redirect_uri를 토큰 교환에 그대로 사용한다 (접속 위치별 다중 host 지원)."""
        from apps.users.services import _exchange_kakao_code

        mock_post.return_value.json.return_value = {"access_token": "t"}

        _exchange_kakao_code("code-1", "http://192.168.0.5:8080/auth/kakao/callback")

        assert mock_post.call_args.kwargs["data"]["redirect_uri"] == "http://192.168.0.5:8080/auth/kakao/callback"

    @patch("apps.users.services.requests.post")
    def test_exchange_falls_back_to_settings_redirect_uri(self, mock_post):
        """redirect_uri 미지정 시 서버 설정값으로 폴백한다 (하위호환)."""
        from django.conf import settings

        from apps.users.services import _exchange_kakao_code

        mock_post.return_value.json.return_value = {"access_token": "t"}

        _exchange_kakao_code("code-1")

        assert mock_post.call_args.kwargs["data"]["redirect_uri"] == settings.KAKAO_REDIRECT_URI

    @patch("apps.users.services.requests.post")
    def test_exchange_uses_native_app_key_for_native_scheme(self, mock_post):
        """네이티브 스킴 redirect_uri면 네이티브 앱 키로 교환하고 client_secret은 제외한다 (KOE320 방지)."""
        from django.test import override_settings

        from apps.users.services import _exchange_kakao_code

        mock_post.return_value.json.return_value = {"access_token": "t"}

        with override_settings(KAKAO_NATIVE_APP_KEY="native-key-123", KAKAO_CLIENT_SECRET="secret"):
            _exchange_kakao_code("code-1", "kakaonative-key-123://oauth")

        sent = mock_post.call_args.kwargs["data"]
        assert sent["client_id"] == "native-key-123"
        assert "client_secret" not in sent

    @patch("apps.users.services.requests.post")
    def test_exchange_uses_native_app_key_on_settings_fallback(self, mock_post):
        """redirect_uri 미전송 + 서버 설정이 네이티브 스킴이어도 네이티브 앱 키로 교환한다 (모바일 앱 기본 경로)."""
        from django.test import override_settings

        from apps.users.services import _exchange_kakao_code

        mock_post.return_value.json.return_value = {"access_token": "t"}

        with override_settings(
            KAKAO_NATIVE_APP_KEY="native-key-123", KAKAO_REDIRECT_URI="kakaonative-key-123://oauth"
        ):
            _exchange_kakao_code("code-1")

        assert mock_post.call_args.kwargs["data"]["client_id"] == "native-key-123"

    @patch("apps.users.services.requests.post")
    def test_exchange_uses_rest_key_for_web_redirect_uri(self, mock_post):
        """웹 redirect_uri는 기존대로 REST API 키 + client_secret으로 교환한다 (회귀 방지)."""
        from django.test import override_settings

        from apps.users.services import _exchange_kakao_code

        mock_post.return_value.json.return_value = {"access_token": "t"}

        with override_settings(
            KAKAO_NATIVE_APP_KEY="native-key-123", KAKAO_REST_API_KEY="rest-key", KAKAO_CLIENT_SECRET="secret"
        ):
            _exchange_kakao_code("code-1", "http://localhost:5173/auth/kakao/callback")

        sent = mock_post.call_args.kwargs["data"]
        assert sent["client_id"] == "rest-key"
        assert sent["client_secret"] == "secret"

    @patch("apps.users.services.requests.post")
    def test_exchange_falls_back_to_rest_key_without_native_key(self, mock_post):
        """KAKAO_NATIVE_APP_KEY 미설정이면 네이티브 스킴이어도 REST 키로 교환한다 (하위호환)."""
        from django.test import override_settings

        from apps.users.services import _exchange_kakao_code

        mock_post.return_value.json.return_value = {"access_token": "t"}

        with override_settings(KAKAO_NATIVE_APP_KEY="", KAKAO_REST_API_KEY="rest-key"):
            _exchange_kakao_code("code-1", "kakaosome-key://oauth")

        assert mock_post.call_args.kwargs["data"]["client_id"] == "rest-key"

    @patch("apps.users.services.requests.post")
    def test_exchange_error_includes_kakao_error_code(self, mock_post):
        """교환 실패 시 카카오 error_code(예: KOE320)를 에러 메시지에 포함한다."""
        from apps.users.services import _exchange_kakao_code

        mock_post.return_value.json.return_value = {
            "error": "invalid_grant",
            "error_code": "KOE320",
            "error_description": "authorization code not found",
        }

        with pytest.raises(SocialLoginError, match="KOE320"):
            _exchange_kakao_code("used-code")


@pytest.mark.django_db
class TestAppleLogin:
    @patch("apps.users.services._generate_apple_client_secret")
    @patch("apps.users.services._exchange_apple_code")
    @patch("apps.users.services._decode_apple_id_token")
    def test_creates_new_user_on_first_login(self, mock_decode, mock_exchange, mock_secret):
        mock_secret.return_value = "fake-client-secret"
        mock_exchange.return_value = {"id_token": "fake-id-token"}
        mock_decode.return_value = APPLE_ID_TOKEN_PAYLOAD

        result = apple_login(code="auth-code")

        assert User.objects.count() == 1
        assert SocialAccount.objects.filter(provider="apple", provider_id="apple.user.id.001").exists()
        assert "access" in result
        assert "refresh" in result
        assert result["is_profile_set"] is False

    @patch("apps.users.services._generate_apple_client_secret")
    @patch("apps.users.services._exchange_apple_code")
    @patch("apps.users.services._decode_apple_id_token")
    def test_returns_existing_user_on_second_login(self, mock_decode, mock_exchange, mock_secret):
        mock_secret.return_value = "fake-client-secret"
        mock_exchange.return_value = {"id_token": "fake-id-token"}
        mock_decode.return_value = {"sub": "apple.user.id.001"}
        existing_user = UserFactory()
        SocialAccountFactory(user=existing_user, provider="apple", provider_id="apple.user.id.001")

        apple_login(code="auth-code")

        assert User.objects.count() == 1

    @patch("apps.users.services._generate_apple_client_secret")
    @patch("apps.users.services._exchange_apple_code")
    @patch("apps.users.services._decode_apple_id_token")
    def test_refresh_token_저장(self, mock_decode, mock_exchange, mock_secret):
        mock_secret.return_value = "fake-client-secret"
        mock_exchange.return_value = {"id_token": "fake-id-token", "refresh_token": "apple-refresh-xyz"}
        mock_decode.return_value = APPLE_ID_TOKEN_PAYLOAD

        apple_login(code="auth-code")

        social = SocialAccount.objects.get(provider="apple")
        assert social.refresh_token == "apple-refresh-xyz"

    @patch("apps.users.services._generate_apple_client_secret")
    @patch("apps.users.services._exchange_apple_code")
    @patch("apps.users.services._decode_apple_id_token")
    def test_재로그인_시_refresh_token_갱신(self, mock_decode, mock_exchange, mock_secret):
        mock_secret.return_value = "fake-client-secret"
        mock_exchange.return_value = {"id_token": "fake-id-token", "refresh_token": "new-refresh-token"}
        mock_decode.return_value = APPLE_ID_TOKEN_PAYLOAD
        existing_user = UserFactory()
        SocialAccountFactory(user=existing_user, provider="apple", provider_id="apple.user.id.001", refresh_token="old-refresh-token")

        apple_login(code="auth-code")

        social = SocialAccount.objects.get(provider="apple")
        assert social.refresh_token == "new-refresh-token"

    @patch("apps.users.services._generate_apple_client_secret")
    @patch("apps.users.services._exchange_apple_code")
    def test_raises_on_token_exchange_failure(self, mock_exchange, mock_secret):
        mock_secret.return_value = "fake-client-secret"
        mock_exchange.side_effect = SocialLoginError("Apple 토큰 교환 실패")

        with pytest.raises(SocialLoginError):
            apple_login(code="bad-code")


@pytest.mark.django_db
class TestUpdateProfile:
    def test_sets_nickname_and_profile_image(self):
        user = UserFactory(name="")

        updated = update_profile(user=user, name="홍길동", profile_image=UserProfileImage.TYPE_1)

        assert updated.name == "홍길동"
        assert updated.profile_image == UserProfileImage.TYPE_1
        assert updated.is_profile_set is True

    def test_raises_on_duplicate_nickname(self):
        UserFactory(name="홍길동")
        other_user = UserFactory(name="")

        with pytest.raises(ProfileUpdateError):
            update_profile(user=other_user, name="홍길동", profile_image=UserProfileImage.TYPE_1)

    def test_allows_keeping_own_nickname(self):
        user = UserFactory(name="홍길동", profile_image=UserProfileImage.TYPE_1)

        updated = update_profile(user=user, name="홍길동", profile_image=UserProfileImage.TYPE_2)

        assert updated.name == "홍길동"
        assert updated.profile_image == UserProfileImage.TYPE_2


@pytest.mark.django_db
class TestWithdrawUser:
    def test_집_없는_유저는_즉시_탈퇴(self):
        user = UserFactory()

        withdraw_user(user=user)

        assert not User.objects.filter(pk=user.pk).exists()

    def test_구성원은_즉시_탈퇴(self):
        user = UserFactory()
        member = HomeMemberFactory(user=user, role=HomeMember.Role.MEMBER)
        user_pk = user.pk
        member_pk = member.pk

        withdraw_user(user=user)

        assert not User.objects.filter(pk=user_pk).exists()
        assert not HomeMember.objects.filter(pk=member_pk).exists()

    def test_관리자는_탈퇴_불가(self):
        user = UserFactory()
        HomeMemberFactory(user=user, role=HomeMember.Role.ADMIN)

        with pytest.raises(HomeAdminWithdrawalError):
            withdraw_user(user=user)

        assert User.objects.filter(pk=user.pk).exists()

    @patch("apps.users.services._kakao_unlink")
    def test_탈퇴_시_소셜계정도_삭제(self, mock_unlink):
        user = UserFactory()
        social = SocialAccountFactory(user=user, provider=SocialAccount.KAKAO)
        social_pk = social.pk

        withdraw_user(user=user)

        assert not SocialAccount.objects.filter(pk=social_pk).exists()
        mock_unlink.assert_called_once_with(social.provider_id)

    @patch("apps.users.services._kakao_unlink")
    def test_카카오_탈퇴_시_unlink_호출(self, mock_unlink):
        user = UserFactory()
        social = SocialAccountFactory(user=user, provider=SocialAccount.KAKAO, provider_id="12345")

        withdraw_user(user=user)

        mock_unlink.assert_called_once_with("12345")

    @patch("apps.users.services._apple_revoke_token")
    def test_애플_탈퇴_시_refresh_token_있으면_revoke_호출(self, mock_revoke):
        user = UserFactory()
        SocialAccountFactory(user=user, provider=SocialAccount.APPLE, refresh_token="apple-refresh-token")

        withdraw_user(user=user)

        mock_revoke.assert_called_once_with("apple-refresh-token")

    @patch("apps.users.services._apple_revoke_token")
    def test_애플_탈퇴_시_refresh_token_없으면_revoke_미호출(self, mock_revoke):
        user = UserFactory()
        SocialAccountFactory(user=user, provider=SocialAccount.APPLE, refresh_token="")

        withdraw_user(user=user)

        mock_revoke.assert_not_called()

    @patch("apps.users.services._kakao_unlink")
    def test_unlink_실패해도_탈퇴_진행(self, mock_unlink):
        mock_unlink.side_effect = Exception("네트워크 오류")
        user = UserFactory()
        SocialAccountFactory(user=user, provider=SocialAccount.KAKAO)
        user_pk = user.pk

        withdraw_user(user=user)

        assert not User.objects.filter(pk=user_pk).exists()


@pytest.mark.django_db
class TestLogoutUser:
    def test_유효한_토큰_로그아웃_성공(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        user = UserFactory()
        refresh = RefreshToken.for_user(user)

        logout_user(refresh_token=str(refresh))

        with pytest.raises(LogoutError):
            logout_user(refresh_token=str(refresh))

    def test_블랙리스트_토큰_재사용_불가(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        user = UserFactory()
        refresh = RefreshToken.for_user(user)
        logout_user(refresh_token=str(refresh))

        with pytest.raises(LogoutError):
            logout_user(refresh_token=str(refresh))

    def test_유효하지_않은_토큰_오류(self):
        with pytest.raises(LogoutError):
            logout_user(refresh_token="invalid.token.value")

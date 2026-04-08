from unittest.mock import patch

import pytest

from apps.users.models import SocialAccount, User
from apps.users.services import ProfileUpdateError, SocialLoginError, apple_login, kakao_login, update_profile
from apps.users.tests.factories import ProfileImageFactory, SocialAccountFactory, UserFactory

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
    def test_raises_on_token_exchange_failure(self, mock_exchange, mock_secret):
        mock_secret.return_value = "fake-client-secret"
        mock_exchange.side_effect = SocialLoginError("Apple 토큰 교환 실패")

        with pytest.raises(SocialLoginError):
            apple_login(code="bad-code")


@pytest.mark.django_db
class TestUpdateProfile:
    def test_sets_nickname_and_profile_image(self):
        user = UserFactory(name="")
        image = ProfileImageFactory()

        updated = update_profile(user=user, name="홍길동", profile_image=image)

        assert updated.name == "홍길동"
        assert updated.profile_image == image.image.name
        assert updated.is_profile_set is True

    def test_raises_on_duplicate_nickname(self):
        UserFactory(name="홍길동")
        other_user = UserFactory(name="")
        image = ProfileImageFactory()

        with pytest.raises(ProfileUpdateError):
            update_profile(user=other_user, name="홍길동", profile_image=image)

    def test_allows_keeping_own_nickname(self):
        image = ProfileImageFactory()
        user = UserFactory(name="홍길동")
        user.profile_image = image.image.name
        user.save()
        new_image = ProfileImageFactory()

        updated = update_profile(user=user, name="홍길동", profile_image=new_image)

        assert updated.name == "홍길동"
        assert updated.profile_image == new_image.image.name

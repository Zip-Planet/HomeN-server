from unittest.mock import patch

import pytest

from apps.homes.models import HomeMember
from apps.homes.tests.factories import HomeMemberFactory
from apps.users.models import SocialAccount, User, UserProfileImage
from apps.users.services import HomeAdminWithdrawalError, ProfileUpdateError, SocialLoginError, apple_login, kakao_login, update_profile, withdraw_user
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

    def test_탈퇴_시_소셜계정도_삭제(self):
        user = UserFactory()
        social = SocialAccountFactory(user=user)
        social_pk = social.pk

        withdraw_user(user=user)

        assert not SocialAccount.objects.filter(pk=social_pk).exists()

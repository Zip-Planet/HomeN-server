from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.homes.models import HomeMember
from apps.homes.tests.factories import HomeFactory, HomeMemberFactory
from apps.users.models import UserProfileImage
from apps.users.services import ProfileUpdateError, SocialLoginError
from apps.users.tests.factories import UserFactory

FAKE_TOKENS = {"access": "fake-access-token", "refresh": "fake-refresh-token", "is_profile_set": False, "has_home": False}


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def auth_client(api_client) -> APIClient:
    user = UserFactory()
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def auth_client_with_user(api_client):
    user = UserFactory()
    api_client.force_authenticate(user=user)
    return api_client, user


@pytest.mark.django_db
class TestKakaoLoginView:
    url = "/api/v1/auth/kakao/"

    @patch("apps.users.services.kakao_login")
    def test_login_success_returns_tokens(self, mock_login, api_client):
        mock_login.return_value = FAKE_TOKENS

        response = api_client.post(self.url, {"code": "valid-code"}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["access"] == FAKE_TOKENS["access"]
        assert response.data["refresh"] == FAKE_TOKENS["refresh"]
        assert "is_profile_set" in response.data
        assert "has_home" in response.data
        mock_login.assert_called_once_with(code="valid-code")

    @patch("apps.users.services.kakao_login")
    def test_login_failure_returns_401(self, mock_login, api_client):
        mock_login.side_effect = SocialLoginError("카카오 토큰 교환 실패")

        response = api_client.post(self.url, {"code": "bad-code"}, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "error" in response.data

    def test_missing_code_returns_400(self, api_client):
        response = api_client.post(self.url, {}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestAppleLoginView:
    url = "/api/v1/auth/apple/"

    @patch("apps.users.services.apple_login")
    def test_login_success_returns_tokens(self, mock_login, api_client):
        mock_login.return_value = FAKE_TOKENS

        response = api_client.post(self.url, {"code": "valid-code"}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["access"] == FAKE_TOKENS["access"]
        assert "has_home" in response.data
        mock_login.assert_called_once_with(code="valid-code")

    @patch("apps.users.services.apple_login")
    def test_login_failure_returns_401(self, mock_login, api_client):
        mock_login.side_effect = SocialLoginError("Apple 토큰 교환 실패")

        response = api_client.post(self.url, {"code": "bad-code"}, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "error" in response.data

    def test_missing_code_returns_400(self, api_client):
        response = api_client.post(self.url, {}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestUserMeView:
    url = "/api/v1/users/me/"

    def test_get_profile_returns_200(self, auth_client):
        response = auth_client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        assert "uid" in response.data
        assert "name" in response.data
        assert "profile_image" in response.data
        assert "is_profile_set" in response.data
        assert "has_home" in response.data

    def test_집_없는_유저_has_home_false(self, api_client):
        user = UserFactory()
        api_client.force_authenticate(user=user)

        response = api_client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["has_home"] is False

    def test_집_있는_유저_has_home_true(self, api_client):
        user = UserFactory()
        home = HomeFactory(status="active")
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.MEMBER)
        api_client.force_authenticate(user=user)

        response = api_client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["has_home"] is True

    def test_get_profile_unauthenticated_returns_401(self, api_client):
        response = api_client.get(self.url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("apps.users.services.update_profile")
    def test_patch_profile_success(self, mock_update, auth_client_with_user):
        api_client, user = auth_client_with_user
        user.name = "홍길동"
        user.profile_image = UserProfileImage.TYPE_1
        mock_update.return_value = user

        response = api_client.patch(
            self.url, {"name": "홍길동", "profile_image": UserProfileImage.TYPE_1}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        mock_update.assert_called_once_with(
            user=user, name="홍길동", profile_image=UserProfileImage.TYPE_1
        )

    def test_patch_profile_invalid_name_too_long(self, auth_client):
        response = auth_client.patch(
            self.url, {"name": "아홉글자닉네임이야", "profile_image": UserProfileImage.TYPE_1}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_patch_profile_invalid_name_special_chars(self, auth_client):
        response = auth_client.patch(
            self.url, {"name": "nick!", "profile_image": UserProfileImage.TYPE_1}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_patch_profile_invalid_profile_image_not_found(self, auth_client):
        response = auth_client.patch(self.url, {"name": "홍길동", "profile_image": 9999}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("apps.users.services.update_profile")
    def test_patch_profile_duplicate_nickname_returns_400(self, mock_update, auth_client):
        mock_update.side_effect = ProfileUpdateError("이미 사용 중인 닉네임입니다.")

        response = auth_client.patch(
            self.url, {"name": "홍길동", "profile_image": UserProfileImage.TYPE_1}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.data


@pytest.mark.django_db
class TestProfileImageListView:
    url = "/api/v1/users/profile-images/"

    def test_returns_profile_image_enum_list(self, api_client):
        response = api_client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == len(UserProfileImage.choices)
        assert "id" in response.data[0]
        assert response.data[0]["id"] == UserProfileImage.TYPE_1

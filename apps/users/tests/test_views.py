from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.services import SocialLoginError

FAKE_TOKENS = {"access": "fake-access-token", "refresh": "fake-refresh-token"}


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


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

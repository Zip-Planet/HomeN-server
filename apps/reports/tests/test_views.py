import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.homes.services import week_start_of
from apps.reports.services import generate_report
from apps.reports.tests.test_services import _confirmed_home
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

_URL = "/api/v1/homes/mine/reports/weekly/"


def auth_client(user) -> APIClient:
    client = APIClient()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


class TestWeeklyReportView:
    def test_리포트_조회_200(self):
        home, admin, _ = _confirmed_home(complete=2)
        generate_report(home=home, week_start=week_start_of(timezone.localdate()))

        res = auth_client(admin).get(_URL)

        assert res.status_code == 200
        assert res.data["completed_count"] == 2
        assert res.data["progress_rate"] == 67
        assert res.data["mvp"]["point"] == 240
        assert len(res.data["member_stats"]) == 1
        assert res.data["most_done"]["count"] == 1

    def test_리포트가_없으면_404(self):
        _home, admin, _ = _confirmed_home(complete=1)

        assert auth_client(admin).get(_URL).status_code == 404

    def test_월요일이_아닌_week_start_400(self):
        _home, admin, _ = _confirmed_home()

        res = auth_client(admin).get(_URL, {"week_start": "2026-07-14"})

        assert res.status_code == 400

    def test_집이_없으면_404(self):
        assert auth_client(UserFactory()).get(_URL).status_code == 404

    def test_인증_없으면_401(self):
        assert APIClient().get(_URL).status_code == 401

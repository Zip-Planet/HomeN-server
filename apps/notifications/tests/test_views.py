import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.homes.models import HomeMember
from apps.homes.tests.factories import HomeFactory, HomeMemberFactory
from apps.notifications.models import Notification, NotificationCategory
from apps.notifications.services import notify_home
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

_URL = "/api/v1/notifications/"


def auth_client(user) -> APIClient:
    client = APIClient()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


def _home_with_admin():
    admin = UserFactory()
    home = HomeFactory()
    HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
    return home, admin


class TestNotificationListView:
    def test_목록_조회_200(self):
        home, admin = _home_with_admin()
        notify_home(home=home, category=NotificationCategory.REPORT, title="이번 주 리포트가 도착했어요")

        res = auth_client(admin).get(_URL)

        assert res.status_code == 200
        assert res.data["unread_count"] == 1
        assert res.data["retention_days"] == 7
        assert res.data["notifications"][0]["title"] == "이번 주 리포트가 도착했어요"
        assert res.data["notifications"][0]["is_read"] is False
        assert res.data["notifications"][0]["category_label"] == "리포트"

    def test_카테고리_필터(self):
        home, admin = _home_with_admin()
        notify_home(home=home, category=NotificationCategory.REPORT, title="리포트")
        notify_home(home=home, category=NotificationCategory.REWARD, title="리워드")

        res = auth_client(admin).get(_URL, {"category": "reward"})

        assert [n["title"] for n in res.data["notifications"]] == ["리워드"]

    def test_잘못된_카테고리_400(self):
        _home, admin = _home_with_admin()

        assert auth_client(admin).get(_URL, {"category": "nope"}).status_code == 400

    def test_인증_없으면_401(self):
        assert APIClient().get(_URL).status_code == 401


class TestNotificationReadView:
    def test_확인_처리_200(self):
        home, admin = _home_with_admin()
        notify_home(home=home, category=NotificationCategory.BOARD, title="도움이 필요해요")
        notification = Notification.objects.first()

        res = auth_client(admin).post(f"{_URL}{notification.id}/read/")

        assert res.status_code == 200
        assert res.data["is_read"] is True

    def test_남의_알림은_404(self):
        home, admin = _home_with_admin()
        notify_home(home=home, category=NotificationCategory.BOARD, title="도움이 필요해요")
        notification = Notification.objects.first()

        res = auth_client(UserFactory()).post(f"{_URL}{notification.id}/read/")

        assert res.status_code == 404


class TestNotificationSettingView:
    url = f"{_URL}settings/"

    def test_조회_시_기본값_생성(self):
        _home, admin = _home_with_admin()

        res = auth_client(admin).get(self.url)

        assert res.status_code == 200
        assert res.data["push_enabled"] is True
        assert res.data["board"] is True

    def test_부분_수정_200(self):
        _home, admin = _home_with_admin()

        res = auth_client(admin).patch(self.url, {"board": False}, format="json")

        assert res.status_code == 200
        assert res.data["board"] is False
        assert res.data["reward"] is True


class TestAssignmentNudgeView:
    url = "/api/v1/homes/mine/assignments/nudge/"

    def test_재촉_201(self):
        home, admin = _home_with_admin()
        member = UserFactory()
        HomeMemberFactory(home=home, user=member, role=HomeMember.Role.MEMBER)

        res = auth_client(member).post(self.url, {}, format="json")

        assert res.status_code == 201
        assert res.data["notified_count"] == 1
        assert Notification.objects.filter(recipient=admin).count() == 1

    def test_집이_없으면_404(self):
        assert auth_client(UserFactory()).post(self.url, {}, format="json").status_code == 404

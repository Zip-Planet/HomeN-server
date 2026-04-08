import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.homes.models import Home, HomeMember
from apps.homes.tests.factories import (
    ChoreFactory,
    HomeFactory,
    HomeImageFactory,
    HomeMemberFactory,
    StarterPackFactory,
)
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def auth_client(user) -> APIClient:
    """인증된 API 클라이언트를 반환합니다."""
    client = APIClient()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


class TestHomeCreateView:
    def test_집_생성_성공(self):
        user = UserFactory()
        image = HomeImageFactory()
        client = auth_client(user)

        res = client.post("/api/v1/homes/", {"name": "우리집", "image_id": image.pk})

        assert res.status_code == 201
        assert res.data["name"] == "우리집"
        assert res.data["status"] == "draft"
        assert res.data["creation_step"] == 1

    def test_특수문자_이름_실패(self):
        user = UserFactory()
        image = HomeImageFactory()
        client = auth_client(user)

        res = client.post("/api/v1/homes/", {"name": "우리집!", "image_id": image.pk})

        assert res.status_code == 400

    def test_이미_집_있으면_실패(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user)
        image = HomeImageFactory()
        client = auth_client(user)

        res = client.post("/api/v1/homes/", {"name": "새집", "image_id": image.pk})

        assert res.status_code == 400


class TestHomeDetailView:
    def test_내_집_조회(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user)
        client = auth_client(user)

        res = client.get("/api/v1/homes/mine/")

        assert res.status_code == 200
        assert res.data["id"] == home.pk

    def test_집_없으면_404(self):
        user = UserFactory()
        client = auth_client(user)

        res = client.get("/api/v1/homes/mine/")

        assert res.status_code == 404


class TestHomeChoreView:
    def test_집안일_추가_성공(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        pack = StarterPackFactory()
        ChoreFactory(starter_pack=pack)
        client = auth_client(user)

        res = client.post(f"/api/v1/homes/{home.pk}/chores/", {"starter_pack_id": pack.pk})

        assert res.status_code == 201
        assert len(res.data) == 1

    def test_구성원은_403(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.MEMBER)
        pack = StarterPackFactory()
        client = auth_client(user)

        res = client.post(f"/api/v1/homes/{home.pk}/chores/", {"starter_pack_id": pack.pk})

        assert res.status_code == 403


class TestHomeRewardView:
    def test_리워드_일괄_등록_성공(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        client = auth_client(user)
        payload = [{"name": "치킨", "goal_point": 100}, {"name": "영화", "goal_point": 200}]

        res = client.post(f"/api/v1/homes/{home.pk}/rewards/", payload, format="json")

        assert res.status_code == 201
        assert len(res.data) == 2
        home.refresh_from_db()
        assert home.status == Home.Status.ACTIVE


class TestHomeInviteView:
    def test_초대코드_조회_성공(self):
        user = UserFactory()
        home = HomeFactory(status=Home.Status.ACTIVE, invite_code="ABC123")
        HomeMemberFactory(home=home, user=UserFactory(), role=HomeMember.Role.ADMIN)
        client = auth_client(user)

        res = client.get("/api/v1/homes/invite/ABC123/")

        assert res.status_code == 200
        assert res.data["invite_code"] == "ABC123"
        assert res.data["member_count"] == 1

    def test_draft_집은_404(self):
        user = UserFactory()
        home = HomeFactory(status=Home.Status.DRAFT, invite_code="DRF999")
        client = auth_client(user)

        res = client.get("/api/v1/homes/invite/DRF999/")

        assert res.status_code == 404


class TestHomeJoinView:
    def test_집_참여_성공(self):
        user = UserFactory()
        home = HomeFactory(status=Home.Status.ACTIVE)
        client = auth_client(user)

        res = client.post("/api/v1/homes/join/", {"invite_code": home.invite_code})

        assert res.status_code == 200
        assert HomeMember.objects.filter(user=user, home=home).exists()

    def test_이미_집_있으면_400(self):
        user = UserFactory()
        existing = HomeFactory(status=Home.Status.ACTIVE)
        HomeMemberFactory(home=existing, user=user)
        another = HomeFactory(status=Home.Status.ACTIVE)
        client = auth_client(user)

        res = client.post("/api/v1/homes/join/", {"invite_code": another.invite_code})

        assert res.status_code == 400

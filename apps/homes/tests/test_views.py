import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.homes.models import Chore, ChoreCategory, Home, HomeMember, HomeImageType
from apps.homes.tests.factories import HomeFactory, HomeMemberFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def auth_client(user) -> APIClient:
    """인증된 API 클라이언트를 반환합니다."""
    client = APIClient()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


class TestHomeCreateView:
    url = "/api/v1/homes/"

    def test_집안일_리워드_없이_생성_성공(self):
        user = UserFactory()
        client = auth_client(user)
        payload = {"name": "우리집", "image_id": HomeImageType.TYPE_1, "chores": [], "rewards": []}

        res = client.post(self.url, payload, format="json")

        assert res.status_code == 201
        assert res.data["name"] == "우리집"
        assert res.data["status"] == Home.Status.ACTIVE
        assert HomeMember.objects.filter(user=user, role=HomeMember.Role.ADMIN).exists()

    def test_집안일_리워드_포함_생성_성공(self):
        user = UserFactory()
        client = auth_client(user)
        payload = {
            "name": "우리집",
            "image_id": HomeImageType.TYPE_1,
            "chores": [
                {"category": ChoreCategory.DISHES, "name": "설거지", "description": "그릇 닦기", "repeat_days": [0, 2], "difficulty": Chore.Difficulty.LOW},
                {"category": ChoreCategory.VACUUM, "name": "청소기", "description": "", "repeat_days": [], "difficulty": Chore.Difficulty.MEDIUM},
            ],
            "rewards": [{"name": "치킨", "goal_point": 100}],
        }

        res = client.post(self.url, payload, format="json")

        assert res.status_code == 201
        home = Home.objects.get(pk=res.data["id"])
        assert home.home_chores.count() == 2
        assert home.rewards.count() == 1

    def test_특수문자_이름_실패(self):
        user = UserFactory()
        client = auth_client(user)

        res = client.post(
            self.url,
            {"name": "우리집!", "image_id": HomeImageType.TYPE_1, "chores": [], "rewards": []},
            format="json",
        )

        assert res.status_code == 400

    def test_잘못된_이미지_id_실패(self):
        user = UserFactory()
        client = auth_client(user)

        res = client.post(
            self.url,
            {"name": "우리집", "image_id": 9999, "chores": [], "rewards": []},
            format="json",
        )

        assert res.status_code == 400

    def test_이미_집_있으면_400(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user)
        client = auth_client(user)

        res = client.post(
            self.url,
            {"name": "새집", "image_id": HomeImageType.TYPE_1, "chores": [], "rewards": []},
            format="json",
        )

        assert res.status_code == 400

    def test_잘못된_집안일_이미지_400(self):
        user = UserFactory()
        client = auth_client(user)

        res = client.post(
            self.url,
            {
                "name": "우리집",
                "image_id": HomeImageType.TYPE_1,
                "chores": [{"category": 9999, "name": "설거지", "description": "", "repeat_days": [], "difficulty": Chore.Difficulty.LOW}],
                "rewards": [],
            },
            format="json",
        )

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
        assert "creation_step" not in res.data

    def test_집_없으면_404(self):
        user = UserFactory()
        client = auth_client(user)

        res = client.get("/api/v1/homes/mine/")

        assert res.status_code == 404


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

    def test_소문자_초대코드로_조회_성공(self):
        user = UserFactory()
        home = HomeFactory(status=Home.Status.ACTIVE, invite_code="ABC123")
        HomeMemberFactory(home=home, user=UserFactory(), role=HomeMember.Role.ADMIN)
        client = auth_client(user)

        res = client.get("/api/v1/homes/invite/abc123/")

        assert res.status_code == 200
        assert res.data["invite_code"] == "ABC123"

    def test_존재하지_않는_코드_404(self):
        user = UserFactory()
        client = auth_client(user)

        res = client.get("/api/v1/homes/invite/XXXXXX/")

        assert res.status_code == 404


class TestHomeJoinView:
    def test_집_참여_성공(self):
        user = UserFactory()
        home = HomeFactory(status=Home.Status.ACTIVE)
        client = auth_client(user)

        res = client.post("/api/v1/homes/join/", {"invite_code": home.invite_code})

        assert res.status_code == 200
        assert HomeMember.objects.filter(user=user, home=home).exists()

    def test_소문자_초대코드로_참여_성공(self):
        user = UserFactory()
        home = HomeFactory(status=Home.Status.ACTIVE, invite_code="ABC123")
        client = auth_client(user)

        res = client.post("/api/v1/homes/join/", {"invite_code": "abc123"})

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


class TestHomeDeleteView:
    url = "/api/v1/homes/mine/"

    def test_관리자_혼자일_때_삭제_성공(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        client = auth_client(user)

        res = client.delete(self.url)

        assert res.status_code == 204
        assert not Home.objects.filter(pk=home.pk).exists()

    def test_구성원_있으면_삭제_불가_400(self):
        admin = UserFactory()
        member = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
        HomeMemberFactory(home=home, user=member, role=HomeMember.Role.MEMBER)
        client = auth_client(admin)

        res = client.delete(self.url)

        assert res.status_code == 400
        assert Home.objects.filter(pk=home.pk).exists()

    def test_구성원은_집_삭제_불가_403(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.MEMBER)
        client = auth_client(user)

        res = client.delete(self.url)

        assert res.status_code == 403

    def test_미인증_401(self):
        res = APIClient().delete(self.url)

        assert res.status_code == 401


class TestHomeLeaveView:
    url = "/api/v1/homes/mine/leave/"

    def test_구성원_집_나가기_성공(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.MEMBER)
        client = auth_client(user)

        res = client.post(self.url)

        assert res.status_code == 204
        assert not HomeMember.objects.filter(user=user).exists()
        assert Home.objects.filter(pk=home.pk).exists()

    def test_관리자_집_나가기_불가_403(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        client = auth_client(user)

        res = client.post(self.url)

        assert res.status_code == 403
        assert HomeMember.objects.filter(user=user).exists()

    def test_집_없는_유저_404(self):
        user = UserFactory()
        client = auth_client(user)

        res = client.post(self.url)

        assert res.status_code == 404

    def test_미인증_401(self):
        res = APIClient().post(self.url)

        assert res.status_code == 401


class TestHomeTransferAdminView:
    url = "/api/v1/homes/mine/transfer-admin/"

    def test_관리자_양도_성공(self):
        admin = UserFactory()
        member = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
        HomeMemberFactory(home=home, user=member, role=HomeMember.Role.MEMBER)
        client = auth_client(admin)

        res = client.post(self.url, {"user_id": str(member.uid)}, format="json")

        assert res.status_code == 204
        assert HomeMember.objects.get(user=admin).role == HomeMember.Role.MEMBER
        assert HomeMember.objects.get(user=member).role == HomeMember.Role.ADMIN

    def test_구성원은_양도_불가_403(self):
        user = UserFactory()
        other = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.MEMBER)
        HomeMemberFactory(home=home, user=other, role=HomeMember.Role.MEMBER)
        client = auth_client(user)

        res = client.post(self.url, {"user_id": str(other.uid)}, format="json")

        assert res.status_code == 403

    def test_다른_집_구성원에게_양도_불가_400(self):
        admin = UserFactory()
        outsider = UserFactory()
        home = HomeFactory()
        other_home = HomeFactory()
        HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
        HomeMemberFactory(home=other_home, user=outsider, role=HomeMember.Role.MEMBER)
        client = auth_client(admin)

        res = client.post(self.url, {"user_id": str(outsider.uid)}, format="json")

        assert res.status_code == 400

    def test_미인증_401(self):
        res = APIClient().post(self.url, {}, format="json")

        assert res.status_code == 401

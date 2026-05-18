from datetime import date, timedelta
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.homes.models import Chore, ChoreCategory, Home, HomeChore, HomeMember, HomeImageType
from apps.homes.tests.factories import (
    ChoreCompletionFactory,
    ChoreFactory,
    HomeChoreFactory,
    HomeFactory,
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
                {"category": ChoreCategory.CLEANING, "name": "청소", "description": "방 청소", "repeat_days": [0, 2], "difficulty": Chore.Difficulty.LOW},
                {"category": ChoreCategory.LAUNDRY, "name": "세탁", "description": "", "repeat_days": [], "difficulty": Chore.Difficulty.MEDIUM},
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

    def test_스타터팩_적용으로_생성_성공(self):
        user = UserFactory()
        pack = StarterPackFactory()
        ChoreFactory(starter_pack=pack, name="청소기 돌리기")
        ChoreFactory(starter_pack=pack, name="설거지")
        client = auth_client(user)

        res = client.post(
            self.url,
            {
                "name": "우리집",
                "image_id": HomeImageType.TYPE_1,
                "starter_pack_id": pack.id,
                "chores": [],
                "rewards": [],
            },
            format="json",
        )

        assert res.status_code == 201
        home = Home.objects.get(id=res.data["id"])
        assert HomeChore.objects.filter(home=home).count() == 2

    def test_스타터팩_id_와_chores_동시_지정_400(self):
        user = UserFactory()
        pack = StarterPackFactory()
        client = auth_client(user)

        res = client.post(
            self.url,
            {
                "name": "우리집",
                "image_id": HomeImageType.TYPE_1,
                "starter_pack_id": pack.id,
                "chores": [
                    {"category": ChoreCategory.TRASH, "name": "쓰레기", "description": "", "repeat_days": [], "difficulty": Chore.Difficulty.LOW},
                ],
                "rewards": [],
            },
            format="json",
        )

        assert res.status_code == 400
        assert "ambiguous_chore_input" in res.data

    def test_잘못된_starter_pack_id_404(self):
        user = UserFactory()
        client = auth_client(user)

        res = client.post(
            self.url,
            {
                "name": "우리집",
                "image_id": HomeImageType.TYPE_1,
                "starter_pack_id": 99999,
                "chores": [],
                "rewards": [],
            },
            format="json",
        )

        assert res.status_code == 404


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

    def test_members_포함_조회(self):
        admin = UserFactory(name="관리자", profile_image=1)
        member = UserFactory(name="구성원", profile_image=2)
        home = HomeFactory()
        HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
        HomeMemberFactory(home=home, user=member, role=HomeMember.Role.MEMBER)
        client = auth_client(admin)

        res = client.get("/api/v1/homes/mine/")

        assert res.status_code == 200
        members = res.data["members"]
        assert len(members) == 2
        admin_data = next(m for m in members if m["role"] == HomeMember.Role.ADMIN)
        member_data = next(m for m in members if m["role"] == HomeMember.Role.MEMBER)
        assert admin_data["name"] == "관리자"
        assert admin_data["profile_image"] == 1
        assert admin_data["role_label"] == "관리자"
        assert member_data["name"] == "구성원"
        assert member_data["profile_image"] == 2
        assert member_data["role_label"] == "구성원"

    def test_members_profile_image_null_허용(self):
        user = UserFactory(profile_image=None)
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.MEMBER)
        client = auth_client(user)

        res = client.get("/api/v1/homes/mine/")

        assert res.status_code == 200
        assert res.data["members"][0]["profile_image"] is None

    def test_집_없으면_404(self):
        user = UserFactory()
        client = auth_client(user)

        res = client.get("/api/v1/homes/mine/")

        assert res.status_code == 404


class TestHomeMembershipView:
    def test_집_있으면_has_home_true(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user)
        client = auth_client(user)

        res = client.get("/api/v1/homes/mine/membership/")

        assert res.status_code == 200
        assert res.data["has_home"] is True

    def test_집_없으면_has_home_false(self):
        user = UserFactory()
        client = auth_client(user)

        res = client.get("/api/v1/homes/mine/membership/")

        assert res.status_code == 200
        assert res.data["has_home"] is False


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


class TestHomeChoreListView:
    url = "/api/v1/homes/mine/chores/"

    def test_관리자_집안일_생성_성공(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        client = auth_client(user)
        payload = {
            "chores": [
                {"category": ChoreCategory.TRASH, "name": "쓰레기 버리기", "description": "분리수거", "repeat_days": [0, 3], "difficulty": Chore.Difficulty.LOW},
                {"category": ChoreCategory.LAUNDRY, "name": "세탁", "description": "", "repeat_days": [], "difficulty": Chore.Difficulty.MEDIUM},
            ]
        }

        res = client.post(self.url, payload, format="json")

        assert res.status_code == 201
        assert len(res.data) == 2
        assert res.data[0]["name"] == "쓰레기 버리기"
        assert HomeChore.objects.filter(home=home).count() == 2

    def test_단건_생성_성공(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        client = auth_client(user)
        payload = {
            "chores": [
                {"category": ChoreCategory.KITCHEN, "name": "설거지", "description": "", "repeat_days": [1], "difficulty": Chore.Difficulty.MEDIUM_LOW},
            ]
        }

        res = client.post(self.url, payload, format="json")

        assert res.status_code == 201
        assert len(res.data) == 1

    def test_구성원도_집안일_생성_가능(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.MEMBER)
        client = auth_client(user)
        payload = {"chores": [{"category": ChoreCategory.TRASH, "name": "쓰레기", "description": "", "repeat_days": [], "difficulty": Chore.Difficulty.LOW}]}

        res = client.post(self.url, payload, format="json")

        assert res.status_code == 201

    def test_집_없는_유저_404(self):
        user = UserFactory()
        client = auth_client(user)
        payload = {"chores": [{"category": ChoreCategory.TRASH, "name": "쓰레기", "description": "", "repeat_days": [], "difficulty": Chore.Difficulty.LOW}]}

        res = client.post(self.url, payload, format="json")

        assert res.status_code == 404

    def test_잘못된_카테고리_400(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        client = auth_client(user)
        payload = {"chores": [{"category": 9999, "name": "집안일", "description": "", "repeat_days": [], "difficulty": Chore.Difficulty.LOW}]}

        res = client.post(self.url, payload, format="json")

        assert res.status_code == 400

    def test_제목_20자_초과_400(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        client = auth_client(user)
        payload = {"chores": [{"category": ChoreCategory.TRASH, "name": "a" * 21, "description": "", "repeat_days": [], "difficulty": Chore.Difficulty.LOW}]}

        res = client.post(self.url, payload, format="json")

        assert res.status_code == 400

    def test_설명_20자_초과_400(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        client = auth_client(user)
        payload = {"chores": [{"category": ChoreCategory.TRASH, "name": "집안일", "description": "a" * 21, "repeat_days": [], "difficulty": Chore.Difficulty.LOW}]}

        res = client.post(self.url, payload, format="json")

        assert res.status_code == 400

    def test_미인증_401(self):
        res = APIClient().post(self.url, {}, format="json")

        assert res.status_code == 401

    def test_스타터팩_적용_성공(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        pack = StarterPackFactory()
        ChoreFactory(starter_pack=pack, name="청소기 돌리기")
        ChoreFactory(starter_pack=pack, name="설거지")
        client = auth_client(user)

        res = client.post(self.url, {"starter_pack_id": pack.id}, format="json")

        assert res.status_code == 201
        assert len(res.data) == 2
        assert HomeChore.objects.filter(home=home).count() == 2

    def test_스타터팩_재적용은_멱등(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        pack = StarterPackFactory()
        ChoreFactory(starter_pack=pack)
        client = auth_client(user)

        first = client.post(self.url, {"starter_pack_id": pack.id}, format="json")
        second = client.post(self.url, {"starter_pack_id": pack.id}, format="json")

        assert first.status_code == 201
        assert second.status_code == 201
        # 두 번째 호출은 새로 생긴 게 없음
        assert second.data == []
        assert HomeChore.objects.filter(home=home).count() == 1

    def test_starter_pack_id_와_chores_동시_지정_400(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        pack = StarterPackFactory()
        client = auth_client(user)
        payload = {
            "starter_pack_id": pack.id,
            "chores": [{"category": ChoreCategory.TRASH, "name": "쓰레기", "description": "", "repeat_days": [], "difficulty": Chore.Difficulty.LOW}],
        }

        res = client.post(self.url, payload, format="json")

        assert res.status_code == 400
        assert "ambiguous_chore_input" in res.data

    def test_둘_다_누락_400(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        client = auth_client(user)

        res = client.post(self.url, {}, format="json")

        assert res.status_code == 400
        assert "missing_chore_input" in res.data

    def test_잘못된_starter_pack_id_404(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        client = auth_client(user)

        res = client.post(self.url, {"starter_pack_id": 99999}, format="json")

        assert res.status_code == 404


class TestHomeChoreListViewGet:
    url = "/api/v1/homes/mine/chores/"

    def test_집안일_없으면_빈_배열_200(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        client = auth_client(user)

        res = client.get(self.url)

        assert res.status_code == 200
        assert res.data == []

    def test_내_집_집안일만_노출(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        mine_chore = ChoreFactory(name="내집 청소")
        HomeChoreFactory(home=home, chore=mine_chore)

        other_home = HomeFactory()
        other_chore = ChoreFactory(name="남의집 청소")
        HomeChoreFactory(home=other_home, chore=other_chore)

        client = auth_client(user)
        res = client.get(self.url)

        assert res.status_code == 200
        assert len(res.data) == 1
        assert res.data[0]["name"] == "내집 청소"

    def test_pk_오름차순_정렬(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        c1 = ChoreFactory(name="first")
        c2 = ChoreFactory(name="second")
        c3 = ChoreFactory(name="third")
        # 일부러 역순으로 부착
        HomeChoreFactory(home=home, chore=c3)
        HomeChoreFactory(home=home, chore=c2)
        HomeChoreFactory(home=home, chore=c1)

        client = auth_client(user)
        res = client.get(self.url)

        assert res.status_code == 200
        ids = [row["id"] for row in res.data]
        assert ids == sorted(ids), f"PK 오름차순이어야 함: {ids}"

    def test_응답에_point_difficulty_label_repeat_days_label_포함(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        chore = ChoreFactory(repeat_days=[0, 5], difficulty=Chore.Difficulty.MEDIUM_HIGH)  # 중상 → 중간 / 160P
        HomeChoreFactory(home=home, chore=chore)

        client = auth_client(user)
        res = client.get(self.url)

        assert res.status_code == 200
        row = res.data[0]
        assert row["difficulty_label"] == "중간"
        assert row["point"] == 160
        assert row["repeat_days_label"] == ["월", "토"]

    def test_속한_집_없으면_404(self):
        user = UserFactory()
        client = auth_client(user)

        res = client.get(self.url)

        assert res.status_code == 404

    def test_미인증_401(self):
        res = APIClient().get(self.url)

        assert res.status_code == 401


def _chore_detail_url(home_chore_id: int) -> str:
    return f"/api/v1/homes/mine/chores/{home_chore_id}/"


class TestHomeChoreDetailViewGet:
    def test_본인_집_chore_조회_200(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        chore = ChoreFactory(name="거실 청소", starter_pack=None)
        home_chore = HomeChoreFactory(home=home, chore=chore)
        client = auth_client(user)

        res = client.get(_chore_detail_url(home_chore.pk))

        assert res.status_code == 200
        assert res.data["id"] == home_chore.pk
        assert res.data["name"] == "거실 청소"

    def test_응답에_point_difficulty_label_repeat_days_label_포함(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        chore = ChoreFactory(
            starter_pack=None,
            repeat_days=[0, 5],
            difficulty=Chore.Difficulty.MEDIUM_HIGH,  # 중상 → '중간' / 160P
        )
        home_chore = HomeChoreFactory(home=home, chore=chore)
        client = auth_client(user)

        res = client.get(_chore_detail_url(home_chore.pk))

        assert res.status_code == 200
        assert res.data["difficulty_label"] == "중간"
        assert res.data["point"] == 160
        assert res.data["repeat_days_label"] == ["월", "토"]

    def test_다른_집_chore_는_404(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)

        other_home = HomeFactory()
        other_chore = ChoreFactory(starter_pack=None)
        other_home_chore = HomeChoreFactory(home=other_home, chore=other_chore)
        client = auth_client(user)

        res = client.get(_chore_detail_url(other_home_chore.pk))

        assert res.status_code == 404

    def test_존재하지_않는_chore_404(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        client = auth_client(user)

        res = client.get(_chore_detail_url(99999))

        assert res.status_code == 404

    def test_속한_집_없으면_404(self):
        user = UserFactory()
        client = auth_client(user)

        res = client.get(_chore_detail_url(1))

        assert res.status_code == 404

    def test_미인증_401(self):
        res = APIClient().get(_chore_detail_url(1))

        assert res.status_code == 401


class TestHomeChoreDetailViewWeeklyProgress:
    """이번 주(월~일) 진행상태 응답 검증.

    `timezone.localdate` 를 `frozen_today` (수요일) 로 픽스해 주 경계를 안정화.
    이번 주 = 2026-05-11(월) ~ 2026-05-17(일).
    """

    frozen_today = date(2026, 5, 13)  # 수요일
    monday = date(2026, 5, 11)
    sunday = date(2026, 5, 17)

    def _freeze(self):
        return patch("apps.homes.selectors.timezone.localdate", return_value=self.frozen_today)

    def test_완료이력_0건이면_repeat_days_만_incomplete_나머지는_not_scheduled(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        chore = ChoreFactory(starter_pack=None, repeat_days=[0, 3])  # 월/목
        home_chore = HomeChoreFactory(home=home, chore=chore)
        client = auth_client(user)

        with self._freeze():
            res = client.get(_chore_detail_url(home_chore.pk))

        assert res.status_code == 200
        progress = res.data["weekly_progress"]
        assert len(progress) == 7
        assert [p["weekday"] for p in progress] == [0, 1, 2, 3, 4, 5, 6]
        assert [p["label"] for p in progress] == ["월", "화", "수", "목", "금", "토", "일"]
        statuses = {p["weekday"]: p["status"] for p in progress}
        assert statuses[0] == "incomplete"
        assert statuses[3] == "incomplete"
        for non_repeat in (1, 2, 4, 5, 6):
            assert statuses[non_repeat] == "not_scheduled"
        assert all(p["completed_by"] is None for p in progress)

    def test_이번주_월요일_완료이력_있으면_요청자_닉네임_표시(self):
        user = UserFactory(name="홍길동", profile_image=3)
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        chore = ChoreFactory(starter_pack=None, repeat_days=[0, 3])
        home_chore = HomeChoreFactory(home=home, chore=chore)
        ChoreCompletionFactory(home_chore=home_chore, completed_by=user, date=self.monday)
        client = auth_client(user)

        with self._freeze():
            res = client.get(_chore_detail_url(home_chore.pk))

        assert res.status_code == 200
        mon = next(p for p in res.data["weekly_progress"] if p["weekday"] == 0)
        assert mon["status"] == "completed"
        assert mon["completed_by"] == {
            "uid": str(user.uid),
            "name": "홍길동",
            "profile_image": 3,
        }
        thu = next(p for p in res.data["weekly_progress"] if p["weekday"] == 3)
        assert thu["status"] == "incomplete"
        assert thu["completed_by"] is None

    def test_같은집_다른멤버가_완료해도_그_사람_닉네임으로_표시(self):
        admin = UserFactory(name="나", profile_image=1)
        other = UserFactory(name="룸메이트", profile_image=5)
        home = HomeFactory()
        HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
        HomeMemberFactory(home=home, user=other, role=HomeMember.Role.MEMBER)
        chore = ChoreFactory(starter_pack=None, repeat_days=[2])  # 수
        home_chore = HomeChoreFactory(home=home, chore=chore)
        ChoreCompletionFactory(
            home_chore=home_chore,
            completed_by=other,
            date=self.monday + timedelta(days=2),  # 수요일
        )
        client = auth_client(admin)

        with self._freeze():
            res = client.get(_chore_detail_url(home_chore.pk))

        assert res.status_code == 200
        wed = next(p for p in res.data["weekly_progress"] if p["weekday"] == 2)
        assert wed["status"] == "completed"
        assert wed["completed_by"]["name"] == "룸메이트"
        assert wed["completed_by"]["profile_image"] == 5

    def test_지난주_완료이력은_이번주_응답에_반영되지_않음(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        chore = ChoreFactory(starter_pack=None, repeat_days=[0])
        home_chore = HomeChoreFactory(home=home, chore=chore)
        # 지난 주 월요일 완료 — 이번 주 윈도우 밖.
        ChoreCompletionFactory(
            home_chore=home_chore,
            completed_by=user,
            date=self.monday - timedelta(days=7),
        )
        client = auth_client(user)

        with self._freeze():
            res = client.get(_chore_detail_url(home_chore.pk))

        assert res.status_code == 200
        mon = next(p for p in res.data["weekly_progress"] if p["weekday"] == 0)
        assert mon["status"] == "incomplete"
        assert mon["completed_by"] is None

    def test_다른_집_완료이력은_누수되지_않음(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        chore = ChoreFactory(starter_pack=None, repeat_days=[0])
        home_chore = HomeChoreFactory(home=home, chore=chore)

        # 같은 chore 인스턴스를 공유하는 별개 집에서 완료
        other_home = HomeFactory()
        other_home_chore = HomeChoreFactory(home=other_home, chore=ChoreFactory(starter_pack=None, repeat_days=[0]))
        ChoreCompletionFactory(home_chore=other_home_chore, completed_by=user, date=self.monday)

        client = auth_client(user)
        with self._freeze():
            res = client.get(_chore_detail_url(home_chore.pk))

        assert res.status_code == 200
        mon = next(p for p in res.data["weekly_progress"] if p["weekday"] == 0)
        assert mon["status"] == "incomplete"

    def test_완료자_탈퇴된_경우_completed_by_null_이지만_completed_유지(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        chore = ChoreFactory(starter_pack=None, repeat_days=[0])
        home_chore = HomeChoreFactory(home=home, chore=chore)
        # completed_by 가 SET_NULL 된 상태
        ChoreCompletionFactory(home_chore=home_chore, completed_by=None, date=self.monday)
        client = auth_client(user)

        with self._freeze():
            res = client.get(_chore_detail_url(home_chore.pk))

        assert res.status_code == 200
        mon = next(p for p in res.data["weekly_progress"] if p["weekday"] == 0)
        assert mon["status"] == "completed"
        assert mon["completed_by"] is None

    def test_목록_응답에는_weekly_progress_없음(self):
        """회귀 점검: list/PATCH 는 기존 시리얼라이저를 유지한다."""
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        chore = ChoreFactory(starter_pack=None)
        HomeChoreFactory(home=home, chore=chore)
        client = auth_client(user)

        res = client.get("/api/v1/homes/mine/chores/")

        assert res.status_code == 200
        assert all("weekly_progress" not in item for item in res.data)


class TestHomeChoreDetailViewPatch:
    def test_커스텀_chore_부분수정_200_in_place(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        chore = ChoreFactory(starter_pack=None, name="기존", difficulty=Chore.Difficulty.LOW)
        home_chore = HomeChoreFactory(home=home, chore=chore)
        client = auth_client(user)
        original_chore_id = chore.pk

        res = client.patch(
            _chore_detail_url(home_chore.pk),
            {"name": "수정됨", "difficulty": Chore.Difficulty.HIGH},
            format="json",
        )

        assert res.status_code == 200
        home_chore.refresh_from_db()
        chore.refresh_from_db()
        # 커스텀 chore 는 in-place 업데이트 — 동일 PK 유지
        assert home_chore.chore_id == original_chore_id
        assert chore.name == "수정됨"
        assert chore.difficulty == Chore.Difficulty.HIGH

    def test_스타터팩_chore_수정시_copy_on_write(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)

        starter_pack = StarterPackFactory()
        preset_chore = ChoreFactory(
            starter_pack=starter_pack,
            name="프리셋 청소",
            difficulty=Chore.Difficulty.LOW,
        )
        home_chore = HomeChoreFactory(home=home, chore=preset_chore)
        # 다른 집도 같은 preset 을 쓰는 상황을 만들어 영향 0 을 검증
        other_home = HomeFactory()
        other_home_chore = HomeChoreFactory(home=other_home, chore=preset_chore)

        client = auth_client(user)
        res = client.patch(
            _chore_detail_url(home_chore.pk),
            {"name": "내 집 청소", "difficulty": Chore.Difficulty.HIGH},
            format="json",
        )

        assert res.status_code == 200
        home_chore.refresh_from_db()
        preset_chore.refresh_from_db()
        other_home_chore.refresh_from_db()

        # 원본 preset Chore 는 보존
        assert preset_chore.name == "프리셋 청소"
        assert preset_chore.difficulty == Chore.Difficulty.LOW
        assert preset_chore.starter_pack_id == starter_pack.pk

        # 내 집 HomeChore 는 새 Chore 로 교체 (copy-on-write)
        assert home_chore.chore_id != preset_chore.pk
        assert home_chore.chore.starter_pack_id is None
        assert home_chore.chore.name == "내 집 청소"
        assert home_chore.chore.difficulty == Chore.Difficulty.HIGH

        # 다른 집의 연결은 그대로
        assert other_home_chore.chore_id == preset_chore.pk

    def test_관리자_아닌_구성원도_수정_가능_200(self):
        admin = UserFactory()
        member = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
        HomeMemberFactory(home=home, user=member, role=HomeMember.Role.MEMBER)
        chore = ChoreFactory(starter_pack=None, name="기존")
        home_chore = HomeChoreFactory(home=home, chore=chore)
        client = auth_client(member)

        res = client.patch(
            _chore_detail_url(home_chore.pk),
            {"name": "구성원이 수정"},
            format="json",
        )

        assert res.status_code == 200
        chore.refresh_from_db()
        assert chore.name == "구성원이 수정"

    def test_다른_집_chore_수정_404(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)

        other_home = HomeFactory()
        other_chore = ChoreFactory(starter_pack=None, name="원래")
        other_home_chore = HomeChoreFactory(home=other_home, chore=other_chore)
        client = auth_client(user)

        res = client.patch(
            _chore_detail_url(other_home_chore.pk),
            {"name": "침입"},
            format="json",
        )

        assert res.status_code == 404
        other_chore.refresh_from_db()
        assert other_chore.name == "원래"

    def test_빈_바디_200_변경없음(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        chore = ChoreFactory(starter_pack=None, name="그대로")
        home_chore = HomeChoreFactory(home=home, chore=chore)
        client = auth_client(user)

        res = client.patch(_chore_detail_url(home_chore.pk), {}, format="json")

        assert res.status_code == 200
        chore.refresh_from_db()
        assert chore.name == "그대로"

    def test_유효성_실패_400(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        chore = ChoreFactory(starter_pack=None)
        home_chore = HomeChoreFactory(home=home, chore=chore)
        client = auth_client(user)

        res = client.patch(
            _chore_detail_url(home_chore.pk),
            {"difficulty": 9999},
            format="json",
        )

        assert res.status_code == 400

    def test_미인증_401(self):
        res = APIClient().patch(_chore_detail_url(1), {"name": "x"}, format="json")

        assert res.status_code == 401


class TestHomeChoreDetailViewDelete:
    def test_커스텀_chore_삭제_204(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        chore = ChoreFactory(starter_pack=None)
        home_chore = HomeChoreFactory(home=home, chore=chore)
        client = auth_client(user)

        res = client.delete(_chore_detail_url(home_chore.pk))

        assert res.status_code == 204
        assert not HomeChore.objects.filter(pk=home_chore.pk).exists()
        # 원본 Chore 는 보존 (orphan 허용 — 별도 정책 없음)
        assert Chore.objects.filter(pk=chore.pk).exists()

    def test_스타터팩_chore_삭제_204_원본_보존(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)

        starter_pack = StarterPackFactory()
        preset_chore = ChoreFactory(starter_pack=starter_pack, name="프리셋")
        home_chore = HomeChoreFactory(home=home, chore=preset_chore)

        other_home = HomeFactory()
        other_home_chore = HomeChoreFactory(home=other_home, chore=preset_chore)

        client = auth_client(user)
        res = client.delete(_chore_detail_url(home_chore.pk))

        assert res.status_code == 204
        # HomeChore 만 사라짐
        assert not HomeChore.objects.filter(pk=home_chore.pk).exists()
        # 원본 preset Chore 는 보존
        preset_chore.refresh_from_db()
        assert preset_chore.name == "프리셋"
        # 다른 집의 연결도 그대로
        assert HomeChore.objects.filter(pk=other_home_chore.pk).exists()

    def test_관리자_아닌_구성원도_삭제_가능_204(self):
        admin = UserFactory()
        member = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
        HomeMemberFactory(home=home, user=member, role=HomeMember.Role.MEMBER)
        chore = ChoreFactory(starter_pack=None)
        home_chore = HomeChoreFactory(home=home, chore=chore)
        client = auth_client(member)

        res = client.delete(_chore_detail_url(home_chore.pk))

        assert res.status_code == 204
        assert not HomeChore.objects.filter(pk=home_chore.pk).exists()

    def test_다른_집_chore_삭제_404(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)

        other_home = HomeFactory()
        other_chore = ChoreFactory(starter_pack=None)
        other_home_chore = HomeChoreFactory(home=other_home, chore=other_chore)
        client = auth_client(user)

        res = client.delete(_chore_detail_url(other_home_chore.pk))

        assert res.status_code == 404
        assert HomeChore.objects.filter(pk=other_home_chore.pk).exists()

    def test_미인증_401(self):
        res = APIClient().delete(_chore_detail_url(1))

        assert res.status_code == 401


def _note_list_url(home_chore_id: int) -> str:
    return f"/api/v1/homes/mine/chores/{home_chore_id}/notes/"


def _note_detail_url(home_chore_id: int, note_id: int) -> str:
    return f"/api/v1/homes/mine/chores/{home_chore_id}/notes/{note_id}/"


class TestHomeChoreNoteListView:
    def test_메모_작성_성공(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        chore = ChoreFactory(starter_pack=None)
        home_chore = HomeChoreFactory(home=home, chore=chore)
        client = auth_client(user)

        res = client.post(_note_list_url(home_chore.pk), {"content": "환기 필수"}, format="json")

        assert res.status_code == 201
        assert res.data["content"] == "환기 필수"
        assert res.data["author"]["uid"] == str(user.uid)

    def test_빈_content_400(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user)
        chore = ChoreFactory(starter_pack=None)
        home_chore = HomeChoreFactory(home=home, chore=chore)
        client = auth_client(user)

        res = client.post(_note_list_url(home_chore.pk), {"content": ""}, format="json")

        assert res.status_code == 400

    def test_길이_초과_400(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user)
        chore = ChoreFactory(starter_pack=None)
        home_chore = HomeChoreFactory(home=home, chore=chore)
        client = auth_client(user)

        res = client.post(_note_list_url(home_chore.pk), {"content": "a" * 201}, format="json")

        assert res.status_code == 400

    def test_다른_집_집안일_404(self):
        user = UserFactory()
        home = HomeFactory()
        other_home = HomeFactory()
        HomeMemberFactory(home=home, user=user)
        other_home_chore = HomeChoreFactory(home=other_home, chore=ChoreFactory(starter_pack=None))
        client = auth_client(user)

        res = client.post(_note_list_url(other_home_chore.pk), {"content": "테스트"}, format="json")

        assert res.status_code == 404

    def test_목록_조회_성공(self):
        user = UserFactory()
        other = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user)
        HomeMemberFactory(home=home, user=other)
        chore = ChoreFactory(starter_pack=None)
        home_chore = HomeChoreFactory(home=home, chore=chore)
        client = auth_client(user)
        client.post(_note_list_url(home_chore.pk), {"content": "first"}, format="json")
        auth_client(other).post(_note_list_url(home_chore.pk), {"content": "second"}, format="json")

        res = client.get(_note_list_url(home_chore.pk))

        assert res.status_code == 200
        assert [n["content"] for n in res.data] == ["first", "second"]
        # 작성자 정보 노출 검증
        authors = [n["author"]["uid"] for n in res.data]
        assert str(user.uid) in authors and str(other.uid) in authors

    def test_메모_없을_때_빈_배열(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user)
        chore = ChoreFactory(starter_pack=None)
        home_chore = HomeChoreFactory(home=home, chore=chore)
        client = auth_client(user)

        res = client.get(_note_list_url(home_chore.pk))

        assert res.status_code == 200
        assert res.data == []

    def test_미인증_401(self):
        res = APIClient().get(_note_list_url(1))

        assert res.status_code == 401


class TestHomeChoreNoteDetailView:
    def _setup(self, *, author_role=HomeMember.Role.MEMBER):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=author_role)
        chore = ChoreFactory(starter_pack=None)
        home_chore = HomeChoreFactory(home=home, chore=chore)
        client = auth_client(user)
        post = client.post(_note_list_url(home_chore.pk), {"content": "원본"}, format="json")
        assert post.status_code == 201
        return user, home, home_chore, post.data["id"], client

    def test_작성자_수정_성공(self):
        user, home, home_chore, note_id, client = self._setup()

        res = client.patch(_note_detail_url(home_chore.pk, note_id), {"content": "수정"}, format="json")

        assert res.status_code == 200
        assert res.data["content"] == "수정"

    def test_다른_유저_수정_403(self):
        author, home, home_chore, note_id, _ = self._setup()
        other = UserFactory()
        HomeMemberFactory(home=home, user=other)
        other_client = auth_client(other)

        res = other_client.patch(_note_detail_url(home_chore.pk, note_id), {"content": "남이 수정"}, format="json")

        assert res.status_code == 403

    def test_작성자_삭제_성공(self):
        user, home, home_chore, note_id, client = self._setup()

        res = client.delete(_note_detail_url(home_chore.pk, note_id))

        assert res.status_code == 204

    def test_다른_유저_삭제_403(self):
        author, home, home_chore, note_id, _ = self._setup()
        other = UserFactory()
        HomeMemberFactory(home=home, user=other)
        other_client = auth_client(other)

        res = other_client.delete(_note_detail_url(home_chore.pk, note_id))

        assert res.status_code == 403

    def test_없는_note_id_404(self):
        user, home, home_chore, note_id, client = self._setup()

        res = client.patch(_note_detail_url(home_chore.pk, 99999), {"content": "x"}, format="json")

        assert res.status_code == 404

    def test_다른_집_집안일_404(self):
        user, home, home_chore, note_id, client = self._setup()
        other_home = HomeFactory()
        other_chore = HomeChoreFactory(home=other_home, chore=ChoreFactory(starter_pack=None))

        res = client.patch(_note_detail_url(other_chore.pk, note_id), {"content": "x"}, format="json")

        assert res.status_code == 404

    def test_미인증_401(self):
        res = APIClient().delete(_note_detail_url(1, 1))

        assert res.status_code == 401

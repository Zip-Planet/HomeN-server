import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.homes.models import Chore, ChoreCategory, Home, HomeChore, HomeMember, HomeImageType
from apps.homes.tests.factories import (
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

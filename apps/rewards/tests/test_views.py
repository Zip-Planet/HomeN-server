import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.homes.models import Chore, HomeMember
from apps.homes.services import (
    _generate_assignment_for_home,
    _mark_confirmed,
    complete_chore,
    week_start_of,
)
from apps.homes.tests.factories import ChoreFactory, HomeChoreFactory, HomeFactory, HomeMemberFactory
from apps.rewards.tests.factories import RewardFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

_REWARD_URL = "/api/v1/homes/mine/rewards/"


def auth_client(user) -> APIClient:
    client = APIClient()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


def _home_with_points(*, complete: int = 0):
    from django.utils import timezone

    admin = UserFactory()
    home = HomeFactory()
    HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
    today = timezone.localdate()
    for i in range(3):
        chore = ChoreFactory(
            starter_pack=None,
            name=f"집안일{i}",
            difficulty=Chore.Difficulty.MEDIUM,
            repeat_days=[today.weekday()],
        )
        HomeChoreFactory(home=home, chore=chore)

    assignment = _generate_assignment_for_home(home=home, week_start=week_start_of(today))
    _mark_confirmed(assignment, confirmed_by=admin)
    for item in list(assignment.items.all())[:complete]:
        complete_chore(user=admin, home_chore_id=item.home_chore_id)
    return home, admin


class TestRewardListView:
    def test_목록_헤더에_내_포인트와_상태별_개수(self):
        home, admin = _home_with_points(complete=2)  # 240P
        RewardFactory(home=home, name="가능", goal_point=100, created_by=admin)
        RewardFactory(home=home, name="진행중", goal_point=5000, created_by=admin)

        res = auth_client(admin).get(_REWARD_URL)

        assert res.status_code == 200
        assert res.data["my_point"] == 240
        assert res.data["claimable_count"] == 1
        assert res.data["in_progress_count"] == 1
        assert res.data["claimed_count"] == 0

    def test_정렬은_받기가능_진행중_완료_순(self):
        home, admin = _home_with_points(complete=3)  # 360P
        RewardFactory(home=home, name="진행중", goal_point=9999, created_by=admin)
        claimable = RewardFactory(home=home, name="가능", goal_point=100, created_by=admin)

        res = auth_client(admin).get(_REWARD_URL)

        assert [r["name"] for r in res.data["rewards"]] == ["가능", "진행중"]
        assert res.data["rewards"][0]["id"] == claimable.id

    def test_등록_201(self):
        _home, admin = _home_with_points()

        res = auth_client(admin).post(
            _REWARD_URL, {"name": "치킨 사주기", "goal_point": 1600}, format="json"
        )

        assert res.status_code == 201
        assert res.data["name"] == "치킨 사주기"
        assert res.data["created_by"]["uid"] == str(admin.uid)
        assert res.data["status"] == "in_progress"

    def test_이름_20자_초과_400(self):
        _home, admin = _home_with_points()

        res = auth_client(admin).post(
            _REWARD_URL, {"name": "가" * 21, "goal_point": 100}, format="json"
        )

        assert res.status_code == 400

    def test_집이_없으면_404(self):
        assert auth_client(UserFactory()).get(_REWARD_URL).status_code == 404

    def test_인증_없으면_401(self):
        assert APIClient().get(_REWARD_URL).status_code == 401


class TestRewardDetailView:
    def test_상세에_구성원_현황_포함(self):
        home, admin = _home_with_points(complete=2)  # 240P
        member = UserFactory()
        HomeMemberFactory(home=home, user=member, role=HomeMember.Role.MEMBER)
        reward = RewardFactory(home=home, goal_point=480, created_by=admin)

        res = auth_client(admin).get(f"{_REWARD_URL}{reward.id}/")

        assert res.status_code == 200
        assert res.data["member_progress"][0]["rank"] == 1
        assert res.data["member_progress"][0]["uid"] == str(admin.uid)
        assert res.data["member_progress"][0]["name"] == admin.name
        assert res.data["member_progress"][0]["profile_image"] == admin.profile_image
        assert res.data["member_progress"][0]["point"] == 240
        assert res.data["member_progress"][0]["achievement_rate"] == 50
        assert res.data["remaining_point"] == 240

    def test_수령_완료_리워드_상세에_수령자와_수령_일시_포함(self):
        home, admin = _home_with_points(complete=3)  # 360P
        reward = RewardFactory(home=home, goal_point=360, created_by=admin)
        client = auth_client(admin)
        client.post(f"{_REWARD_URL}{reward.id}/claim/")

        res = client.get(f"{_REWARD_URL}{reward.id}/")

        assert res.status_code == 200
        assert res.data["status"] == "claimed"
        assert res.data["claim"]["claimed_by"]["uid"] == str(admin.uid)
        assert res.data["claim"]["claimed_by"]["name"] == admin.name
        assert res.data["claim"]["claimed_point"] == 360
        assert res.data["claim"]["claimed_at"] is not None

    def test_수정_200(self):
        home, admin = _home_with_points()
        reward = RewardFactory(home=home, goal_point=100, created_by=admin)

        res = auth_client(admin).patch(
            f"{_REWARD_URL}{reward.id}/", {"goal_point": 700}, format="json"
        )

        assert res.status_code == 200
        assert res.data["goal_point"] == 700

    def test_삭제_204(self):
        home, admin = _home_with_points()
        reward = RewardFactory(home=home, created_by=admin)

        res = auth_client(admin).delete(f"{_REWARD_URL}{reward.id}/")

        assert res.status_code == 204

    def test_다른_집_리워드는_404(self):
        _home, admin = _home_with_points()
        outsider = RewardFactory()

        assert auth_client(admin).get(f"{_REWARD_URL}{outsider.id}/").status_code == 404


class TestRewardClaimView:
    def test_수령_성공_시_상태가_claimed(self):
        home, admin = _home_with_points(complete=3)  # 360P
        reward = RewardFactory(home=home, goal_point=360, created_by=admin)

        res = auth_client(admin).post(f"{_REWARD_URL}{reward.id}/claim/")

        assert res.status_code == 200
        assert res.data["status"] == "claimed"
        assert res.data["claim"]["claimed_point"] == 360
        assert res.data["claim"]["claimed_by"]["uid"] == str(admin.uid)

    def test_포인트_부족_400(self):
        home, admin = _home_with_points(complete=1)  # 120P
        reward = RewardFactory(home=home, goal_point=5000, created_by=admin)

        res = auth_client(admin).post(f"{_REWARD_URL}{reward.id}/claim/")

        assert res.status_code == 400
        assert res.data["error"]["code"] == "not_enough_points"

    def test_중복_수령_409(self):
        home, admin = _home_with_points(complete=3)
        reward = RewardFactory(home=home, goal_point=100, created_by=admin)
        client = auth_client(admin)
        client.post(f"{_REWARD_URL}{reward.id}/claim/")

        res = client.post(f"{_REWARD_URL}{reward.id}/claim/")

        assert res.status_code == 409
        assert res.data["error"]["code"] == "already_claimed"

    def test_수령된_리워드_수정은_409(self):
        home, admin = _home_with_points(complete=3)
        reward = RewardFactory(home=home, goal_point=100, created_by=admin)
        client = auth_client(admin)
        client.post(f"{_REWARD_URL}{reward.id}/claim/")

        res = client.patch(f"{_REWARD_URL}{reward.id}/", {"goal_point": 200}, format="json")

        assert res.status_code == 409

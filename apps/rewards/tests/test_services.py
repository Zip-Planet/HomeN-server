import pytest
from django.utils import timezone

from apps.homes.models import Chore, HomeMember
from apps.homes.services import (
    _generate_assignment_for_home,
    _mark_confirmed,
    complete_chore,
    week_start_of,
)
from apps.homes.tests.factories import ChoreFactory, HomeChoreFactory, HomeFactory, HomeMemberFactory
from apps.rewards.models import RewardClaim
from apps.rewards.selectors import get_member_progress, get_point_balance
from apps.rewards.services import (
    NotEnoughPointsError,
    RewardAlreadyClaimedError,
    RewardNotFoundError,
    claim_reward,
    create_reward,
    delete_reward,
    update_reward,
)
from apps.rewards.tests.factories import RewardFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _home_with_points(*, chore_count: int = 3, complete: int = 0):
    """관리자 1인 집 + 확정 분담안을 만들고 `complete` 건을 완료 처리합니다."""
    admin = UserFactory()
    home = HomeFactory()
    HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
    today = timezone.localdate()
    for i in range(chore_count):
        chore = ChoreFactory(
            starter_pack=None,
            name=f"집안일{i}",
            difficulty=Chore.Difficulty.MEDIUM,  # 120P
            repeat_days=[today.weekday()],
        )
        HomeChoreFactory(home=home, chore=chore)

    assignment = _generate_assignment_for_home(home=home, week_start=week_start_of(today))
    _mark_confirmed(assignment, confirmed_by=admin)
    for item in list(assignment.items.all())[:complete]:
        complete_chore(user=admin, home_chore_id=item.home_chore_id)
    return home, admin


class TestPointBalance:
    def test_완료_포인트가_잔액이_된다(self):
        _home, admin = _home_with_points(complete=2)

        assert get_point_balance(user=admin) == 240

    def test_완료가_없으면_0(self):
        _home, admin = _home_with_points(complete=0)

        assert get_point_balance(user=admin) == 0

    def test_수령하면_잔액이_차감된다(self):
        home, admin = _home_with_points(complete=3)  # 360P
        reward = RewardFactory(home=home, goal_point=200, created_by=admin)

        claim_reward(user=admin, reward_id=reward.id)

        assert get_point_balance(user=admin) == 160


class TestCreateReward:
    def test_등록하면_작성자가_기록된다(self):
        home, admin = _home_with_points()

        reward = create_reward(user=admin, name="치킨", goal_point=500)

        assert reward.home == home
        assert reward.created_by == admin
        assert reward.goal_point == 500

    def test_집이_없으면_에러(self):
        from apps.rewards.services import HomeRequiredError

        with pytest.raises(HomeRequiredError):
            create_reward(user=UserFactory(), name="치킨", goal_point=500)


class TestClaimReward:
    def test_잔액이_충분하면_수령된다(self):
        home, admin = _home_with_points(complete=3)  # 360P
        reward = RewardFactory(home=home, goal_point=360, created_by=admin)

        claim = claim_reward(user=admin, reward_id=reward.id)

        assert claim.claimed_by == admin
        assert claim.claimed_point == 360
        assert RewardClaim.objects.filter(reward=reward).count() == 1

    def test_잔액이_부족하면_거부된다(self):
        home, admin = _home_with_points(complete=1)  # 120P
        reward = RewardFactory(home=home, goal_point=1000, created_by=admin)

        with pytest.raises(NotEnoughPointsError):
            claim_reward(user=admin, reward_id=reward.id)

    def test_이미_수령된_리워드는_재수령_불가(self):
        home, admin = _home_with_points(complete=3)
        reward = RewardFactory(home=home, goal_point=100, created_by=admin)
        claim_reward(user=admin, reward_id=reward.id)

        with pytest.raises(RewardAlreadyClaimedError):
            claim_reward(user=admin, reward_id=reward.id)

    def test_다른_집_리워드는_404(self):
        _home, admin = _home_with_points()
        outsider_reward = RewardFactory()

        with pytest.raises(RewardNotFoundError):
            claim_reward(user=admin, reward_id=outsider_reward.id)


class TestUpdateDeleteReward:
    def test_수정_성공(self):
        home, admin = _home_with_points()
        reward = RewardFactory(home=home, goal_point=100, created_by=admin)

        updated = update_reward(user=admin, reward_id=reward.id, fields={"goal_point": 300})

        assert updated.goal_point == 300

    def test_수령된_리워드는_수정_불가(self):
        home, admin = _home_with_points(complete=3)
        reward = RewardFactory(home=home, goal_point=100, created_by=admin)
        claim_reward(user=admin, reward_id=reward.id)

        with pytest.raises(RewardAlreadyClaimedError):
            update_reward(user=admin, reward_id=reward.id, fields={"goal_point": 300})

    def test_수령된_리워드는_삭제_불가(self):
        home, admin = _home_with_points(complete=3)
        reward = RewardFactory(home=home, goal_point=100, created_by=admin)
        claim_reward(user=admin, reward_id=reward.id)

        with pytest.raises(RewardAlreadyClaimedError):
            delete_reward(user=admin, reward_id=reward.id)

    def test_미수령_리워드는_삭제된다(self):
        from apps.rewards.models import Reward

        home, admin = _home_with_points()
        reward = RewardFactory(home=home, created_by=admin)

        delete_reward(user=admin, reward_id=reward.id)

        assert not Reward.objects.filter(id=reward.id).exists()


class TestMemberProgress:
    def test_보유_포인트_내림차순으로_순위가_매겨진다(self):
        home, admin = _home_with_points(complete=2)  # admin 240P
        member = UserFactory()
        HomeMemberFactory(home=home, user=member, role=HomeMember.Role.MEMBER)
        reward = RewardFactory(home=home, goal_point=480, created_by=admin)

        rows = get_member_progress(reward=reward)

        assert rows[0]["uid"] == str(admin.uid)
        assert rows[0]["rank"] == 1
        assert rows[0]["point"] == 240
        assert rows[0]["achievement_rate"] == 50
        assert rows[1]["point"] == 0
        assert rows[1]["rank"] == 2

    def test_달성률은_100을_넘지_않는다(self):
        home, admin = _home_with_points(complete=3)  # 360P
        reward = RewardFactory(home=home, goal_point=100, created_by=admin)

        rows = get_member_progress(reward=reward)

        assert rows[0]["achievement_rate"] == 100

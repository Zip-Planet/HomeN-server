import pytest

from apps.homes.models import Home, HomeMember, HomeImageType, Reward
from apps.homes.services import (
    AlreadyHasHomeError,
    HomeNotFoundError,
    HomePermissionError,
    add_rewards,
    add_starter_pack_chores,
    create_home,
    join_home,
)
from apps.homes.tests.factories import (
    ChoreFactory,
    HomeFactory,
    HomeMemberFactory,
    StarterPackFactory,
)
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestCreateHome:
    def test_집_생성_성공(self):
        user = UserFactory()

        home = create_home(user=user, name="우리집", image_id=HomeImageType.TYPE_1)

        assert home.name == "우리집"
        assert home.image == HomeImageType.TYPE_1
        assert home.status == Home.Status.DRAFT
        assert home.creation_step == Home.CreationStep.PROFILE
        assert len(home.invite_code) == 6

    def test_관리자_멤버_자동_생성(self):
        user = UserFactory()

        home = create_home(user=user, name="우리집", image_id=HomeImageType.TYPE_1)

        member = HomeMember.objects.get(home=home, user=user)
        assert member.role == HomeMember.Role.ADMIN

    def test_이미_집이_있으면_실패(self):
        user = UserFactory()
        existing_home = HomeFactory()
        HomeMemberFactory(home=existing_home, user=user)

        with pytest.raises(AlreadyHasHomeError):
            create_home(user=user, name="새집", image_id=HomeImageType.TYPE_1)


class TestAddStarterPackChores:
    def test_집안일_추가_성공(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        pack = StarterPackFactory()
        ChoreFactory(starter_pack=pack)
        ChoreFactory(starter_pack=pack)

        chores = add_starter_pack_chores(home=home, user=user, starter_pack_id=pack.pk)

        assert len(chores) == 2
        assert home.home_chores.count() == 2
        assert home.creation_step == Home.CreationStep.CHORES

    def test_기존_집안일_교체(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        old_pack = StarterPackFactory()
        ChoreFactory(starter_pack=old_pack)
        add_starter_pack_chores(home=home, user=user, starter_pack_id=old_pack.pk)

        new_pack = StarterPackFactory()
        ChoreFactory(starter_pack=new_pack)
        ChoreFactory(starter_pack=new_pack)
        add_starter_pack_chores(home=home, user=user, starter_pack_id=new_pack.pk)

        assert home.home_chores.count() == 2

    def test_관리자가_아니면_실패(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.MEMBER)
        pack = StarterPackFactory()

        with pytest.raises(HomePermissionError):
            add_starter_pack_chores(home=home, user=user, starter_pack_id=pack.pk)


class TestAddRewards:
    def test_리워드_일괄_등록_성공(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)
        rewards_data = [{"name": "치킨", "goal_point": 100}, {"name": "영화", "goal_point": 200}]

        rewards = add_rewards(home=home, user=user, rewards_data=rewards_data)

        assert len(rewards) == 2
        assert Reward.objects.filter(home=home).count() == 2
        assert home.status == Home.Status.ACTIVE
        assert home.creation_step == Home.CreationStep.REWARDS

    def test_관리자가_아니면_실패(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.MEMBER)

        with pytest.raises(HomePermissionError):
            add_rewards(home=home, user=user, rewards_data=[{"name": "치킨", "goal_point": 100}])


class TestJoinHome:
    def test_집_참여_성공(self):
        user = UserFactory()
        home = HomeFactory(status=Home.Status.ACTIVE)

        member = join_home(user=user, invite_code=home.invite_code)

        assert member.role == HomeMember.Role.MEMBER
        assert member.home == home

    def test_이미_집이_있으면_실패(self):
        user = UserFactory()
        existing_home = HomeFactory(status=Home.Status.ACTIVE)
        HomeMemberFactory(home=existing_home, user=user)
        another_home = HomeFactory(status=Home.Status.ACTIVE)

        with pytest.raises(AlreadyHasHomeError):
            join_home(user=user, invite_code=another_home.invite_code)

    def test_잘못된_초대코드_실패(self):
        user = UserFactory()

        with pytest.raises(HomeNotFoundError):
            join_home(user=user, invite_code="XXXXX")

    def test_draft_집_참여_불가(self):
        user = UserFactory()
        home = HomeFactory(status=Home.Status.DRAFT)

        with pytest.raises(HomeNotFoundError):
            join_home(user=user, invite_code=home.invite_code)

import pytest

from apps.homes.models import Home, HomeChore, HomeMember, HomeImageType, Reward
from apps.homes.services import (
    AlreadyHasHomeError,
    HomeError,
    HomeNotFoundError,
    create_home,
    join_home,
)
from apps.homes.tests.factories import ChoreFactory, HomeFactory, HomeMemberFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestCreateHome:
    def test_집_생성_성공(self):
        user = UserFactory()

        home = create_home(user=user, name="우리집", image_id=HomeImageType.TYPE_1, chores=[], rewards=[])

        assert home.name == "우리집"
        assert home.image == HomeImageType.TYPE_1
        assert home.status == Home.Status.ACTIVE
        assert len(home.invite_code) == 6

    def test_관리자_멤버_자동_생성(self):
        user = UserFactory()

        home = create_home(user=user, name="우리집", image_id=HomeImageType.TYPE_1, chores=[], rewards=[])

        member = HomeMember.objects.get(home=home, user=user)
        assert member.role == HomeMember.Role.ADMIN

    def test_집안일_함께_생성(self):
        user = UserFactory()
        chore1 = ChoreFactory()
        chore2 = ChoreFactory()

        home = create_home(
            user=user, name="우리집", image_id=HomeImageType.TYPE_1,
            chores=[chore1.pk, chore2.pk], rewards=[],
        )

        assert HomeChore.objects.filter(home=home).count() == 2

    def test_빈_집안일_리스트_집안일_생성_안함(self):
        user = UserFactory()

        home = create_home(user=user, name="우리집", image_id=HomeImageType.TYPE_1, chores=[], rewards=[])

        assert HomeChore.objects.filter(home=home).count() == 0

    def test_리워드_함께_생성(self):
        user = UserFactory()
        rewards_data = [{"name": "치킨", "goal_point": 100}, {"name": "영화", "goal_point": 200}]

        home = create_home(
            user=user, name="우리집", image_id=HomeImageType.TYPE_1,
            chores=[], rewards=rewards_data,
        )

        assert Reward.objects.filter(home=home).count() == 2

    def test_빈_리워드_리스트_리워드_생성_안함(self):
        user = UserFactory()

        home = create_home(user=user, name="우리집", image_id=HomeImageType.TYPE_1, chores=[], rewards=[])

        assert Reward.objects.filter(home=home).count() == 0

    def test_이미_집이_있으면_실패(self):
        user = UserFactory()
        existing_home = HomeFactory()
        HomeMemberFactory(home=existing_home, user=user)

        with pytest.raises(AlreadyHasHomeError):
            create_home(user=user, name="새집", image_id=HomeImageType.TYPE_1, chores=[], rewards=[])

    def test_존재하지_않는_집안일_ID_실패(self):
        user = UserFactory()

        with pytest.raises(HomeError):
            create_home(user=user, name="우리집", image_id=HomeImageType.TYPE_1, chores=[99999], rewards=[])


class TestJoinHome:
    def test_집_참여_성공(self):
        user = UserFactory()
        home = HomeFactory(status=Home.Status.ACTIVE)

        member = join_home(user=user, invite_code=home.invite_code)

        assert member.role == HomeMember.Role.MEMBER
        assert member.home == home

    def test_소문자_초대코드로_참여_성공(self):
        user = UserFactory()
        home = HomeFactory(status=Home.Status.ACTIVE, invite_code="ABC123")

        member = join_home(user=user, invite_code="abc123")

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

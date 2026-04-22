import pytest

from apps.homes.models import Chore, ChoreCategory, Home, HomeChore, HomeMember, HomeImageType, Reward
from apps.homes.services import (
    AdminCannotLeaveError,
    AlreadyHasHomeError,
    HomeHasMembersError,
    HomeNotFoundError,
    NotHomeAdminError,
    TransferAdminTargetError,
    create_home,
    delete_home,
    join_home,
    leave_home,
    transfer_admin,
)
from apps.homes.tests.factories import HomeFactory, HomeMemberFactory
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
        chores_data = [
            {"category": ChoreCategory.CLEANING, "name": "청소", "description": "방 청소", "repeat_days": [0, 2], "difficulty": Chore.Difficulty.LOW},
            {"category": ChoreCategory.LAUNDRY, "name": "세탁", "description": "", "repeat_days": [], "difficulty": Chore.Difficulty.MEDIUM},
        ]

        home = create_home(
            user=user, name="우리집", image_id=HomeImageType.TYPE_1,
            chores=chores_data, rewards=[],
        )

        assert HomeChore.objects.filter(home=home).count() == 2
        assert Chore.objects.filter(home_chores__home=home).count() == 2

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


class TestDeleteHome:
    def test_관리자_혼자일_때_삭제_성공(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)

        delete_home(user=user)

        assert not Home.objects.filter(pk=home.pk).exists()

    def test_구성원_있으면_삭제_불가(self):
        admin = UserFactory()
        member = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
        HomeMemberFactory(home=home, user=member, role=HomeMember.Role.MEMBER)

        with pytest.raises(HomeHasMembersError):
            delete_home(user=admin)

        assert Home.objects.filter(pk=home.pk).exists()

    def test_구성원은_집_삭제_불가(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.MEMBER)

        with pytest.raises(NotHomeAdminError):
            delete_home(user=user)

    def test_집_없는_유저는_집_삭제_불가(self):
        user = UserFactory()

        with pytest.raises(NotHomeAdminError):
            delete_home(user=user)


class TestLeaveHome:
    def test_구성원은_집_나가기_성공(self):
        user = UserFactory()
        home = HomeFactory()
        member = HomeMemberFactory(home=home, user=user, role=HomeMember.Role.MEMBER)
        member_pk = member.pk

        leave_home(user=user)

        assert not HomeMember.objects.filter(pk=member_pk).exists()
        assert Home.objects.filter(pk=home.pk).exists()

    def test_관리자는_집_나가기_불가(self):
        user = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.ADMIN)

        with pytest.raises(AdminCannotLeaveError):
            leave_home(user=user)

    def test_집_없는_유저는_집_나가기_불가(self):
        user = UserFactory()

        with pytest.raises(HomeNotFoundError):
            leave_home(user=user)


class TestTransferAdmin:
    def test_관리자_양도_성공(self):
        admin = UserFactory()
        member = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
        HomeMemberFactory(home=home, user=member, role=HomeMember.Role.MEMBER)

        transfer_admin(user=admin, target_uid=member.uid)

        assert HomeMember.objects.get(user=admin).role == HomeMember.Role.MEMBER
        assert HomeMember.objects.get(user=member).role == HomeMember.Role.ADMIN

    def test_관리자가_아니면_양도_불가(self):
        member = UserFactory()
        other = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=member, role=HomeMember.Role.MEMBER)
        HomeMemberFactory(home=home, user=other, role=HomeMember.Role.MEMBER)

        with pytest.raises(NotHomeAdminError):
            transfer_admin(user=member, target_uid=other.uid)

    def test_다른_집_구성원에게_양도_불가(self):
        admin = UserFactory()
        outsider = UserFactory()
        home = HomeFactory()
        other_home = HomeFactory()
        HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
        HomeMemberFactory(home=other_home, user=outsider, role=HomeMember.Role.MEMBER)

        with pytest.raises(TransferAdminTargetError):
            transfer_admin(user=admin, target_uid=outsider.uid)

    def test_집에_없는_유저에게_양도_불가(self):
        admin = UserFactory()
        nonmember = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)

        with pytest.raises(TransferAdminTargetError):
            transfer_admin(user=admin, target_uid=nonmember.uid)

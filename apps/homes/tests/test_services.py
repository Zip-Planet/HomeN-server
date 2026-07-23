from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.homes.models import Chore, ChoreCategory, Home, HomeChore, HomeMember, HomeImageType, Reward, WeeklyAssignment
from apps.homes.services import (
    AdminCannotLeaveError,
    AlreadyHasHomeError,
    AssignmentConflictError,
    AssignmentNotFoundError,
    AssignmentStateError,
    HomeHasMembersError,
    HomeNotFoundError,
    NotHomeAdminError,
    TransferAdminTargetError,
    auto_confirm_due_assignments,
    confirm_assignment,
    create_home,
    delete_home,
    delete_home_chore,
    expire_past_assignments,
    generate_assignment,
    generate_weekly_assignments,
    join_home,
    leave_home,
    next_week_start,
    regenerate_assignment,
    transfer_admin,
    update_home_chore,
    week_start_of,
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


class TestChorePoint:
    """난이도 → 포인트 자동 부여 (하40/중하80/중120/중상160/상200)."""

    @pytest.mark.parametrize(
        ("difficulty", "expected_point"),
        [(1, 40), (2, 80), (3, 120), (4, 160), (5, 200)],
    )
    def test_난이도별_포인트_자동_산출(self, difficulty: int, expected_point: int):
        chore = Chore(category=ChoreCategory.TRASH, name="집안일", repeat_days=[0], difficulty=difficulty)

        assert chore.point == expected_point


def _make_home_with_admin():
    admin = UserFactory()
    home = HomeFactory()
    HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
    return home, admin


def _add_chore(home, *, name="집안일", difficulty=Chore.Difficulty.MEDIUM, repeat_days=None, is_active=True):
    from apps.homes.tests.factories import ChoreFactory, HomeChoreFactory

    chore = ChoreFactory(starter_pack=None, name=name, difficulty=difficulty, repeat_days=repeat_days or [0])
    return HomeChoreFactory(home=home, chore=chore, is_active=is_active)


class TestGenerateAssignment:
    def test_생성_성공_스냅샷과_항목(self):
        home, admin = _make_home_with_admin()
        _add_chore(home, name="분리수거", difficulty=Chore.Difficulty.MEDIUM, repeat_days=[0, 2, 4])
        _add_chore(home, name="화장실 청소", difficulty=Chore.Difficulty.MEDIUM_HIGH, repeat_days=[5])
        _add_chore(home, name="설거지", difficulty=Chore.Difficulty.LOW, repeat_days=[1])

        week_start = next_week_start()
        assignment = generate_assignment(user=admin, week_start=week_start)

        assert assignment.status == WeeklyAssignment.Status.PROPOSED
        assert assignment.week_start == week_start
        assert assignment.member_uids_snapshot == [str(admin.uid)]
        assert assignment.chore_fingerprint
        items = list(assignment.items.all())
        assert len(items) == 5  # 3 + 1 + 1 (repeat_days 펼침)
        trash_items = [i for i in items if i.chore_name == "분리수거"]
        assert sorted(i.weekday for i in trash_items) == [0, 2, 4]
        assert all(i.point == 120 for i in trash_items)  # 난이도 중 스냅샷
        assert all(i.assignee == admin for i in items)

    def test_week_start_생략_시_다음주(self):
        home, admin = _make_home_with_admin()
        for i in range(3):
            _add_chore(home, name=f"집안일{i}")

        assignment = generate_assignment(user=admin)

        assert assignment.week_start == next_week_start()

    def test_관리자_아니면_불가(self):
        home, _admin = _make_home_with_admin()
        member = UserFactory()
        HomeMemberFactory(home=home, user=member, role=HomeMember.Role.MEMBER)

        with pytest.raises(NotHomeAdminError):
            generate_assignment(user=member)

    def test_활성_집안일_3개_미만이면_불가(self):
        home, admin = _make_home_with_admin()
        _add_chore(home)
        _add_chore(home)
        _add_chore(home, is_active=False)  # 비활성은 미포함

        with pytest.raises(AssignmentStateError) as exc:
            generate_assignment(user=admin)

        assert exc.value.code == "not_enough_chores"

    def test_비활성_집안일은_배정에서_제외(self):
        home, admin = _make_home_with_admin()
        for i in range(3):
            _add_chore(home, name=f"활성{i}", repeat_days=[0])
        _add_chore(home, name="삭제됨", repeat_days=[0, 1, 2], is_active=False)

        assignment = generate_assignment(user=admin)

        assert assignment.items.count() == 3
        assert not assignment.items.filter(chore_name="삭제됨").exists()

    def test_같은_주차_중복_생성_불가(self):
        home, admin = _make_home_with_admin()
        for i in range(3):
            _add_chore(home, name=f"집안일{i}")
        generate_assignment(user=admin)

        with pytest.raises(AssignmentStateError) as exc:
            generate_assignment(user=admin)

        assert exc.value.code == "assignment_already_exists"

    def test_과거_주차_생성_불가(self):
        home, admin = _make_home_with_admin()
        for i in range(3):
            _add_chore(home, name=f"집안일{i}")
        last_week = week_start_of(timezone.localdate()) - timedelta(days=7)

        with pytest.raises(AssignmentStateError) as exc:
            generate_assignment(user=admin, week_start=last_week)

        assert exc.value.code == "invalid_week_start"

    def test_월요일_아닌_week_start_불가(self):
        home, admin = _make_home_with_admin()
        for i in range(3):
            _add_chore(home, name=f"집안일{i}")

        with pytest.raises(AssignmentStateError) as exc:
            generate_assignment(user=admin, week_start=next_week_start() + timedelta(days=1))

        assert exc.value.code == "invalid_week_start"

    def test_멤버별_포인트_균등_배정(self):
        home, admin = _make_home_with_admin()
        member = UserFactory()
        HomeMemberFactory(home=home, user=member, role=HomeMember.Role.MEMBER)
        # 동일 포인트(중=120) 4건 → 2명에게 2건씩 (총합 240:240)
        for i in range(4):
            _add_chore(home, name=f"집안일{i}", difficulty=Chore.Difficulty.MEDIUM, repeat_days=[i])

        assignment = generate_assignment(user=admin)

        totals: dict[int, int] = {}
        for item in assignment.items.all():
            totals[item.assignee_id] = totals.get(item.assignee_id, 0) + item.point
        assert sorted(totals.values()) == [240, 240]

    def test_동점_시_최근_3주_기여도_낮은_멤버_우선(self):
        from apps.homes.tests.factories import ChoreCompletionFactory

        home, admin = _make_home_with_admin()
        member = UserFactory()
        HomeMemberFactory(home=home, user=member, role=HomeMember.Role.MEMBER)
        chores = [_add_chore(home, name=f"집안일{i}", repeat_days=[0]) for i in range(3)]

        week_start = next_week_start()
        # admin 만 지난주 완료 이력(기여도 120) 보유 → 첫 배정은 기여도 0 인 member 에게
        ChoreCompletionFactory(home_chore=chores[0], completed_by=admin, date=week_start - timedelta(days=7))

        assignment = generate_assignment(user=admin, week_start=week_start)

        items = sorted(assignment.items.all(), key=lambda i: i.id)
        member_count = sum(1 for i in items if i.assignee_id == member.id)
        admin_count = sum(1 for i in items if i.assignee_id == admin.id)
        # 3건(각 120P) → 균등 2:1, 기여도 낮은 member 가 2건
        assert member_count == 2
        assert admin_count == 1


class TestRegenerateAssignment:
    def test_재생성_성공_기존_폐기_및_최신_반영(self):
        home, admin = _make_home_with_admin()
        for i in range(3):
            _add_chore(home, name=f"집안일{i}")
        old = generate_assignment(user=admin)

        _add_chore(home, name="새 집안일", repeat_days=[3])
        new = regenerate_assignment(user=admin, assignment_id=old.id)

        assert not WeeklyAssignment.objects.filter(id=old.id).exists()
        assert new.week_start == old.week_start
        assert new.status == WeeklyAssignment.Status.PROPOSED
        assert new.items.filter(chore_name="새 집안일").exists()

    def test_proposed_아니면_재생성_불가(self):
        home, admin = _make_home_with_admin()
        for i in range(3):
            _add_chore(home, name=f"집안일{i}")
        assignment = generate_assignment(user=admin)
        confirm_assignment(user=admin, assignment_id=assignment.id)

        with pytest.raises(AssignmentStateError) as exc:
            regenerate_assignment(user=admin, assignment_id=assignment.id)

        assert exc.value.code == "not_proposed"

    def test_관리자_아니면_불가(self):
        home, admin = _make_home_with_admin()
        member = UserFactory()
        HomeMemberFactory(home=home, user=member, role=HomeMember.Role.MEMBER)
        for i in range(3):
            _add_chore(home, name=f"집안일{i}")
        assignment = generate_assignment(user=admin)

        with pytest.raises(NotHomeAdminError):
            regenerate_assignment(user=member, assignment_id=assignment.id)

    def test_다른_집_분담안_불가(self):
        home, admin = _make_home_with_admin()
        for i in range(3):
            _add_chore(home, name=f"집안일{i}")
        assignment = generate_assignment(user=admin)

        other_home, other_admin = _make_home_with_admin()

        with pytest.raises(AssignmentNotFoundError):
            regenerate_assignment(user=other_admin, assignment_id=assignment.id)


class TestConfirmAssignment:
    def _setup(self):
        home, admin = _make_home_with_admin()
        home_chores = [_add_chore(home, name=f"집안일{i}") for i in range(3)]
        assignment = generate_assignment(user=admin)
        return home, admin, home_chores, assignment

    def test_확정_성공(self):
        _home, admin, _chores, assignment = self._setup()

        confirmed = confirm_assignment(user=admin, assignment_id=assignment.id)

        assert confirmed.status == WeeklyAssignment.Status.CONFIRMED
        assert confirmed.confirmed_by == admin
        assert confirmed.confirmed_at is not None

    def test_이미_확정된_분담안_재확정_불가(self):
        _home, admin, _chores, assignment = self._setup()
        confirm_assignment(user=admin, assignment_id=assignment.id)

        with pytest.raises(AssignmentStateError) as exc:
            confirm_assignment(user=admin, assignment_id=assignment.id)

        assert exc.value.code == "not_proposed"

    def test_같은_주차_확정본_존재_시_불가(self):
        home, admin, _chores, assignment = self._setup()
        # 직접 ORM 으로 같은 주차 확정본을 만들어 중복 확정을 시뮬레이션
        WeeklyAssignment.objects.create(
            home=home,
            week_start=assignment.week_start,
            status=WeeklyAssignment.Status.CONFIRMED,
            generated_at=timezone.now(),
            member_uids_snapshot=assignment.member_uids_snapshot,
            chore_fingerprint=assignment.chore_fingerprint,
        )

        with pytest.raises(AssignmentStateError) as exc:
            confirm_assignment(user=admin, assignment_id=assignment.id)

        assert exc.value.code == "already_confirmed_week"

    def test_생성_이후_집안일_수정되면_409(self):
        _home, admin, home_chores, assignment = self._setup()
        update_home_chore(user=admin, home_chore_id=home_chores[0].id, fields={"name": "변경됨"})

        with pytest.raises(AssignmentConflictError) as exc:
            confirm_assignment(user=admin, assignment_id=assignment.id)

        assert exc.value.code == "chores_changed"

    def test_생성_이후_집안일_추가되면_409(self):
        home, admin, _chores, assignment = self._setup()
        _add_chore(home, name="신규 집안일")

        with pytest.raises(AssignmentConflictError) as exc:
            confirm_assignment(user=admin, assignment_id=assignment.id)

        assert exc.value.code == "chores_changed"

    def test_생성_이후_구성원_변화_시_409(self):
        home, admin, _chores, assignment = self._setup()
        newcomer = UserFactory()
        HomeMemberFactory(home=home, user=newcomer, role=HomeMember.Role.MEMBER)

        with pytest.raises(AssignmentConflictError) as exc:
            confirm_assignment(user=admin, assignment_id=assignment.id)

        assert exc.value.code == "members_changed"

    def test_활성_집안일_3개_미만이_되면_409(self):
        _home, admin, home_chores, assignment = self._setup()
        # 완료 이력 없는 chore 삭제 → 물리 삭제로 활성 2개
        delete_home_chore(user=admin, home_chore_id=home_chores[0].id)

        with pytest.raises(AssignmentConflictError) as exc:
            confirm_assignment(user=admin, assignment_id=assignment.id)

        assert exc.value.code == "not_enough_chores"

    def test_확정본은_원본_수정에_불변_스냅샷(self):
        _home, admin, home_chores, assignment = self._setup()
        confirmed = confirm_assignment(user=admin, assignment_id=assignment.id)

        update_home_chore(
            user=admin,
            home_chore_id=home_chores[0].id,
            fields={"name": "바뀐 이름", "difficulty": Chore.Difficulty.HIGH},
        )

        item = confirmed.items.order_by("id").first()
        item.refresh_from_db()
        assert item.chore_name == "집안일0"
        assert item.point == 120


class TestAssignmentScheduleBatch:
    def test_자동_생성_대상만_생성_기존_보유_집은_스킵(self):
        eligible_home, _ = _make_home_with_admin()
        for i in range(3):
            _add_chore(eligible_home, name=f"집안일{i}")

        manual_home, manual_admin = _make_home_with_admin()
        for i in range(3):
            _add_chore(manual_home, name=f"수동집안일{i}")
        generate_assignment(user=manual_admin)  # 관리자 수동 생성 → 자동 생성 스킵 대상

        lacking_home, _ = _make_home_with_admin()
        _add_chore(lacking_home, name="집안일 하나뿐")

        created, skipped = generate_weekly_assignments()

        assert created == 1
        assert skipped == 2
        assert WeeklyAssignment.objects.filter(
            home=eligible_home, week_start=next_week_start(), status=WeeklyAssignment.Status.PROPOSED
        ).exists()
        assert not WeeklyAssignment.objects.filter(home=lacking_home).exists()

    def test_자동_생성_멱등(self):
        home, _ = _make_home_with_admin()
        for i in range(3):
            _add_chore(home, name=f"집안일{i}")

        first = generate_weekly_assignments()
        second = generate_weekly_assignments()

        assert first == (1, 0)
        assert second == (0, 1)
        assert WeeklyAssignment.objects.filter(home=home).count() == 1

    def test_자동_확정_조건_만족_시_confirmed_by_없이_확정(self):
        home, admin = _make_home_with_admin()
        for i in range(3):
            _add_chore(home, name=f"집안일{i}")
        current_week = week_start_of(timezone.localdate())
        assignment = generate_assignment(user=admin, week_start=current_week)

        confirmed, skipped = auto_confirm_due_assignments()

        assert (confirmed, skipped) == (1, 0)
        assignment.refresh_from_db()
        assert assignment.status == WeeklyAssignment.Status.CONFIRMED
        assert assignment.confirmed_by is None
        assert assignment.confirmed_at is not None

    def test_자동_확정_조건_불만족_시_proposed_유지(self):
        home, admin = _make_home_with_admin()
        for i in range(3):
            _add_chore(home, name=f"집안일{i}")
        current_week = week_start_of(timezone.localdate())
        assignment = generate_assignment(user=admin, week_start=current_week)
        _add_chore(home, name="확정_직전_추가됨")  # 지문 불일치 유발

        confirmed, skipped = auto_confirm_due_assignments()

        assert (confirmed, skipped) == (0, 1)
        assignment.refresh_from_db()
        assert assignment.status == WeeklyAssignment.Status.PROPOSED

    def test_다음_주차_proposed_는_자동_확정_대상_아님(self):
        home, admin = _make_home_with_admin()
        for i in range(3):
            _add_chore(home, name=f"집안일{i}")
        assignment = generate_assignment(user=admin)  # 다음 주차

        confirmed, skipped = auto_confirm_due_assignments()

        assert (confirmed, skipped) == (0, 0)
        assignment.refresh_from_db()
        assert assignment.status == WeeklyAssignment.Status.PROPOSED

    def test_지난_주차_confirmed_만료_전환(self):
        home, _admin = _make_home_with_admin()
        current_week = week_start_of(timezone.localdate())
        past = WeeklyAssignment.objects.create(
            home=home,
            week_start=current_week - timedelta(days=7),
            status=WeeklyAssignment.Status.CONFIRMED,
            generated_at=timezone.now(),
            member_uids_snapshot=[],
            chore_fingerprint="f",
        )
        current = WeeklyAssignment.objects.create(
            home=home,
            week_start=current_week,
            status=WeeklyAssignment.Status.CONFIRMED,
            generated_at=timezone.now(),
            member_uids_snapshot=[],
            chore_fingerprint="f",
        )

        expired_count = expire_past_assignments()

        assert expired_count == 1
        past.refresh_from_db()
        current.refresh_from_db()
        assert past.status == WeeklyAssignment.Status.EXPIRED
        assert current.status == WeeklyAssignment.Status.CONFIRMED

    def test_generate_assignments_커맨드(self):
        home, _ = _make_home_with_admin()
        for i in range(3):
            _add_chore(home, name=f"집안일{i}")

        out = StringIO()
        call_command("generate_assignments", stdout=out)

        assert "생성 1건" in out.getvalue()
        assert WeeklyAssignment.objects.filter(home=home, week_start=next_week_start()).exists()

    def test_finalize_assignments_커맨드(self):
        home, admin = _make_home_with_admin()
        for i in range(3):
            _add_chore(home, name=f"집안일{i}")
        current_week = week_start_of(timezone.localdate())
        generate_assignment(user=admin, week_start=current_week)

        out = StringIO()
        call_command("finalize_assignments", stdout=out)

        assert "자동 확정 1건" in out.getvalue()
        assert WeeklyAssignment.objects.filter(
            home=home, week_start=current_week, status=WeeklyAssignment.Status.CONFIRMED, confirmed_by=None
        ).exists()


# ── 집안일 완료 처리 ─────────────────────────────────────────────────────────


def _confirm_this_week(home, admin, *, today=None):
    """이번 주차 분담안을 만들고 확정 상태로 만들어 반환합니다."""
    from apps.homes.services import _mark_confirmed, _generate_assignment_for_home

    today = today or timezone.localdate()
    assignment = _generate_assignment_for_home(home=home, week_start=week_start_of(today))
    return _mark_confirmed(assignment, confirmed_by=admin)


class TestCompleteChore:
    def test_담당자가_완료하면_이력이_생기고_포인트가_실린다(self):
        from apps.homes.services import complete_chore

        home, admin = _make_home_with_admin()
        today = timezone.localdate()
        _add_chore(home, name="분리수거", difficulty=Chore.Difficulty.MEDIUM, repeat_days=[today.weekday()])
        _add_chore(home, name="설거지", repeat_days=[today.weekday()])
        _add_chore(home, name="빨래", repeat_days=[today.weekday()])
        assignment = _confirm_this_week(home, admin, today=today)
        item = assignment.items.filter(chore_name="분리수거").first()

        completion = complete_chore(user=admin, home_chore_id=item.home_chore_id)

        assert completion.date == today
        assert completion.completed_by == admin
        assert completion.earned_point == 120

    def test_중복_완료는_차단된다(self):
        from apps.homes.services import ChoreAlreadyCompletedError, complete_chore

        home, admin = _make_home_with_admin()
        today = timezone.localdate()
        for name in ("분리수거", "설거지", "빨래"):
            _add_chore(home, name=name, repeat_days=[today.weekday()])
        assignment = _confirm_this_week(home, admin, today=today)
        item = assignment.items.first()

        complete_chore(user=admin, home_chore_id=item.home_chore_id)

        with pytest.raises(ChoreAlreadyCompletedError):
            complete_chore(user=admin, home_chore_id=item.home_chore_id)

    def test_담당자가_아니면_거부된다(self):
        from apps.homes.services import NotChoreAssigneeError, complete_chore

        home, admin = _make_home_with_admin()
        other = UserFactory()
        HomeMemberFactory(home=home, user=other, role=HomeMember.Role.MEMBER)
        today = timezone.localdate()
        for name in ("분리수거", "설거지", "빨래"):
            _add_chore(home, name=name, repeat_days=[today.weekday()])
        assignment = _confirm_this_week(home, admin, today=today)
        item = assignment.items.exclude(assignee=other).first()

        with pytest.raises(NotChoreAssigneeError):
            complete_chore(user=other, home_chore_id=item.home_chore_id)

    def test_확정_분담안이_없으면_완료할_수_없다(self):
        from apps.homes.services import ChoreCompletionError, complete_chore

        home, admin = _make_home_with_admin()
        today = timezone.localdate()
        home_chore = _add_chore(home, name="분리수거", repeat_days=[today.weekday()])

        with pytest.raises(ChoreCompletionError) as exc:
            complete_chore(user=admin, home_chore_id=home_chore.id)

        assert exc.value.code == "assignment_not_confirmed"

    def test_배정되지_않은_요일은_완료할_수_없다(self):
        from apps.homes.services import ChoreCompletionError, complete_chore

        home, admin = _make_home_with_admin()
        today = timezone.localdate()
        other_weekday = (today.weekday() + 1) % 7
        target = _add_chore(home, name="분리수거", repeat_days=[other_weekday])
        _add_chore(home, name="설거지", repeat_days=[today.weekday()])
        _add_chore(home, name="빨래", repeat_days=[today.weekday()])
        _confirm_this_week(home, admin, today=today)

        with pytest.raises(ChoreCompletionError) as exc:
            complete_chore(user=admin, home_chore_id=target.id)

        assert exc.value.code == "not_assigned_on_date"


class TestUncompleteChore:
    def test_완료자_본인은_취소할_수_있다(self):
        from apps.homes.models import ChoreCompletion
        from apps.homes.services import complete_chore, uncomplete_chore

        home, admin = _make_home_with_admin()
        today = timezone.localdate()
        for name in ("분리수거", "설거지", "빨래"):
            _add_chore(home, name=name, repeat_days=[today.weekday()])
        assignment = _confirm_this_week(home, admin, today=today)
        item = assignment.items.first()
        complete_chore(user=admin, home_chore_id=item.home_chore_id)

        uncomplete_chore(user=admin, home_chore_id=item.home_chore_id, target_date=today)

        assert not ChoreCompletion.objects.filter(home_chore_id=item.home_chore_id, date=today).exists()

    def test_완료자가_아니면_취소할_수_없다(self):
        from apps.homes.services import NotChoreAssigneeError, complete_chore, uncomplete_chore

        home, admin = _make_home_with_admin()
        other = UserFactory()
        HomeMemberFactory(home=home, user=other, role=HomeMember.Role.MEMBER)
        today = timezone.localdate()
        for name in ("분리수거", "설거지", "빨래"):
            _add_chore(home, name=name, repeat_days=[today.weekday()])
        assignment = _confirm_this_week(home, admin, today=today)
        item = assignment.items.filter(assignee=admin).first()
        complete_chore(user=admin, home_chore_id=item.home_chore_id)

        with pytest.raises(NotChoreAssigneeError):
            uncomplete_chore(user=other, home_chore_id=item.home_chore_id, target_date=today)

    def test_이력이_없으면_404_에러(self):
        from apps.homes.services import ChoreCompletionNotFoundError, uncomplete_chore

        home, admin = _make_home_with_admin()
        today = timezone.localdate()
        home_chore = _add_chore(home, name="분리수거", repeat_days=[today.weekday()])

        with pytest.raises(ChoreCompletionNotFoundError):
            uncomplete_chore(user=admin, home_chore_id=home_chore.id, target_date=today)


class TestHomeDashboard:
    def test_진행률_기여도_MVP_집계(self):
        from apps.homes.selectors import get_home_dashboard
        from apps.homes.services import complete_chore

        home, admin = _make_home_with_admin()
        today = timezone.localdate()
        for name in ("분리수거", "설거지", "빨래"):
            _add_chore(home, name=name, difficulty=Chore.Difficulty.MEDIUM, repeat_days=[today.weekday()])
        assignment = _confirm_this_week(home, admin, today=today)
        item = assignment.items.first()
        complete_chore(user=admin, home_chore_id=item.home_chore_id)

        dashboard = get_home_dashboard(user=admin, today=today)

        assert dashboard["this_week"]["total_count"] == 3
        assert dashboard["this_week"]["completed_count"] == 1
        assert dashboard["this_week"]["progress_rate"] == 33
        # 완료 포인트 전부가 admin 것이므로 기여도 100%
        assert dashboard["this_week"]["my_contribution_rate"] == 100
        assert dashboard["this_week"]["mvp"]["name"] == admin.name
        assert dashboard["this_week"]["mvp"]["point"] == 120
        assert dashboard["next_week"]["status"] is None

    def test_분담안이_없으면_0값_요약(self):
        from apps.homes.selectors import get_home_dashboard

        home, admin = _make_home_with_admin()

        dashboard = get_home_dashboard(user=admin)

        assert dashboard["this_week"]["total_count"] == 0
        assert dashboard["this_week"]["progress_rate"] == 0
        assert dashboard["this_week"]["mvp"] is None
        assert dashboard["home"]["member_count"] == 1

    def test_집이_없으면_None(self):
        from apps.homes.selectors import get_home_dashboard

        assert get_home_dashboard(user=UserFactory()) is None


class TestWeeklyProgressAssignee:
    def test_배정된_요일에는_담당자가_실린다(self):
        from apps.homes.selectors import get_weekly_progress
        from apps.homes.services import complete_chore

        home, admin = _make_home_with_admin()
        today = timezone.localdate()
        for name in ("분리수거", "설거지", "빨래"):
            _add_chore(home, name=name, repeat_days=[today.weekday()])
        assignment = _confirm_this_week(home, admin, today=today)
        item = assignment.items.first()
        complete_chore(user=admin, home_chore_id=item.home_chore_id)

        progress = get_weekly_progress(item.home_chore, today=today)
        entry = next(p for p in progress if p["weekday"] == today.weekday())

        assert entry["status"] == "completed"
        assert entry["assignee"]["uid"] == str(admin.uid)
        assert entry["completed_by"]["uid"] == str(admin.uid)

    def test_분담안이_없으면_담당자는_null_이고_repeat_days_로_판단(self):
        from apps.homes.selectors import get_weekly_progress

        home, _admin = _make_home_with_admin()
        home_chore = _add_chore(home, name="분리수거", repeat_days=[0])

        progress = get_weekly_progress(home_chore, today=week_start_of(timezone.localdate()))

        assert progress[0]["status"] == "incomplete"
        assert progress[0]["assignee"] is None
        assert progress[1]["status"] == "not_scheduled"


class TestAssignmentChanges:
    def test_생성_후_추가된_집안일은_new_entries(self):
        from apps.homes.selectors import get_assignment_changes

        home, admin = _make_home_with_admin()
        for name in ("분리수거", "설거지", "빨래"):
            _add_chore(home, name=name, repeat_days=[0])
        assignment = generate_assignment(user=admin)
        _add_chore(home, name="화장실 청소", repeat_days=[5])

        changes = get_assignment_changes(assignment)

        assert changes["has_changes"] is True
        assert [e["chore_name"] for e in changes["new_entries"]] == ["화장실 청소"]
        assert changes["new_entries"][0]["weekday"] == 5
        assert changes["updated_item_ids"] == []

    def test_수정된_집안일은_updated_item_ids(self):
        from apps.homes.selectors import get_assignment_changes

        home, admin = _make_home_with_admin()
        target = _add_chore(home, name="분리수거", difficulty=Chore.Difficulty.MEDIUM, repeat_days=[0])
        _add_chore(home, name="설거지", repeat_days=[0])
        _add_chore(home, name="빨래", repeat_days=[0])
        assignment = generate_assignment(user=admin)
        update_home_chore(user=admin, home_chore_id=target.id, fields={"difficulty": Chore.Difficulty.HIGH})

        changes = get_assignment_changes(assignment)

        assert changes["has_changes"] is True
        assert len(changes["updated_item_ids"]) == 1
        item = assignment.items.get(id=changes["updated_item_ids"][0])
        assert item.chore_name == "분리수거"

    def test_삭제된_집안일은_removed_item_ids(self):
        from apps.homes.selectors import get_assignment_changes

        home, admin = _make_home_with_admin()
        target = _add_chore(home, name="분리수거", repeat_days=[0])
        _add_chore(home, name="설거지", repeat_days=[0])
        _add_chore(home, name="빨래", repeat_days=[0])
        assignment = generate_assignment(user=admin)
        target.is_active = False
        target.save(update_fields=["is_active"])

        changes = get_assignment_changes(assignment)

        assert len(changes["removed_item_ids"]) == 1
        assert changes["has_changes"] is True

    def test_변경이_없으면_has_changes_false(self):
        from apps.homes.selectors import get_assignment_changes

        home, admin = _make_home_with_admin()
        for name in ("분리수거", "설거지", "빨래"):
            _add_chore(home, name=name, repeat_days=[0])
        assignment = generate_assignment(user=admin)

        changes = get_assignment_changes(assignment)

        assert changes["has_changes"] is False
        assert changes["new_entries"] == []

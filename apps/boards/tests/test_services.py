from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.boards.models import HelpRequest, RequestStatus
from apps.boards.services import (
    BoardConflictError,
    BoardPermissionError,
    BoardStateError,
    accept_help_request,
    accept_swap_request,
    cancel_help_request,
    create_help_request,
    create_swap_request,
    expire_board_requests,
    expires_at,
    reject_swap_request,
)
from apps.homes.models import Chore, HomeMember
from apps.homes.services import (
    _generate_assignment_for_home,
    _mark_confirmed,
    complete_chore,
    week_start_of,
)
from apps.homes.tests.factories import ChoreFactory, HomeChoreFactory, HomeFactory, HomeMemberFactory
from apps.notifications.models import Notification, NotificationCategory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _confirmed_home_two_members():
    """관리자 + 구성원 1명, 확정 분담안(각자 최소 1개씩 배정)을 만든다."""
    admin = UserFactory()
    member = UserFactory()
    home = HomeFactory()
    HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
    HomeMemberFactory(home=home, user=member, role=HomeMember.Role.MEMBER)

    today = timezone.localdate()
    for i in range(4):
        chore = ChoreFactory(
            starter_pack=None,
            name=f"집안일{i}",
            difficulty=Chore.Difficulty.MEDIUM,
            repeat_days=[today.weekday()],
        )
        HomeChoreFactory(home=home, chore=chore)

    assignment = _generate_assignment_for_home(home=home, week_start=week_start_of(today))
    assignment = _mark_confirmed(assignment, confirmed_by=admin)
    return home, admin, member, assignment


def _item_of(assignment, user):
    return assignment.items.filter(assignee=user).first()


class TestHelpRequest:
    def test_본인_항목이면_요청_생성(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        item = _item_of(assignment, admin)

        help_request = create_help_request(user=admin, item_id=item.id, message="대신해줄 사람?")

        assert help_request.status == RequestStatus.PENDING
        assert help_request.requester == admin
        # 본인을 제외한 구성원에게 보드 알림이 간다
        # (분담안 생성/확정 알림도 함께 쌓이므로 카테고리로 좁혀 확인한다).
        board_notifications = Notification.objects.filter(category=NotificationCategory.BOARD)
        assert board_notifications.filter(recipient=member).count() == 1
        assert not board_notifications.filter(recipient=admin).exists()

    def test_남의_항목이면_403(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        item = _item_of(assignment, admin)

        with pytest.raises(BoardPermissionError):
            create_help_request(user=member, item_id=item.id)

    def test_중복_요청은_409(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        item = _item_of(assignment, admin)
        create_help_request(user=admin, item_id=item.id)

        with pytest.raises(BoardConflictError):
            create_help_request(user=admin, item_id=item.id)

    def test_이미_완료된_항목은_조율_불가(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        item = _item_of(assignment, admin)
        complete_chore(user=admin, home_chore_id=item.home_chore_id)

        with pytest.raises(BoardStateError) as exc:
            create_help_request(user=admin, item_id=item.id)

        assert exc.value.code == "already_completed"

    def test_제안됨_분담안_항목은_조율_불가(self):
        admin = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
        today = timezone.localdate()
        for i in range(3):
            HomeChoreFactory(
                home=home,
                chore=ChoreFactory(starter_pack=None, name=f"c{i}", repeat_days=[today.weekday()]),
            )
        assignment = _generate_assignment_for_home(home=home, week_start=week_start_of(today))

        with pytest.raises(BoardStateError) as exc:
            create_help_request(user=admin, item_id=assignment.items.first().id)

        assert exc.value.code == "assignment_not_confirmed"

    def test_수락하면_담당자가_바뀐다(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        item = _item_of(assignment, admin)
        help_request = create_help_request(user=admin, item_id=item.id)

        accept_help_request(user=member, help_request_id=help_request.id)

        item.refresh_from_db()
        help_request.refresh_from_db()
        assert item.assignee == member
        assert help_request.status == RequestStatus.ACCEPTED
        assert help_request.accepted_by == member

    def test_본인_요청은_스스로_수락_불가(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        item = _item_of(assignment, admin)
        help_request = create_help_request(user=admin, item_id=item.id)

        with pytest.raises(BoardPermissionError):
            accept_help_request(user=admin, help_request_id=help_request.id)

    def test_이미_수락된_요청은_409(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        item = _item_of(assignment, admin)
        help_request = create_help_request(user=admin, item_id=item.id)
        accept_help_request(user=member, help_request_id=help_request.id)

        with pytest.raises(BoardConflictError):
            accept_help_request(user=member, help_request_id=help_request.id)

    def test_본인_카드만_취소_가능(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        item = _item_of(assignment, admin)
        help_request = create_help_request(user=admin, item_id=item.id)

        with pytest.raises(BoardPermissionError):
            cancel_help_request(user=member, help_request_id=help_request.id)

        cancel_help_request(user=admin, help_request_id=help_request.id)
        assert not HelpRequest.objects.filter(id=help_request.id).exists()


class TestSwapRequest:
    def test_교환_생성과_수락_시_담당자_맞바꿈(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        mine = _item_of(assignment, admin)
        theirs = _item_of(assignment, member)

        swap = create_swap_request(
            user=admin, requester_item_id=mine.id, target_item_id=theirs.id, message="바꿔줄래?"
        )
        accept_swap_request(user=member, swap_id=swap.id)

        mine.refresh_from_db()
        theirs.refresh_from_db()
        swap.refresh_from_db()
        assert mine.assignee == member
        assert theirs.assignee == admin
        assert swap.status == RequestStatus.ACCEPTED

    def test_거절하면_담당자는_그대로(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        mine = _item_of(assignment, admin)
        theirs = _item_of(assignment, member)
        swap = create_swap_request(user=admin, requester_item_id=mine.id, target_item_id=theirs.id)

        reject_swap_request(user=member, swap_id=swap.id)

        mine.refresh_from_db()
        theirs.refresh_from_db()
        swap.refresh_from_db()
        assert mine.assignee == admin
        assert theirs.assignee == member
        assert swap.status == RequestStatus.REJECTED

    def test_요청_받은_담당자만_응답_가능(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        mine = _item_of(assignment, admin)
        theirs = _item_of(assignment, member)
        swap = create_swap_request(user=admin, requester_item_id=mine.id, target_item_id=theirs.id)
        outsider = UserFactory()
        HomeMemberFactory(home=home, user=outsider, role=HomeMember.Role.MEMBER)

        with pytest.raises(BoardPermissionError):
            accept_swap_request(user=outsider, swap_id=swap.id)

    def test_같은_항목끼리는_교환_불가(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        mine = _item_of(assignment, admin)

        with pytest.raises(BoardStateError) as exc:
            create_swap_request(user=admin, requester_item_id=mine.id, target_item_id=mine.id)

        assert exc.value.code == "same_item"

    def test_본인_항목끼리는_교환_불가(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        mine = list(assignment.items.filter(assignee=admin))
        if len(mine) < 2:
            pytest.skip("관리자에게 배정된 항목이 2개 미만")

        with pytest.raises(BoardPermissionError):
            create_swap_request(user=admin, requester_item_id=mine[0].id, target_item_id=mine[1].id)


class TestExpiry:
    def test_기한은_대상_집안일_다음날_2359(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        item = _item_of(assignment, admin)
        target_date = assignment.week_start + timedelta(days=item.weekday)

        deadline = expires_at(item)

        assert deadline.date() == target_date + timedelta(days=1)
        assert (deadline.hour, deadline.minute) == (23, 59)

    def test_기한이_지나면_만료된다(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        item = _item_of(assignment, admin)
        help_request = create_help_request(user=admin, item_id=item.id)

        helps, _swaps = expire_board_requests(now=expires_at(item) + timedelta(minutes=1))

        help_request.refresh_from_db()
        assert helps == 1
        assert help_request.status == RequestStatus.EXPIRED

    def test_기한_전에는_만료되지_않는다(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        item = _item_of(assignment, admin)
        help_request = create_help_request(user=admin, item_id=item.id)

        helps, _swaps = expire_board_requests(now=expires_at(item) - timedelta(minutes=1))

        help_request.refresh_from_db()
        assert helps == 0
        assert help_request.status == RequestStatus.PENDING

    def test_교환은_더_이른_항목_기준으로_만료(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        mine = _item_of(assignment, admin)
        theirs = _item_of(assignment, member)
        swap = create_swap_request(user=admin, requester_item_id=mine.id, target_item_id=theirs.id)
        earliest = min(expires_at(mine), expires_at(theirs))

        _helps, swaps = expire_board_requests(now=earliest + timedelta(minutes=1))

        swap.refresh_from_db()
        assert swaps == 1
        assert swap.status == RequestStatus.EXPIRED

    def test_management_command_실행(self):
        out = StringIO()

        call_command("expire_board_requests", stdout=out)

        assert "조율 카드 만료 완료" in out.getvalue()

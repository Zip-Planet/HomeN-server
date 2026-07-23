"""집안 보드 쓰기 오케스트레이션.

핵심 정책 (Figma T2_FairBoard / Q1 / Q2):
- 도움·교환 카드는 **확정된 분담안 항목**에 대해서만 만들 수 있다.
- 도움 요청은 본인 담당 항목만, 교환은 본인 항목 ↔ 남의 항목으로 건다.
- 수락은 담당자를 실제로 바꾼다 (교환은 맞바꿈).
- 만료 기준: 대상 집안일 날짜의 **다음 날 23:59** 까지 응답이 없으면 만료.
- 이미 완료된 항목은 조율 대상이 아니다.
"""

from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from apps.boards.models import BotCard, HelpRequest, RequestStatus, SwapRequest
from apps.homes.models import AssignmentItem, ChoreCompletion, Home, HomeMember, WeeklyAssignment
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify, notify_home
from apps.users.models import User


class BoardError(Exception):
    """보드 관련 오류의 공통 부모. `code` 는 API 에러 코드로 노출된다."""

    code = "board_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class BoardNotFoundError(BoardError):
    """대상(집/항목/카드)을 찾을 수 없을 때 발생합니다 (404)."""

    code = "not_found"


class BoardPermissionError(BoardError):
    """권한이 없는 유저가 카드를 만들거나 취소·응답할 때 발생합니다 (403)."""

    code = "permission_denied"


class BoardStateError(BoardError):
    """상태상 허용되지 않는 요청일 때 발생합니다 (400)."""

    code = "invalid_state"


class BoardConflictError(BoardError):
    """이미 처리·중복된 요청일 때 발생합니다 (409)."""

    code = "conflict"


def item_date(item: AssignmentItem) -> date:
    """분담안 항목의 실행 날짜 (week_start + weekday)."""
    return item.assignment.week_start + timedelta(days=item.weekday)


def expires_at(item: AssignmentItem) -> datetime:
    """조율 카드 만료 시각 — 대상 집안일 **다음 날 23:59**."""
    deadline_date = item_date(item) + timedelta(days=1)
    naive = datetime.combine(deadline_date, time(23, 59))
    return timezone.make_aware(naive, timezone.get_current_timezone())


def _get_home(user: User) -> Home:
    membership = HomeMember.objects.select_related("home").filter(user=user).first()
    if membership is None:
        raise BoardNotFoundError("속한 집이 없습니다.")
    return membership.home


def _get_confirmed_item(*, home: Home, item_id: int) -> AssignmentItem:
    item = (
        AssignmentItem.objects.select_related("assignment", "assignee")
        .filter(id=item_id, assignment__home=home)
        .first()
    )
    if item is None:
        raise BoardNotFoundError("분담안 항목을 찾을 수 없습니다.")
    if item.assignment.status != WeeklyAssignment.Status.CONFIRMED:
        raise BoardStateError(
            "확정된 분담안의 집안일만 조율할 수 있습니다.", code="assignment_not_confirmed"
        )
    if ChoreCompletion.objects.filter(home_chore_id=item.home_chore_id, date=item_date(item)).exists():
        raise BoardStateError("이미 완료된 집안일은 조율할 수 없습니다.", code="already_completed")
    return item


# ──────────────────────────────────────────
# 도움 요청
# ──────────────────────────────────────────


def create_help_request(*, user: User, item_id: int, message: str = "") -> HelpRequest:
    """도움 요청 카드를 만듭니다 (본인 담당 항목만).

    Raises:
        BoardNotFoundError: 본인 집의 항목이 아닌 경우.
        BoardStateError: 미확정 분담안이거나 이미 완료된 항목인 경우.
        BoardPermissionError: 본인 담당 항목이 아닌 경우.
        BoardConflictError: 같은 항목에 대기 중인 요청이 이미 있는 경우.
    """
    home = _get_home(user)
    item = _get_confirmed_item(home=home, item_id=item_id)

    if item.assignee_id != user.id:
        raise BoardPermissionError("본인이 담당한 집안일만 도움을 요청할 수 있습니다.")
    if HelpRequest.objects.filter(item=item, status=RequestStatus.PENDING).exists():
        raise BoardConflictError("이미 도움 요청한 집안일이에요.", code="already_requested")

    help_request = HelpRequest.objects.create(
        home=home, item=item, requester=user, message=message
    )
    notify_home(
        home=home,
        category=NotificationCategory.BOARD,
        title=f"도움이 필요해요 ({user.name})",
        body=message or f"{item.chore_name} 을(를) 대신해 줄 사람을 찾고 있어요.",
        deep_link=f"board:help:{help_request.id}",
        exclude=user,
    )
    return help_request


def accept_help_request(*, user: User, help_request_id: int) -> HelpRequest:
    """도움 요청을 수락합니다 — 대상 항목의 담당자가 수락자로 바뀝니다.

    Raises:
        BoardNotFoundError: 본인 집의 요청이 아닌 경우.
        BoardConflictError: 이미 처리된 요청인 경우.
        BoardPermissionError: 본인이 만든 요청을 스스로 수락하려는 경우.
    """
    home = _get_home(user)
    help_request = (
        HelpRequest.objects.select_related("item__assignment", "requester")
        .filter(id=help_request_id, home=home)
        .first()
    )
    if help_request is None:
        raise BoardNotFoundError("도움 요청을 찾을 수 없습니다.")
    if help_request.status != RequestStatus.PENDING:
        raise BoardConflictError("이미 처리된 도움 요청이에요.", code="already_resolved")
    if help_request.requester_id == user.id:
        raise BoardPermissionError("본인이 올린 도움 요청은 수락할 수 없습니다.")

    with transaction.atomic():
        item = help_request.item
        item.assignee = user
        item.save(update_fields=["assignee"])

        help_request.status = RequestStatus.ACCEPTED
        help_request.accepted_by = user
        help_request.resolved_at = timezone.now()
        help_request.save(update_fields=["status", "accepted_by", "resolved_at"])

    notify(
        home=home,
        recipients=[help_request.requester],
        category=NotificationCategory.BOARD,
        title="도움 요청이 수락됐어요",
        body=f"{user.name}님이 도와주기로 했어요.",
        deep_link=f"board:help:{help_request.id}",
    )
    return help_request


def cancel_help_request(*, user: User, help_request_id: int) -> None:
    """본인이 만든 대기 중 도움 요청을 취소(삭제)합니다."""
    home = _get_home(user)
    help_request = HelpRequest.objects.filter(id=help_request_id, home=home).first()
    if help_request is None:
        raise BoardNotFoundError("도움 요청을 찾을 수 없습니다.")
    if help_request.requester_id != user.id:
        raise BoardPermissionError("본인이 올린 카드만 취소할 수 있습니다.")
    if help_request.status != RequestStatus.PENDING:
        raise BoardConflictError("이미 처리된 도움 요청이에요.", code="already_resolved")

    help_request.delete()


# ──────────────────────────────────────────
# 교환 요청
# ──────────────────────────────────────────


def create_swap_request(
    *, user: User, requester_item_id: int, target_item_id: int, message: str = ""
) -> SwapRequest:
    """교환 요청 카드를 만듭니다 (내 항목 ↔ 남의 항목).

    Raises:
        BoardNotFoundError: 본인 집의 항목이 아닌 경우.
        BoardStateError: 미확정/완료 항목이거나 같은 항목을 지정한 경우.
        BoardPermissionError: 내 항목이 아니거나 상대 항목이 본인 것인 경우.
        BoardConflictError: 같은 항목에 대기 중인 교환 요청이 있는 경우.
    """
    home = _get_home(user)
    if requester_item_id == target_item_id:
        raise BoardStateError("같은 집안일끼리는 교환할 수 없습니다.", code="same_item")

    requester_item = _get_confirmed_item(home=home, item_id=requester_item_id)
    target_item = _get_confirmed_item(home=home, item_id=target_item_id)

    if requester_item.assignee_id != user.id:
        raise BoardPermissionError("본인이 담당한 집안일만 교환에 내놓을 수 있습니다.")
    if target_item.assignee_id == user.id:
        raise BoardPermissionError("본인 집안일끼리는 교환할 수 없습니다.")
    if target_item.assignee_id is None:
        raise BoardStateError("담당자가 없는 집안일과는 교환할 수 없습니다.", code="no_assignee")
    if SwapRequest.objects.filter(requester_item=requester_item, status=RequestStatus.PENDING).exists():
        raise BoardConflictError("이미 교환 요청한 집안일이에요.", code="already_requested")

    swap = SwapRequest.objects.create(
        home=home,
        requester_item=requester_item,
        target_item=target_item,
        requester=user,
        message=message,
    )
    notify(
        home=home,
        recipients=[target_item.assignee],
        category=NotificationCategory.BOARD,
        title="교환 요청이 도착했어요",
        body=message or f"{user.name}님이 집안일 교환을 요청했어요.",
        deep_link=f"board:swap:{swap.id}",
    )
    return swap


def _get_pending_swap(*, user: User, swap_id: int) -> SwapRequest:
    home = _get_home(user)
    swap = (
        SwapRequest.objects.select_related(
            "requester_item__assignment", "target_item__assignment", "requester"
        )
        .filter(id=swap_id, home=home)
        .first()
    )
    if swap is None:
        raise BoardNotFoundError("교환 요청을 찾을 수 없습니다.")
    if swap.status != RequestStatus.PENDING:
        raise BoardConflictError("이미 처리된 교환 요청이에요.", code="already_resolved")
    return swap


def accept_swap_request(*, user: User, swap_id: int) -> SwapRequest:
    """교환 요청을 수락합니다 — 두 항목의 담당자를 맞바꿉니다.

    교환 요청을 받은 당사자(상대 항목 담당자)만 응답할 수 있다.
    """
    swap = _get_pending_swap(user=user, swap_id=swap_id)
    if swap.target_item.assignee_id != user.id:
        raise BoardPermissionError("교환 요청을 받은 담당자만 응답할 수 있습니다.")

    with transaction.atomic():
        requester_item = swap.requester_item
        target_item = swap.target_item
        requester_item.assignee, target_item.assignee = target_item.assignee, requester_item.assignee
        requester_item.save(update_fields=["assignee"])
        target_item.save(update_fields=["assignee"])

        swap.status = RequestStatus.ACCEPTED
        swap.responded_by = user
        swap.resolved_at = timezone.now()
        swap.save(update_fields=["status", "responded_by", "resolved_at"])

    notify(
        home=swap.home,
        recipients=[swap.requester],
        category=NotificationCategory.BOARD,
        title="교환 요청이 수락됐어요",
        body=f"{user.name}님이 교환을 수락했어요.",
        deep_link=f"board:swap:{swap.id}",
    )
    return swap


def reject_swap_request(*, user: User, swap_id: int) -> SwapRequest:
    """교환 요청을 거절합니다 ("아쉽지만 다음에 교환해요")."""
    swap = _get_pending_swap(user=user, swap_id=swap_id)
    if swap.target_item.assignee_id != user.id:
        raise BoardPermissionError("교환 요청을 받은 담당자만 응답할 수 있습니다.")

    swap.status = RequestStatus.REJECTED
    swap.responded_by = user
    swap.resolved_at = timezone.now()
    swap.save(update_fields=["status", "responded_by", "resolved_at"])

    notify(
        home=swap.home,
        recipients=[swap.requester],
        category=NotificationCategory.BOARD,
        title="아쉽지만 다음에 교환해요",
        body=f"{user.name}님은 이번 교환이 어렵다고 했어요.",
        deep_link=f"board:swap:{swap.id}",
    )
    return swap


def cancel_swap_request(*, user: User, swap_id: int) -> None:
    """본인이 만든 대기 중 교환 요청을 취소(삭제)합니다."""
    swap = _get_pending_swap(user=user, swap_id=swap_id)
    if swap.requester_id != user.id:
        raise BoardPermissionError("본인이 올린 카드만 취소할 수 있습니다.")
    swap.delete()


# ──────────────────────────────────────────
# 만료 배치
# ──────────────────────────────────────────


def expire_board_requests(*, now=None) -> tuple[int, int]:
    """응답 기한이 지난 조율 카드를 만료 처리합니다.

    기한은 대상 집안일 날짜의 다음 날 23:59 이며, 교환은 두 항목 중 **이른
    쪽** 을 기준으로 한다 (먼저 지나가는 집안일이 기준).

    Args:
        now: 기준 시각 (테스트용 주입). None 이면 현재 시각.

    Returns:
        (만료된 도움 요청 수, 만료된 교환 요청 수).
    """
    now = now or timezone.now()

    helps = HelpRequest.objects.select_related("item__assignment").filter(status=RequestStatus.PENDING)
    expired_help_ids = [h.id for h in helps if expires_at(h.item) < now]

    swaps = SwapRequest.objects.select_related(
        "requester_item__assignment", "target_item__assignment"
    ).filter(status=RequestStatus.PENDING)
    expired_swap_ids = [
        s.id
        for s in swaps
        if min(expires_at(s.requester_item), expires_at(s.target_item)) < now
    ]

    HelpRequest.objects.filter(id__in=expired_help_ids).update(
        status=RequestStatus.EXPIRED, resolved_at=now
    )
    SwapRequest.objects.filter(id__in=expired_swap_ids).update(
        status=RequestStatus.EXPIRED, resolved_at=now
    )
    return len(expired_help_ids), len(expired_swap_ids)


# ──────────────────────────────────────────
# 봇 카드 발행
# ──────────────────────────────────────────


def publish_bot_card(*, home: Home, kind: str, week_start: date, payload: dict) -> BotCard:
    """봇 카드를 발행합니다 (같은 집·종류·주차에 1건 — 멱등)."""
    card, _created = BotCard.objects.update_or_create(
        home=home, kind=kind, week_start=week_start, defaults={"payload": payload}
    )
    return card

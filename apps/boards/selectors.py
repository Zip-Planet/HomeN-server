"""보드 피드 읽기 전용 쿼리.

피드는 봇 카드와 조율 카드를 **시간순으로 병합한 단일 목록**이다. 각 원소는
`type` 으로 종류를 구분하고, 화면은 `week_start` 가 바뀌는 지점에 주차 구분선을
그린다.
"""

from datetime import timedelta

from apps.boards.models import BotCard, HelpRequest, RequestStatus, SwapRequest
from apps.homes.models import AssignmentItem, ChoreCompletion, Home, WeeklyAssignment
from apps.users.models import User


def _member(user: User | None) -> dict | None:
    if user is None:
        return None
    return {"uid": str(user.uid), "name": user.name, "profile_image": user.profile_image}


def _item_summary(item: AssignmentItem) -> dict:
    """카드에 붙는 대상 집안일 요약 — `욕실청소 · 토 · 난이도 중상 · 160P`."""
    from apps.homes.models import Chore

    return {
        "id": item.id,
        "chore_name": item.chore_name,
        "weekday": item.weekday,
        "weekday_label": Chore.Weekday(item.weekday).label,
        "difficulty": item.difficulty,
        "point": item.point,
        "date": item.assignment.week_start + timedelta(days=item.weekday),
        "assignee": _member(item.assignee),
    }


def get_board_feed(*, home: Home) -> list[dict]:
    """보드 피드를 최신순으로 반환합니다.

    Args:
        home: 대상 집.

    Returns:
        `type` 이 `bot` / `help` / `swap` 인 카드 딕셔너리 목록 (최신순).
    """
    cards: list[dict] = []

    for card in BotCard.objects.filter(home=home):
        cards.append({
            "type": "bot",
            "id": card.id,
            "kind": card.kind,
            "kind_label": card.get_kind_display(),
            "week_start": card.week_start,
            "payload": card.payload,
            "created_at": card.created_at,
        })

    for help_request in HelpRequest.objects.select_related(
        "item__assignment", "item__assignee", "requester", "accepted_by"
    ).filter(home=home):
        cards.append({
            "type": "help",
            "id": help_request.id,
            "status": help_request.status,
            "week_start": help_request.item.assignment.week_start,
            "message": help_request.message,
            "requester": _member(help_request.requester),
            "accepted_by": _member(help_request.accepted_by),
            "item": _item_summary(help_request.item),
            "created_at": help_request.created_at,
        })

    for swap in SwapRequest.objects.select_related(
        "requester_item__assignment",
        "requester_item__assignee",
        "target_item__assignment",
        "target_item__assignee",
        "requester",
        "responded_by",
    ).filter(home=home):
        cards.append({
            "type": "swap",
            "id": swap.id,
            "status": swap.status,
            "week_start": swap.requester_item.assignment.week_start,
            "message": swap.message,
            "requester": _member(swap.requester),
            "responded_by": _member(swap.responded_by),
            "requester_item": _item_summary(swap.requester_item),
            "target_item": _item_summary(swap.target_item),
            "created_at": swap.created_at,
        })

    cards.sort(key=lambda c: (c["created_at"], c["id"]), reverse=True)
    return cards


def get_coordinatable_items(*, home: Home, week_start, assignee: User | None = None) -> list[dict]:
    """조율 카드 생성 화면의 아코디언 목록.

    확정 분담안의 **미완료** 항목만 노출하고, 이미 대기 중인 조율 카드가 걸린
    항목은 `is_requested=True` 로 표시한다 (화면의 "이미 도움 요청한 집안일이에요").

    Args:
        home: 대상 집.
        week_start: 대상 주차의 월요일.
        assignee: 담당자 필터. None 이면 전체 구성원.

    Returns:
        항목 요약 + `is_requested` 목록.
    """
    assignment = (
        WeeklyAssignment.objects.filter(
            home=home, week_start=week_start, status=WeeklyAssignment.Status.CONFIRMED
        )
        .prefetch_related("items__assignee")
        .first()
    )
    if assignment is None:
        return []

    completed = set(
        ChoreCompletion.objects.filter(
            home_chore__home=home,
            date__range=(week_start, week_start + timedelta(days=6)),
        ).values_list("home_chore_id", "date")
    )
    pending_help = set(
        HelpRequest.objects.filter(home=home, status=RequestStatus.PENDING).values_list("item_id", flat=True)
    )
    pending_swap = set(
        SwapRequest.objects.filter(home=home, status=RequestStatus.PENDING).values_list(
            "requester_item_id", flat=True
        )
    )

    rows = []
    for item in assignment.items.all():
        if assignee is not None and item.assignee_id != assignee.id:
            continue
        item_date = week_start + timedelta(days=item.weekday)
        if (item.home_chore_id, item_date) in completed:
            continue
        rows.append({
            **_item_summary(item),
            "is_requested": item.id in pending_help or item.id in pending_swap,
        })
    return rows

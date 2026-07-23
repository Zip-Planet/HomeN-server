"""알림 읽기 전용 쿼리."""

from django.db.models import Case, IntegerField, QuerySet, Value, When

from apps.notifications.models import Notification
from apps.users.models import User


def get_notifications(*, user: User, category: str | None = None) -> QuerySet[Notification]:
    """유저의 알림 목록을 반환합니다.

    정렬은 화면 규칙대로 **미확인 우선 > 최신순** 이다.

    Args:
        user: 수신자.
        category: 카테고리 필터. None/빈 값이면 전체.

    Returns:
        Notification QuerySet.
    """
    queryset = Notification.objects.filter(recipient=user)
    if category:
        queryset = queryset.filter(category=category)

    return queryset.annotate(
        unread_order=Case(
            When(read_at__isnull=True, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    ).order_by("unread_order", "-created_at", "-id")


def get_unread_count(*, user: User) -> int:
    """미확인 알림 개수 (헤더 벨 배지용)."""
    return Notification.objects.filter(recipient=user, read_at__isnull=True).count()

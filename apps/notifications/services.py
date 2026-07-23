"""알림 적재 / 설정 갱신.

발송(푸시) 인프라는 미정이므로 본 모듈은 **인앱 알림 레코드 적재**까지만
수행하고, 실제 푸시 발송 지점은 TODO 로 표시한다. 알림함과 푸시는 문구·랜딩이
동일하므로 발송 시에도 같은 레코드를 근거로 하면 된다.
"""

from datetime import timedelta

from django.utils import timezone

from apps.homes.models import HomeMember
from apps.notifications.models import Notification, NotificationCategory, NotificationSetting
from apps.users.models import User

NOTIFICATION_RETENTION_DAYS = 7
"""알림 보관 기간 — "7일 전 알림까지 확인할 수 있어요"."""


class NotificationError(Exception):
    """알림 관련 오류의 공통 부모."""

    code = "notification_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class NotificationNotFoundError(NotificationError):
    """본인 알림이 아니거나 존재하지 않을 때 발생합니다 (404)."""

    code = "not_found"


def get_or_create_setting(*, user: User) -> NotificationSetting:
    """유저의 푸시 설정을 반환합니다. 없으면 기본값(전체 on)으로 생성합니다."""
    setting, _created = NotificationSetting.objects.get_or_create(user=user)
    return setting


def update_setting(*, user: User, fields: dict) -> NotificationSetting:
    """푸시 설정을 부분 수정합니다.

    Args:
        user: 대상 유저.
        fields: 변경할 토글 부분 dict.

    Returns:
        갱신된 NotificationSetting.
    """
    setting = get_or_create_setting(user=user)
    editable = ("push_enabled", "home_member", "assignment", "board", "reward", "report")
    updates = {k: v for k, v in fields.items() if k in editable}
    if not updates:
        return setting

    for key, value in updates.items():
        setattr(setting, key, value)
    setting.save(update_fields=list(updates.keys()))
    return setting


def notify(
    *,
    home,
    recipients: list[User],
    category: str,
    title: str,
    body: str = "",
    deep_link: str = "",
) -> list[Notification]:
    """수신자들에게 인앱 알림을 적재합니다.

    푸시 설정이 꺼진 유저에게도 **인앱 알림은 남긴다** — 알림함은 기록이고,
    설정 토글은 푸시 발송 여부만 제어하기 때문이다.

    Args:
        home: 알림이 발생한 집.
        recipients: 수신자 목록.
        category: `NotificationCategory` 값.
        title: 알림 제목.
        body: 보조 문구.
        deep_link: 이동 목적지 문자열.

    Returns:
        생성된 Notification 목록.
    """
    if not recipients:
        return []

    created = Notification.objects.bulk_create([
        Notification(
            home=home,
            recipient=user,
            category=category,
            title=title,
            body=body,
            deep_link=deep_link,
        )
        for user in recipients
    ])

    # TODO(푸시): 인프라 확정 후 `NotificationSetting.allows(category)` 가 True 인
    # 수신자에게만 동일 문구/랜딩으로 앱푸시를 발송한다.
    return created


def notify_home(
    *,
    home,
    category: str,
    title: str,
    body: str = "",
    deep_link: str = "",
    exclude: User | None = None,
) -> list[Notification]:
    """집 전체 구성원에게 알림을 적재합니다 (`exclude` 는 제외).

    행위자 본인에게는 알리지 않는 경우가 많아 `exclude` 를 받는다.
    """
    recipients = [
        m.user
        for m in HomeMember.objects.select_related("user").filter(home=home)
        if exclude is None or m.user_id != exclude.id
    ]
    return notify(
        home=home, recipients=recipients, category=category, title=title, body=body, deep_link=deep_link
    )


def notify_admin(
    *,
    home,
    category: str,
    title: str,
    body: str = "",
    deep_link: str = "",
) -> list[Notification]:
    """집 관리자에게만 알림을 적재합니다 (예: 분담안 생성 재촉)."""
    admins = [
        m.user
        for m in HomeMember.objects.select_related("user").filter(
            home=home, role=HomeMember.Role.ADMIN
        )
    ]
    return notify(
        home=home, recipients=admins, category=category, title=title, body=body, deep_link=deep_link
    )


def mark_read(*, user: User, notification_id: int) -> Notification:
    """알림을 확인 처리합니다 (본인 알림만).

    Raises:
        NotificationNotFoundError: 본인 알림이 아니거나 없는 경우.
    """
    notification = Notification.objects.filter(id=notification_id, recipient=user).first()
    if notification is None:
        raise NotificationNotFoundError("알림을 찾을 수 없습니다.")

    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    return notification


def purge_expired_notifications(*, now=None) -> int:
    """보관 기간(7일)이 지난 알림을 삭제합니다.

    Args:
        now: 기준 시각 (테스트용 주입). None 이면 현재 시각.

    Returns:
        삭제 건수.
    """
    cutoff = (now or timezone.now()) - timedelta(days=NOTIFICATION_RETENTION_DAYS)
    deleted, _ = Notification.objects.filter(created_at__lt=cutoff).delete()
    return deleted


def nudge_assignment(*, user: User, week_start) -> list[Notification]:
    """구성원이 관리자에게 분담안 생성을 재촉합니다.

    최종 디자인의 알림 `이번 주 분담안을 기다리고 있어요 / [닉네임]님이 분담안
    생성을 기다리고 있어요` 에 대응한다. 관리자에게만 전달된다.

    Args:
        user: 재촉하는 구성원.
        week_start: 대상 주차의 월요일 날짜.

    Returns:
        생성된 알림 목록 (관리자가 없으면 빈 리스트).

    Raises:
        NotificationError: 속한 집이 없는 경우.
    """
    membership = HomeMember.objects.select_related("home").filter(user=user).first()
    if membership is None:
        raise NotificationError("속한 집이 없습니다.", code="not_found")

    return notify_admin(
        home=membership.home,
        category=NotificationCategory.ASSIGNMENT,
        title="이번 주 분담안을 기다리고 있어요",
        body=f"{user.name}님이 분담안 생성을 기다리고 있어요. 이번 주 분담안을 생성해볼까요?",
        deep_link=f"assignment:{week_start}",
    )

"""알림 적재 / 설정 갱신 / 푸시 기기 등록·발송.

인앱 알림 레코드 적재와, FCM 기기 식별자 등록·해제, 푸시 발송을 담당한다.
`notify` 가 알림 레코드를 만든 뒤 트랜잭션 커밋 시점에 같은 문구·랜딩으로 푸시를
보낸다 (`_push_notifications`). 푸시는 부가 기능이라 어떤 실패도 호출한 서비스로
전파하지 않는다.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from firebase_admin import exceptions as firebase_exceptions
from firebase_admin import messaging

from apps.homes.models import HomeMember
from apps.notifications import fcm
from apps.notifications.models import Device, Notification, NotificationCategory, NotificationSetting
from apps.users.models import User

logger = logging.getLogger(__name__)

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
    """수신자들에게 인앱 알림을 적재하고, 커밋 후 같은 내용의 푸시를 보냅니다.

    푸시 설정이 꺼진 유저에게도 **인앱 알림은 남긴다** — 알림함은 기록이고,
    설정 토글은 푸시 발송 여부만 제어하기 때문이다. 푸시는 트랜잭션이 커밋된
    뒤에 나가며(`transaction.on_commit`), 트랜잭션 밖에서 호출되면 즉시 나간다.

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

    transaction.on_commit(lambda: _push_notifications(created))
    return created


def _push_notifications(notifications: list[Notification]) -> None:
    """알림 레코드와 같은 문구·랜딩의 푸시를 설정이 켜진 수신자에게 보냅니다.

    `notify` 가 커밋 시점에 호출한다. 수신자의 `NotificationSetting` 이 없으면
    기본값(전체 on)으로 본다. FCM 미설정·장애·무효 기기 등 어떤 실패도 로그만 남기고
    삼킨다 — 알림함 레코드와 원래 동작(도움 요청, 분담안 확정 등)은 영향받지 않는다.

    Args:
        notifications: `notify` 가 방금 만든 알림 목록 (제목·본문·카테고리 동일).
    """
    if not notifications or not settings.PUSH_EVENTS_ENABLED:
        return

    first = notifications[0]
    settings_by_user = NotificationSetting.objects.filter(
        user_id__in=[n.recipient_id for n in notifications]
    ).in_bulk(field_name="user_id")
    allowed = [
        n
        for n in notifications
        if (setting := settings_by_user.get(n.recipient_id)) is None or setting.allows(n.category)
    ]
    if not allowed:
        return

    data_by_user = {
        n.recipient_id: {"deep_link": n.deep_link, "category": n.category, "notification_id": str(n.id)}
        for n in allowed
    }
    try:
        result = send_push_to_users(
            users=[n.recipient for n in allowed], title=first.title, body=first.body, data_by_user=data_by_user
        )
    except fcm.PushNotConfiguredError as e:
        logger.info("푸시 발송 건너뜀 (FCM 미설정): %s", e)
    except Exception:
        logger.exception("푸시 발송 실패 category=%s recipients=%d", first.category, len(allowed))
    else:
        logger.info(
            "푸시 발송 category=%s recipients=%d sent=%d failed=%d deactivated=%d",
            first.category, len(allowed), result.sent, result.failed, result.deactivated,
        )


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


# ── 푸시 기기 등록 / 해제 / 발송 ──────────────────────────────────────────────

_DEAD_REGISTRATION_ERRORS = (messaging.UnregisteredError, firebase_exceptions.InvalidArgumentError)
"""FCM 이 "이 식별자는 더 이상 유효하지 않다" 로 답한 경우 — 기기를 비활성화한다."""


@dataclass(frozen=True)
class PushResult:
    """`send_push_to_user` 결과 집계.

    Attributes:
        sent: 전달(또는 dry_run 검증) 성공 수.
        failed: 실패 수 (비활성화된 기기 포함).
        deactivated: 실패 중 식별자가 무효해 `is_active=False` 처리한 수.
    """

    sent: int
    failed: int
    deactivated: int


def register_device(
    *, user: User, registration_id: str, kind: str, platform: str, app_version: str = ""
) -> tuple[Device, bool]:
    """기기 식별자를 현재 유저에게 등록(없으면 생성, 있으면 갱신)합니다.

    같은 기기에 다른 계정이 로그인한 경우 행을 현재 유저로 옮긴다. 호출할 때마다
    `last_seen_at` 을 갱신하고 `is_active` 를 되살린다.

    Args:
        user: 현재 로그인한 유저.
        registration_id: FCM registration token 또는 FID.
        kind: `Device.Kind` 값.
        platform: `Device.Platform` 값.
        app_version: 앱 버전 (선택).

    Returns:
        (Device, 새로 생성됐는지 여부).
    """
    device, created = Device.objects.update_or_create(
        registration_id=registration_id,
        defaults={
            "user": user,
            "kind": kind,
            "platform": platform,
            "app_version": app_version,
            "is_active": True,
            "last_seen_at": timezone.now(),
        },
    )
    return device, created


def unregister_device(*, user: User, registration_id: str) -> None:
    """본인 기기를 발송 대상에서 제외합니다 (로그아웃 시). 없거나 타인 기기면 무시합니다."""
    Device.objects.filter(user=user, registration_id=registration_id).update(is_active=False)


def send_push_to_users(
    *,
    users: list[User],
    title: str,
    body: str,
    data: dict[str, str] | None = None,
    data_by_user: dict[int, dict[str, str]] | None = None,
    dry_run: bool = False,
) -> PushResult:
    """여러 유저의 활성 기기 전부에 푸시를 보냅니다 (500개 단위로 FCM 호출).

    FCM 이 무효하다고 답한 기기(UNREGISTERED / INVALID_ARGUMENT)는 `is_active=False`
    로 바꾼다.

    Args:
        users: 수신 유저 목록.
        title: 알림 제목.
        body: 알림 본문.
        data: 모든 기기에 공통으로 실을 데이터.
        data_by_user: 유저 PK 별로 추가할 데이터 (예: 수신자마다 다른 `notification_id`).
            `data` 와 합쳐지며 같은 키는 이쪽이 우선한다.
        dry_run: True 면 FCM 검증만 하고 실제 전달하지 않는다.

    Returns:
        발송 결과 집계.

    Raises:
        fcm.PushNotConfiguredError: FCM 자격증명이 없을 때.
    """
    devices = list(Device.objects.filter(user__in=users, is_active=True).order_by("id"))
    if not devices:
        return PushResult(sent=0, failed=0, deactivated=0)

    targets = []
    for device in devices:
        merged = {**(data or {}), **(data_by_user or {}).get(device.user_id, {})}
        targets.append(fcm.PushTarget(registration_id=device.registration_id, kind=device.kind, data=merged or None))

    sent = failed = 0
    dead_ids: list[str] = []
    for start in range(0, len(targets), fcm.BATCH_LIMIT):
        chunk = targets[start : start + fcm.BATCH_LIMIT]
        response = fcm.send_each(targets=chunk, title=title, body=body, dry_run=dry_run)
        for target, item in zip(chunk, response.responses, strict=True):
            if item.success:
                sent += 1
                continue
            failed += 1
            if isinstance(item.exception, _DEAD_REGISTRATION_ERRORS):
                dead_ids.append(target.registration_id)

    if dead_ids:
        Device.objects.filter(registration_id__in=dead_ids).update(is_active=False)
    return PushResult(sent=sent, failed=failed, deactivated=len(dead_ids))


def send_push_to_user(
    *, user: User, title: str, body: str, data: dict[str, str] | None = None, dry_run: bool = False
) -> PushResult:
    """유저 한 명의 활성 기기 전부에 푸시를 보냅니다 (`send_push_to_users` 의 단일 유저 버전)."""
    return send_push_to_users(users=[user], title=title, body=body, data=data, dry_run=dry_run)

"""알림 적재 / 설정 갱신 / 푸시 기기 등록·발송.

인앱 알림 레코드 적재와, FCM 기기 식별자 등록·해제, 유저 단위 푸시 발송을 담당한다.
알림 이벤트(`notify`)와 푸시 발송(`send_push_to_user`)의 연결은 아직 하지 않았다 —
`notify` 의 TODO 참고. 알림함과 푸시는 문구·랜딩이 동일하므로 연결 시 같은 레코드를
근거로 하면 된다.
"""

from dataclasses import dataclass
from datetime import timedelta
from itertools import groupby

from django.utils import timezone
from firebase_admin import exceptions as firebase_exceptions
from firebase_admin import messaging

from apps.homes.models import HomeMember
from apps.notifications import fcm
from apps.notifications.models import Device, Notification, NotificationCategory, NotificationSetting
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

    # TODO(푸시): `NotificationSetting.allows(category)` 가 True 인 수신자에게
    # `send_push_to_user(user=..., title=title, body=body, data={"deep_link": deep_link})`
    # 로 동일 문구/랜딩의 앱푸시를 발송한다 (기기 등록·발송 서비스는 준비됨).
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


def send_push_to_user(
    *, user: User, title: str, body: str, data: dict[str, str] | None = None, dry_run: bool = False
) -> PushResult:
    """유저의 활성 기기 전부에 푸시를 보냅니다.

    식별자 종류(token/fid)별로 나눠 FCM 에 보내고, FCM 이 무효하다고 답한 기기
    (UNREGISTERED / INVALID_ARGUMENT) 는 `is_active=False` 로 바꾼다.

    Args:
        user: 수신 유저.
        title: 알림 제목.
        body: 알림 본문.
        data: 앱이 받을 추가 데이터.
        dry_run: True 면 FCM 검증만 하고 실제 전달하지 않는다.

    Returns:
        발송 결과 집계.

    Raises:
        fcm.PushNotConfiguredError: FCM 자격증명이 없을 때.
    """
    devices = list(Device.objects.filter(user=user, is_active=True).order_by("kind", "id"))
    if not devices:
        return PushResult(sent=0, failed=0, deactivated=0)

    sent = failed = 0
    dead_ids: list[str] = []
    for kind, group in groupby(devices, key=lambda d: d.kind):
        ids = [d.registration_id for d in group]
        response = fcm.send_multicast(
            registration_ids=ids, kind=kind, title=title, body=body, data=data, dry_run=dry_run
        )
        for registration_id, item in zip(ids, response.responses, strict=True):
            if item.success:
                sent += 1
                continue
            failed += 1
            if isinstance(item.exception, _DEAD_REGISTRATION_ERRORS):
                dead_ids.append(registration_id)

    if dead_ids:
        Device.objects.filter(registration_id__in=dead_ids).update(is_active=False)
    return PushResult(sent=sent, failed=failed, deactivated=len(dead_ids))

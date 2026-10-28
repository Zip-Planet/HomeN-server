"""Firebase Cloud Messaging(FCM) 발송 어댑터.

firebase-admin SDK 호출을 한곳에 모은다. 비즈니스 규칙(누구에게 보낼지, 실패한
기기를 어떻게 처리할지)은 `services.py` 가 맡고, 본 모듈은 "주어진 식별자 목록에
한 번 보낸다"만 한다. 테스트는 `send_multicast` 를 patch 한다.

초기화는 첫 발송 시점에 한 번만 한다 — 자격증명(`FIREBASE_CREDENTIALS_JSON`)이
없어도 서버 기동과 테스트에 영향을 주지 않기 위해서다.
"""

import json

import firebase_admin
from django.conf import settings
from firebase_admin import credentials, messaging

FIREBASE_APP_NAME = "homen-push"
MULTICAST_LIMIT = 500
"""FCM 이 한 번의 multicast 에 허용하는 최대 식별자 수."""


class PushNotConfiguredError(Exception):
    """FCM 자격증명이 없거나 잘못돼 발송할 수 없을 때 발생합니다."""


def _get_app() -> firebase_admin.App:
    """FCM 발송용 Firebase 앱을 반환합니다 (없으면 설정에서 생성).

    Raises:
        PushNotConfiguredError: `FIREBASE_CREDENTIALS_JSON` 이 비어 있거나 JSON 이 아닌 경우.
    """
    try:
        return firebase_admin.get_app(FIREBASE_APP_NAME)
    except ValueError:
        pass

    raw = settings.FIREBASE_CREDENTIALS_JSON
    if not raw:
        raise PushNotConfiguredError("FIREBASE_CREDENTIALS_JSON 이 설정되지 않았습니다.")
    try:
        cert = credentials.Certificate(json.loads(raw))
    except (ValueError, OSError) as e:
        raise PushNotConfiguredError(f"FIREBASE_CREDENTIALS_JSON 이 올바르지 않습니다: {e}") from e
    return firebase_admin.initialize_app(cert, name=FIREBASE_APP_NAME)


def send_multicast(
    *,
    registration_ids: list[str],
    kind: str,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
    dry_run: bool = False,
) -> messaging.BatchResponse:
    """같은 종류(token/fid)의 식별자 목록에 알림 한 건을 보냅니다.

    Args:
        registration_ids: FCM registration token 또는 FID 목록 (최대 500).
        kind: `Device.Kind` 값 — `token` 이면 `tokens=`, `fid` 면 `fids=` 로 보낸다.
        title: 알림 제목.
        body: 알림 본문.
        data: 앱이 받을 추가 데이터 (값은 문자열).
        dry_run: True 면 실제 전달 없이 FCM 검증만 수행한다.

    Returns:
        입력 순서와 같은 순서의 `BatchResponse`.

    Raises:
        PushNotConfiguredError: 자격증명이 없을 때.
        ValueError: 식별자가 500개를 넘을 때.
    """
    if len(registration_ids) > MULTICAST_LIMIT:
        raise ValueError(f"한 번에 {MULTICAST_LIMIT}개까지만 보낼 수 있습니다.")

    app = _get_app()
    ids_kwargs = {"fids": registration_ids} if kind == "fid" else {"tokens": registration_ids}
    message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body),
        data=data,
        apns=messaging.APNSConfig(payload=messaging.APNSPayload(aps=messaging.Aps(sound="default"))),
        **ids_kwargs,
    )
    return messaging.send_each_for_multicast(message, dry_run=dry_run, app=app)

from unittest.mock import patch

import pytest
from firebase_admin import messaging

from apps.notifications import fcm


class TestGetApp:
    def test_자격증명이_비어_있으면_PushNotConfiguredError(self, settings):
        settings.FIREBASE_CREDENTIALS_JSON = ""

        with pytest.raises(fcm.PushNotConfiguredError):
            fcm._get_app()

    def test_JSON이_깨져_있으면_PushNotConfiguredError(self, settings):
        settings.FIREBASE_CREDENTIALS_JSON = "{not json"

        with pytest.raises(fcm.PushNotConfiguredError):
            fcm._get_app()


class TestSendEach:
    @patch("apps.notifications.fcm.messaging.send_each")
    @patch("apps.notifications.fcm._get_app", return_value="app")
    def test_대상마다_token_또는_fid_메시지를_만들어_한_번에_보낸다(self, _mock_app, mock_send):
        mock_send.return_value = messaging.BatchResponse([])
        targets = [
            fcm.PushTarget(registration_id="tok-1", kind="token", data={"deep_link": "a"}),
            fcm.PushTarget(registration_id="fid-1", kind="fid", data=None),
        ]

        fcm.send_each(targets=targets, title="t", body="b", dry_run=True)

        messages = mock_send.call_args.args[0]
        assert [(m.token, m.fid, m.data) for m in messages] == [
            ("tok-1", None, {"deep_link": "a"}),
            (None, "fid-1", None),
        ]
        assert all(m.notification.title == "t" and m.notification.body == "b" for m in messages)
        assert mock_send.call_args.kwargs == {"dry_run": True, "app": "app"}

    def test_500개를_넘으면_ValueError(self):
        targets = [fcm.PushTarget(registration_id=f"tok-{i}", kind="token") for i in range(501)]

        with pytest.raises(ValueError):
            fcm.send_each(targets=targets, title="t", body="b")

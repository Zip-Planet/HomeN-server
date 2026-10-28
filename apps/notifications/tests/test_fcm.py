import pytest

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

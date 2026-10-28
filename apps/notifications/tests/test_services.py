from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.homes.models import HomeMember
from apps.homes.services import week_start_of
from apps.homes.tests.factories import HomeFactory, HomeMemberFactory
from apps.notifications.models import Notification, NotificationCategory
from apps.notifications.selectors import get_notifications, get_unread_count
from apps.notifications.services import (
    NotificationError,
    NotificationNotFoundError,
    get_or_create_setting,
    mark_read,
    notify_admin,
    notify_home,
    nudge_assignment,
    purge_expired_notifications,
    update_setting,
)
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _home_with_members(member_count: int = 2):
    admin = UserFactory()
    home = HomeFactory()
    HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
    members = [UserFactory() for _ in range(member_count)]
    for user in members:
        HomeMemberFactory(home=home, user=user, role=HomeMember.Role.MEMBER)
    return home, admin, members


class TestNotify:
    def test_집_전체에_알림이_적재된다(self):
        home, admin, members = _home_with_members()

        created = notify_home(
            home=home,
            category=NotificationCategory.ASSIGNMENT,
            title="다음 주 분담안이 생성됐어요",
        )

        assert len(created) == 3
        assert Notification.objects.filter(home=home).count() == 3

    def test_exclude_한_유저는_제외된다(self):
        home, admin, members = _home_with_members()

        notify_home(
            home=home,
            category=NotificationCategory.HOME_MEMBER,
            title="새 구성원이 참여했어요",
            exclude=admin,
        )

        assert not Notification.objects.filter(recipient=admin).exists()
        assert Notification.objects.count() == 2

    def test_관리자에게만_보내기(self):
        home, admin, _members = _home_with_members()

        notify_admin(home=home, category=NotificationCategory.ASSIGNMENT, title="확인해 주세요")

        assert Notification.objects.count() == 1
        assert Notification.objects.first().recipient == admin


class TestNudgeAssignment:
    def test_구성원이_재촉하면_관리자에게_알림(self):
        home, admin, members = _home_with_members()
        member = members[0]

        created = nudge_assignment(user=member, week_start=week_start_of(timezone.localdate()))

        assert len(created) == 1
        notification = created[0]
        assert notification.recipient == admin
        assert notification.title == "이번 주 분담안을 기다리고 있어요"
        assert member.name in notification.body

    def test_집이_없으면_에러(self):
        with pytest.raises(NotificationError):
            nudge_assignment(user=UserFactory(), week_start=week_start_of(timezone.localdate()))


class TestNotificationOrdering:
    def test_미확인_우선_최신순(self):
        home, admin, _ = _home_with_members(member_count=0)
        notify_home(home=home, category=NotificationCategory.REPORT, title="오래된 미확인")
        notify_home(home=home, category=NotificationCategory.REWARD, title="읽은 알림")
        read_target = Notification.objects.get(title="읽은 알림")
        mark_read(user=admin, notification_id=read_target.id)
        notify_home(home=home, category=NotificationCategory.BOARD, title="최신 미확인")

        titles = [n.title for n in get_notifications(user=admin)]

        assert titles == ["최신 미확인", "오래된 미확인", "읽은 알림"]

    def test_카테고리_필터(self):
        home, admin, _ = _home_with_members(member_count=0)
        notify_home(home=home, category=NotificationCategory.REPORT, title="리포트")
        notify_home(home=home, category=NotificationCategory.REWARD, title="리워드")

        titles = [n.title for n in get_notifications(user=admin, category="report")]

        assert titles == ["리포트"]

    def test_미확인_개수(self):
        home, admin, _ = _home_with_members(member_count=0)
        notify_home(home=home, category=NotificationCategory.REPORT, title="a")
        notify_home(home=home, category=NotificationCategory.REPORT, title="b")

        assert get_unread_count(user=admin) == 2

        mark_read(user=admin, notification_id=Notification.objects.first().id)

        assert get_unread_count(user=admin) == 1


class TestMarkRead:
    def test_본인_알림이_아니면_404(self):
        home, admin, _ = _home_with_members(member_count=0)
        notify_home(home=home, category=NotificationCategory.REPORT, title="a")
        other = UserFactory()

        with pytest.raises(NotificationNotFoundError):
            mark_read(user=other, notification_id=Notification.objects.first().id)


class TestPurge:
    def test_7일_지난_알림은_삭제된다(self):
        home, admin, _ = _home_with_members(member_count=0)
        notify_home(home=home, category=NotificationCategory.REPORT, title="old")
        notify_home(home=home, category=NotificationCategory.REPORT, title="new")
        old = Notification.objects.get(title="old")
        Notification.objects.filter(id=old.id).update(
            created_at=timezone.now() - timedelta(days=8)
        )

        deleted = purge_expired_notifications()

        assert deleted == 1
        assert list(Notification.objects.values_list("title", flat=True)) == ["new"]

    def test_management_command_실행(self):
        out = StringIO()

        call_command("purge_notifications", stdout=out)

        assert "만료 알림 삭제 완료" in out.getvalue()


class TestNotificationSetting:
    def test_기본값은_전체_on(self):
        setting = get_or_create_setting(user=UserFactory())

        assert setting.push_enabled is True
        assert setting.allows("board") is True

    def test_마스터_토글이_꺼지면_모두_차단(self):
        user = UserFactory()
        update_setting(user=user, fields={"push_enabled": False})

        setting = get_or_create_setting(user=user)

        assert setting.allows("assignment") is False

    def test_카테고리별_토글(self):
        user = UserFactory()

        setting = update_setting(user=user, fields={"board": False})

        assert setting.allows("board") is False
        assert setting.allows("reward") is True


# ── 기기 등록 / 해제 / 푸시 발송 ──────────────────────────────────────────────

from datetime import UTC, datetime  # noqa: E402
from unittest.mock import patch  # noqa: E402

from firebase_admin import exceptions as firebase_exceptions  # noqa: E402
from firebase_admin import messaging  # noqa: E402

from apps.notifications.fcm import PushNotConfiguredError  # noqa: E402
from apps.notifications.models import Device  # noqa: E402
from apps.notifications.services import (  # noqa: E402
    PushResult,
    register_device,
    send_push_to_user,
    unregister_device,
)
from apps.notifications.tests.factories import DeviceFactory  # noqa: E402


def _batch(*exceptions):
    """성공(None) / 실패(예외) 순서대로 SendResponse 를 담은 BatchResponse."""
    responses = [
        messaging.SendResponse({"name": f"projects/x/messages/{i}"} if exc is None else None, exc)
        for i, exc in enumerate(exceptions)
    ]
    return messaging.BatchResponse(responses)


class TestRegisterDevice:
    def test_처음_등록하면_생성된다(self):
        user = UserFactory()

        device, created = register_device(user=user, registration_id="tok-1", kind="token", platform="ios")

        assert created is True
        assert device.user == user
        assert device.is_active is True
        assert Device.objects.count() == 1

    def test_같은_식별자로_다시_등록하면_갱신만_된다(self):
        user = UserFactory()
        old = DeviceFactory(user=user, registration_id="tok-1", app_version="1.0.0", is_active=False)
        old.last_seen_at = datetime(2020, 1, 1, tzinfo=UTC)
        old.save(update_fields=["last_seen_at"])

        device, created = register_device(
            user=user, registration_id="tok-1", kind="token", platform="ios", app_version="1.1.0"
        )

        assert created is False
        assert Device.objects.count() == 1
        assert device.app_version == "1.1.0"
        assert device.is_active is True
        assert device.last_seen_at.year == timezone.now().year

    def test_다른_유저가_같은_기기로_등록하면_새_유저로_옮겨진다(self):
        first, second = UserFactory(), UserFactory()
        DeviceFactory(user=first, registration_id="tok-shared")

        device, _ = register_device(user=second, registration_id="tok-shared", kind="token", platform="android")

        assert Device.objects.count() == 1
        assert device.user == second
        assert not Device.objects.filter(user=first).exists()


class TestUnregisterDevice:
    def test_본인_기기를_비활성화한다(self):
        user = UserFactory()
        DeviceFactory(user=user, registration_id="tok-1")

        unregister_device(user=user, registration_id="tok-1")

        assert Device.objects.get(registration_id="tok-1").is_active is False

    def test_없는_기기나_타인_기기는_조용히_무시한다(self):
        user, other = UserFactory(), UserFactory()
        DeviceFactory(user=other, registration_id="tok-other")

        unregister_device(user=user, registration_id="tok-other")
        unregister_device(user=user, registration_id="tok-missing")

        assert Device.objects.get(registration_id="tok-other").is_active is True


class TestSendPushToUser:
    @patch("apps.notifications.services.fcm.send_multicast")
    def test_활성_기기가_없으면_발송하지_않는다(self, mock_send):
        user = UserFactory()
        DeviceFactory(user=user, is_active=False)

        result = send_push_to_user(user=user, title="t", body="b")

        assert result == PushResult(sent=0, failed=0, deactivated=0)
        mock_send.assert_not_called()

    @patch("apps.notifications.services.fcm.send_multicast")
    def test_종류별로_나눠_보내고_결과를_합산한다(self, mock_send):
        user = UserFactory()
        DeviceFactory(user=user, registration_id="tok-1", kind="token")
        DeviceFactory(user=user, registration_id="tok-2", kind="token")
        DeviceFactory(user=user, registration_id="fid-1", kind="fid")
        mock_send.side_effect = lambda **kw: _batch(*([None] * len(kw["registration_ids"])))

        result = send_push_to_user(user=user, title="t", body="b", data={"k": "v"}, dry_run=True)

        assert result == PushResult(sent=3, failed=0, deactivated=0)
        kinds = sorted(call.kwargs["kind"] for call in mock_send.call_args_list)
        assert kinds == ["fid", "token"]
        for call in mock_send.call_args_list:
            assert call.kwargs["dry_run"] is True
            assert call.kwargs["data"] == {"k": "v"}

    @patch("apps.notifications.services.fcm.send_multicast")
    def test_UNREGISTERED_INVALID_ARGUMENT_응답_기기는_비활성화된다(self, mock_send):
        user = UserFactory()
        DeviceFactory(user=user, registration_id="tok-ok", kind="token")
        DeviceFactory(user=user, registration_id="tok-gone", kind="token")
        DeviceFactory(user=user, registration_id="tok-bad", kind="token")
        DeviceFactory(user=user, registration_id="tok-quota", kind="token")
        mock_send.return_value = _batch(
            None,
            messaging.UnregisteredError("gone"),
            firebase_exceptions.InvalidArgumentError("bad token"),
            messaging.QuotaExceededError("later"),
        )

        result = send_push_to_user(user=user, title="t", body="b")

        assert result == PushResult(sent=1, failed=3, deactivated=2)
        assert Device.objects.get(registration_id="tok-ok").is_active is True
        assert Device.objects.get(registration_id="tok-gone").is_active is False
        assert Device.objects.get(registration_id="tok-bad").is_active is False
        assert Device.objects.get(registration_id="tok-quota").is_active is True

    @patch("apps.notifications.services.fcm.send_multicast", side_effect=PushNotConfiguredError("no creds"))
    def test_자격증명_미설정이면_예외가_그대로_올라온다(self, _mock_send):
        user = UserFactory()
        DeviceFactory(user=user)

        with pytest.raises(PushNotConfiguredError):
            send_push_to_user(user=user, title="t", body="b")


class TestSendTestPushCommand:
    @patch("apps.notifications.services.fcm.send_multicast")
    def test_커맨드가_결과를_출력한다(self, mock_send):
        user = UserFactory()
        DeviceFactory(user=user)
        mock_send.return_value = _batch(None)
        out = StringIO()

        call_command("send_test_push", "--user", str(user.id), "--dry-run", stdout=out)

        assert "sent=1" in out.getvalue()
        assert mock_send.call_args.kwargs["dry_run"] is True

    def test_없는_유저면_에러(self):
        from django.core.management.base import CommandError

        with pytest.raises(CommandError):
            call_command("send_test_push", "--user", "999999")

    @patch("apps.notifications.services.fcm.send_multicast", side_effect=PushNotConfiguredError("no creds"))
    def test_자격증명_미설정이면_에러(self, _mock_send):
        from django.core.management.base import CommandError

        user = UserFactory()
        DeviceFactory(user=user)

        with pytest.raises(CommandError):
            call_command("send_test_push", "--user", str(user.id))

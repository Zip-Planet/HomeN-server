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

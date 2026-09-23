import pytest
from django.utils import timezone

from apps.homes.models import Chore, HomeMember
from apps.homes.services import _generate_assignment_for_home, complete_chore, week_start_of
from apps.homes.tests.factories import ChoreFactory, HomeChoreFactory, HomeFactory, HomeMemberFactory
from apps.notifications.models import Notification
from apps.reports.models import WeeklyReport
from apps.reports.selectors import get_weekly_report
from apps.reports.services import generate_report
from apps.reports.tests.test_services import _confirmed_home
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestGetWeeklyReport:
    def test_조회_시점_기준으로_실시간_집계한다(self):
        home, admin, _ = _confirmed_home(complete=2)

        report = get_weekly_report(home=home, week_start=week_start_of(timezone.localdate()))

        assert report is not None
        assert report.pk is None
        assert report.generated_at is not None
        assert report.total_count == 3
        assert report.completed_count == 2
        assert report.progress_rate == 67
        assert report.mvp_user == admin
        assert report.mvp_point == 240
        assert WeeklyReport.objects.count() == 0

    def test_실시간_집계는_알림을_만들지_않는다(self):
        home, _admin, _ = _confirmed_home(complete=1)
        before = Notification.objects.count()  # 확정·완료 알림은 fixture 가 만든 것

        get_weekly_report(home=home, week_start=week_start_of(timezone.localdate()))

        assert Notification.objects.count() == before

    def test_스냅샷이_있어도_현재_완료_현황을_반영한다(self):
        home, admin, assignment = _confirmed_home(complete=1)
        week_start = week_start_of(timezone.localdate())
        generate_report(home=home, week_start=week_start)
        complete_chore(user=admin, home_chore_id=list(assignment.items.all())[1].home_chore_id)

        report = get_weekly_report(home=home, week_start=week_start)

        assert report.pk is None
        assert report.completed_count == 2

    def test_분담안이_없으면_None(self):
        home = HomeFactory()

        assert get_weekly_report(home=home, week_start=week_start_of(timezone.localdate())) is None

    def test_제안됨_분담안만_있으면_None(self):
        admin = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
        today = timezone.localdate()
        for i in range(3):
            HomeChoreFactory(
                home=home,
                chore=ChoreFactory(
                    starter_pack=None, name=f"c{i}", difficulty=Chore.Difficulty.MEDIUM, repeat_days=[today.weekday()]
                ),
            )
        _generate_assignment_for_home(home=home, week_start=week_start_of(today))

        assert get_weekly_report(home=home, week_start=week_start_of(today)) is None

from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.homes.models import Chore, HomeMember
from apps.homes.services import (
    _generate_assignment_for_home,
    _mark_confirmed,
    complete_chore,
    week_start_of,
)
from apps.homes.tests.factories import ChoreFactory, HomeChoreFactory, HomeFactory, HomeMemberFactory
from apps.reports.models import WeeklyReport
from apps.reports.services import generate_report, generate_weekly_reports
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _confirmed_home(*, complete: int = 0, chore_count: int = 3):
    admin = UserFactory()
    home = HomeFactory()
    HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
    today = timezone.localdate()
    for i in range(chore_count):
        chore = ChoreFactory(
            starter_pack=None,
            name=f"집안일{i}",
            difficulty=Chore.Difficulty.MEDIUM,  # 120P
            repeat_days=[today.weekday()],
        )
        HomeChoreFactory(home=home, chore=chore)

    assignment = _generate_assignment_for_home(home=home, week_start=week_start_of(today))
    _mark_confirmed(assignment, confirmed_by=admin)
    for item in list(assignment.items.all())[:complete]:
        complete_chore(user=admin, home_chore_id=item.home_chore_id)
    return home, admin, assignment


class TestGenerateReport:
    def test_진행률과_MVP_가_집계된다(self):
        home, admin, _ = _confirmed_home(complete=2)

        report = generate_report(home=home, week_start=week_start_of(timezone.localdate()))

        assert report.total_count == 3
        assert report.completed_count == 2
        assert report.progress_rate == 67
        assert report.mvp_user == admin
        assert report.mvp_name == admin.name
        assert report.mvp_point == 240
        assert report.mvp_completed_count == 2

    def test_구성원_통계에_배정과_완료가_모두_담긴다(self):
        home, admin, _ = _confirmed_home(complete=1)
        member = UserFactory()
        HomeMemberFactory(home=home, user=member, role=HomeMember.Role.MEMBER)

        report = generate_report(home=home, week_start=week_start_of(timezone.localdate()))

        admin_row = next(r for r in report.member_stats if r["uid"] == str(admin.uid))
        assert admin_row["assigned_count"] == 3
        assert admin_row["completed_count"] == 1
        assert admin_row["point"] == 120
        # 나중에 합류해 배정이 없는 구성원도 0건으로 노출된다.
        member_row = next(r for r in report.member_stats if r["uid"] == str(member.uid))
        assert member_row["assigned_count"] == 0

    def test_하이라이트는_완료_미완료_최다_집안일(self):
        home, admin, _ = _confirmed_home(complete=1)

        report = generate_report(home=home, week_start=week_start_of(timezone.localdate()))

        assert report.most_done["count"] == 1
        assert report.most_missed["count"] == 1
        assert report.most_done["name"] != report.most_missed["name"]

    def test_완료가_없으면_MVP_는_null(self):
        home, _admin, _ = _confirmed_home(complete=0)

        report = generate_report(home=home, week_start=week_start_of(timezone.localdate()))

        assert report.mvp_user is None
        assert report.mvp_name == ""
        assert report.progress_rate == 0

    def test_분담안이_없으면_생성하지_않는다(self):
        home = HomeFactory()

        assert generate_report(home=home, week_start=week_start_of(timezone.localdate())) is None

    def test_제안됨_분담안은_리포트_대상이_아니다(self):
        admin = UserFactory()
        home = HomeFactory()
        HomeMemberFactory(home=home, user=admin, role=HomeMember.Role.ADMIN)
        today = timezone.localdate()
        for i in range(3):
            HomeChoreFactory(
                home=home,
                chore=ChoreFactory(starter_pack=None, name=f"c{i}", repeat_days=[today.weekday()]),
            )
        _generate_assignment_for_home(home=home, week_start=week_start_of(today))

        assert generate_report(home=home, week_start=week_start_of(today)) is None

    def test_중복_실행은_덮어쓴다_멱등(self):
        home, admin, _ = _confirmed_home(complete=1)
        week_start = week_start_of(timezone.localdate())

        generate_report(home=home, week_start=week_start)
        generate_report(home=home, week_start=week_start)

        assert WeeklyReport.objects.filter(home=home, week_start=week_start).count() == 1


class TestGenerateWeeklyReportsCommand:
    def test_커맨드가_활성_집을_순회한다(self):
        home, _admin, _ = _confirmed_home(complete=1)
        HomeFactory()  # 분담안 없는 집 → 스킵

        created, skipped = generate_weekly_reports()

        assert created == 1
        assert skipped == 1

    def test_management_command_실행(self):
        _confirmed_home(complete=1)
        out = StringIO()

        call_command("generate_weekly_reports", stdout=out)

        assert "주간 리포트 생성 완료" in out.getvalue()

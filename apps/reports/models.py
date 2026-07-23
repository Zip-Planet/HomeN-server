from django.db import models

from apps.homes.models import Home
from apps.users.models import User


class WeeklyReport(models.Model):
    """주간 리포트 스냅샷 (R1_WeeklyReport).

    화면 구성: 이번 주 진행률 / 우리집 MVP / 구성원별 달성 순위 / 이번주 하이라이트
    (가장 많이 한 집안일, 미완료가 많은 집안일).

    집계는 생성 시점에 굳혀 저장한다 — 리포트는 "그 주에 무슨 일이 있었나" 를
    남기는 기록이므로 이후 집안일 수정·삭제에 소급되면 안 된다.

    Attributes:
        home: 대상 집.
        week_start: 대상 주차의 월요일 날짜.
        total_count / completed_count: 그 주 전체·완료 항목 수.
        progress_rate: 진행률 % (반올림 정수).
        mvp_user: 완료 포인트 1위 구성원 (탈퇴 시 NULL).
        mvp_point / mvp_completed_count: MVP 의 완료 포인트·건수 스냅샷.
        mvp_name: MVP 닉네임 스냅샷 (탈퇴해도 화면에 남기기 위해).
        member_stats: 구성원별 달성 현황 목록 (JSON 스냅샷).
        most_done / most_missed: 하이라이트 `{name, count}` (없으면 null).
        generated_at: 리포트 생성 시각.
    """

    home = models.ForeignKey(Home, on_delete=models.CASCADE, related_name="weekly_reports")
    week_start = models.DateField()

    total_count = models.PositiveIntegerField(default=0)
    completed_count = models.PositiveIntegerField(default=0)
    progress_rate = models.PositiveIntegerField(default=0)

    mvp_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mvp_reports",
    )
    mvp_name = models.CharField(max_length=8, blank=True, default="")
    mvp_point = models.PositiveIntegerField(default=0)
    mvp_completed_count = models.PositiveIntegerField(default=0)

    member_stats = models.JSONField(default=list)
    most_done = models.JSONField(null=True, blank=True)
    most_missed = models.JSONField(null=True, blank=True)

    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "weekly_reports"
        constraints = [
            models.UniqueConstraint(fields=["home", "week_start"], name="uniq_weekly_report_per_home_week"),
        ]
        ordering = ["-week_start"]

    def __str__(self) -> str:
        return f"weekly_report:{self.pk}:{self.week_start}"

"""주간 리포트 출력 스키마 (R1_WeeklyReport)."""

from rest_framework import serializers

from apps.reports.models import WeeklyReport


class ReportMemberStatSerializer(serializers.Serializer):
    """구성원별 달성 현황 한 줄 — 화면의 "누가 가장 많이 달성했을까요?"."""

    uid = serializers.CharField(help_text="유저 uid.")
    name = serializers.CharField(help_text="닉네임 (생성 시점 스냅샷).")
    profile_image = serializers.IntegerField(allow_null=True, help_text="프로필 이미지 enum.")
    assigned_count = serializers.IntegerField(help_text="배정된 항목 수.")
    completed_count = serializers.IntegerField(help_text="완료한 항목 수.")
    point = serializers.IntegerField(help_text="완료로 획득한 포인트 합.")


class ReportHighlightSerializer(serializers.Serializer):
    """하이라이트 한 건 — `{name, count}`."""

    name = serializers.CharField(help_text="집안일명.")
    count = serializers.IntegerField(help_text="횟수.")


class WeeklyReportOutputSerializer(serializers.ModelSerializer):
    """주간 리포트 응답."""

    mvp = serializers.SerializerMethodField(
        help_text="우리집 MVP `{uid, name, profile_image, point, completed_count}`. 완료 이력이 없으면 null.",
    )
    member_stats = ReportMemberStatSerializer(
        many=True, help_text="구성원별 달성 현황 (포인트 내림차순)."
    )
    most_done = ReportHighlightSerializer(
        allow_null=True, help_text="가장 많이 한 집안일 `{name, count}`."
    )
    most_missed = ReportHighlightSerializer(
        allow_null=True, help_text="미완료가 많은 집안일 `{name, count}`."
    )

    class Meta:
        model = WeeklyReport
        fields = [
            "id",
            "week_start",
            "total_count",
            "completed_count",
            "progress_rate",
            "mvp",
            "member_stats",
            "most_done",
            "most_missed",
            "generated_at",
        ]
        extra_kwargs = {
            "id": {"help_text": "리포트 PK."},
            "week_start": {"help_text": "대상 주차의 월요일 날짜."},
            "total_count": {"help_text": "그 주 전체 항목 수."},
            "completed_count": {"help_text": "완료 항목 수."},
            "progress_rate": {"help_text": "진행률 % (반올림)."},
            "generated_at": {"help_text": "리포트 생성 시각."},
        }

    def get_mvp(self, obj: WeeklyReport) -> dict | None:
        if not obj.mvp_name:
            return None
        return {
            "uid": str(obj.mvp_user.uid) if obj.mvp_user else None,
            "name": obj.mvp_name,
            "profile_image": obj.mvp_user.profile_image if obj.mvp_user else None,
            "point": obj.mvp_point,
            "completed_count": obj.mvp_completed_count,
        }


class WeeklyReportQuerySerializer(serializers.Serializer):
    """리포트 조회 쿼리 — `week_start` 생략 시 이번 주차."""

    week_start = serializers.DateField(
        required=False,
        help_text="조회할 주차의 월요일 날짜 (YYYY-MM-DD). 생략 시 이번 주차.",
    )

    def validate_week_start(self, value):
        if value.weekday() != 0:
            raise serializers.ValidationError("week_start 는 월요일 날짜여야 합니다.")
        return value

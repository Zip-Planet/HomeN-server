"""알림 입출력 스키마 (N1_NotificationInbox / T5_My 푸시 설정)."""

from rest_framework import serializers

from apps.notifications.models import Notification, NotificationCategory, NotificationSetting


class NotificationOutputSerializer(serializers.ModelSerializer):
    """알림 한 건 응답."""

    category_label = serializers.CharField(
        source="get_category_display", help_text="카테고리 한국어 표시."
    )
    is_read = serializers.SerializerMethodField(help_text="확인 여부. false 면 화면에서 강조 표시.")

    class Meta:
        model = Notification
        fields = [
            "id",
            "category",
            "category_label",
            "title",
            "body",
            "deep_link",
            "is_read",
            "created_at",
        ]
        extra_kwargs = {
            "id": {"help_text": "알림 PK."},
            "category": {"help_text": "home_member / assignment / board / reward / report."},
            "title": {"help_text": "알림 제목."},
            "body": {"help_text": "보조 문구."},
            "deep_link": {"help_text": "탭 시 이동할 목적지 문자열."},
            "created_at": {"help_text": "발생 시각."},
        }

    def get_is_read(self, obj: Notification) -> bool:
        return obj.read_at is not None


class NotificationQuerySerializer(serializers.Serializer):
    """알림 목록 조회 쿼리."""

    category = serializers.ChoiceField(
        choices=NotificationCategory.choices,
        required=False,
        help_text="카테고리 필터. 생략하면 전체.",
    )


class NotificationListOutputSerializer(serializers.Serializer):
    """알림함 응답 — 미확인 개수 + 목록."""

    unread_count = serializers.IntegerField(help_text="미확인 알림 개수 (헤더 벨 배지).")
    retention_days = serializers.IntegerField(help_text="알림 보관 기간(일). 화면 하단 안내 문구용.")
    notifications = NotificationOutputSerializer(
        many=True, help_text="알림 목록 (미확인 우선 > 최신순)."
    )


class NotificationSettingSerializer(serializers.ModelSerializer):
    """푸시 알림 설정 (마스터 토글 + 카테고리별 토글)."""

    class Meta:
        model = NotificationSetting
        fields = ["push_enabled", "home_member", "assignment", "board", "reward", "report"]
        extra_kwargs = {
            "push_enabled": {"help_text": "푸시 전체 on/off. 꺼지면 카테고리 값과 무관하게 발송 안 함."},
            "home_member": {"help_text": "집·구성원 알림 수신 여부."},
            "assignment": {"help_text": "분담안 알림 수신 여부."},
            "board": {"help_text": "보드 조율 알림 수신 여부."},
            "reward": {"help_text": "리워드 알림 수신 여부."},
            "report": {"help_text": "리포트 알림 수신 여부."},
        }


class AssignmentNudgeSerializer(serializers.Serializer):
    """분담안 생성 재촉 요청."""

    week_start = serializers.DateField(
        required=False,
        help_text="대상 주차의 월요일 날짜. 생략 시 이번 주차.",
    )

    def validate_week_start(self, value):
        if value.weekday() != 0:
            raise serializers.ValidationError("week_start 는 월요일 날짜여야 합니다.")
        return value

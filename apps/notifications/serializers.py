"""알림 입출력 스키마 (N1_NotificationInbox / T5_My 푸시 설정 / 푸시 기기 등록)."""

from rest_framework import serializers

from apps.notifications.models import Device, Notification, NotificationCategory, NotificationSetting


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


# ── 푸시 기기 등록 / 해제 / 테스트 발송 ───────────────────────────────────────


class DeviceRegisterSerializer(serializers.Serializer):
    """푸시 기기 등록 요청 (앱 시작마다 호출, 멱등)."""

    registration_id = serializers.CharField(
        max_length=255,
        help_text="Firebase Messaging SDK 가 돌려준 registration token 또는 FID.",
    )
    kind = serializers.ChoiceField(
        choices=Device.Kind.choices,
        default=Device.Kind.TOKEN,
        help_text="식별자 종류. `token`(기본) 또는 `fid`(Firebase Installation ID 모드를 켠 앱).",
    )
    platform = serializers.ChoiceField(
        choices=Device.Platform.choices,
        help_text="`ios` | `android`.",
    )
    app_version = serializers.CharField(
        max_length=32,
        required=False,
        allow_blank=True,
        default="",
        help_text="앱 버전 (디버깅용, 선택).",
    )


class DeviceOutputSerializer(serializers.ModelSerializer):
    """등록된 기기 응답."""

    class Meta:
        model = Device
        fields = ["registration_id", "kind", "platform", "app_version", "is_active", "last_seen_at"]
        extra_kwargs = {
            "registration_id": {"help_text": "등록된 식별자."},
            "kind": {"help_text": "`token` | `fid`."},
            "platform": {"help_text": "`ios` | `android`."},
            "app_version": {"help_text": "앱 버전."},
            "is_active": {"help_text": "발송 대상 여부."},
            "last_seen_at": {"help_text": "마지막 등록 시각."},
        }


class DeviceUnregisterSerializer(serializers.Serializer):
    """푸시 기기 해제 요청 (로그아웃 시)."""

    registration_id = serializers.CharField(max_length=255, help_text="해제할 식별자.")


class PushTestSerializer(serializers.Serializer):
    """본인 기기 테스트 푸시 요청."""

    title = serializers.CharField(max_length=100, default="HomeN 테스트 알림", help_text="알림 제목.")
    body = serializers.CharField(
        max_length=200, default="푸시 설정이 정상적으로 동작하고 있어요.", help_text="알림 본문."
    )
    dry_run = serializers.BooleanField(
        default=False, help_text="true 면 실제 전달 없이 FCM 검증만 수행한다 (식별자 유효성 확인용)."
    )


class PushResultSerializer(serializers.Serializer):
    """푸시 발송 결과 집계."""

    sent = serializers.IntegerField(help_text="성공 수.")
    failed = serializers.IntegerField(help_text="실패 수.")
    deactivated = serializers.IntegerField(help_text="실패 중 식별자가 무효해 비활성화한 기기 수.")

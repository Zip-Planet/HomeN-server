"""보드 입출력 스키마 (T2_FairBoard / Q1 / Q2)."""

from rest_framework import serializers


class BoardItemSummarySerializer(serializers.Serializer):
    """카드에 붙는 대상 집안일 요약."""

    id = serializers.IntegerField(help_text="분담안 항목 PK.")
    chore_name = serializers.CharField(help_text="집안일명 (생성 시점 스냅샷).")
    weekday = serializers.IntegerField(help_text="실행 요일 (0=월 ~ 6=일).")
    weekday_label = serializers.CharField(help_text="요일 한글 라벨.")
    difficulty = serializers.IntegerField(help_text="난이도 enum (스냅샷).")
    point = serializers.IntegerField(help_text="포인트 (스냅샷).")
    date = serializers.DateField(help_text="실행 날짜.")
    assignee = serializers.DictField(allow_null=True, help_text="현재 담당자 {uid, name, profile_image}.")


class BoardSelectableItemSerializer(BoardItemSummarySerializer):
    """조율 카드 생성 화면의 선택 가능 항목."""

    is_requested = serializers.BooleanField(
        help_text="이미 대기 중인 조율 카드가 걸린 항목이면 true (선택 불가 표시)."
    )


class BoardCardSerializer(serializers.Serializer):
    """보드 피드 카드 한 건 (봇/도움/교환 공통 표현).

    `type` 으로 종류를 구분한다.
    - `bot`: `kind`(4종) + `payload` 스냅샷.
    - `help`: `status`, `requester`, `accepted_by`, `item`.
    - `swap`: `status`, `requester`, `responded_by`, `requester_item`, `target_item`.
    """

    type = serializers.CharField(help_text="bot / help / swap.")
    id = serializers.IntegerField(help_text="카드 PK (종류별 독립).")
    week_start = serializers.DateField(help_text="카드가 속한 주차의 월요일 (주차 구분선 기준).")
    created_at = serializers.DateTimeField(help_text="발행 시각.")

    kind = serializers.CharField(required=False, help_text="봇 카드 종류 (type=bot).")
    kind_label = serializers.CharField(required=False, help_text="봇 카드 종류 한국어.")
    payload = serializers.DictField(required=False, help_text="봇 카드 문구용 스냅샷.")

    status = serializers.CharField(required=False, help_text="pending / accepted / rejected / expired.")
    message = serializers.CharField(required=False, allow_blank=True, help_text="작성 메시지 (최대 30자).")
    requester = serializers.DictField(required=False, allow_null=True, help_text="요청자.")
    accepted_by = serializers.DictField(required=False, allow_null=True, help_text="도움 수락자.")
    responded_by = serializers.DictField(required=False, allow_null=True, help_text="교환 응답자.")
    item = BoardItemSummarySerializer(required=False, help_text="도움 요청 대상 항목.")
    requester_item = BoardItemSummarySerializer(required=False, help_text="교환 — 요청자 항목.")
    target_item = BoardItemSummarySerializer(required=False, help_text="교환 — 상대 항목.")


class BoardFeedOutputSerializer(serializers.Serializer):
    """보드 피드 응답."""

    cards = BoardCardSerializer(many=True, help_text="봇/조율 카드 병합 목록 (최신순).")


class HelpRequestCreateSerializer(serializers.Serializer):
    """도움 요청 생성."""

    item_id = serializers.IntegerField(help_text="도움 받을 분담안 항목 PK (본인 담당).")
    message = serializers.CharField(
        max_length=30, required=False, allow_blank=True, default="", help_text="메시지 (선택, 최대 30자)."
    )


class SwapRequestCreateSerializer(serializers.Serializer):
    """교환 요청 생성."""

    requester_item_id = serializers.IntegerField(help_text="내가 넘길 항목 PK (본인 담당).")
    target_item_id = serializers.IntegerField(help_text="내가 대신할 상대 항목 PK.")
    message = serializers.CharField(
        max_length=30, required=False, allow_blank=True, default="", help_text="메시지 (선택, 최대 30자)."
    )


class BoardItemQuerySerializer(serializers.Serializer):
    """조율 대상 항목 조회 쿼리."""

    week_start = serializers.DateField(
        required=False, help_text="대상 주차의 월요일. 생략 시 이번 주차."
    )
    assignee = serializers.CharField(
        required=False, help_text="담당자 필터 — `me` 또는 구성원 uid. 생략 시 전체."
    )

    def validate_week_start(self, value):
        if value.weekday() != 0:
            raise serializers.ValidationError("week_start 는 월요일 날짜여야 합니다.")
        return value

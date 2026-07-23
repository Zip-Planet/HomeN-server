from django.db import models

from apps.homes.models import AssignmentItem, Home
from apps.users.models import User


class BotCardKind(models.TextChoices):
    """페어봇 시스템 카드 4종 (Figma T2_FairBoard)."""

    ASSIGNMENT_CREATED = "assignment_created", "분담안 제안"
    ASSIGNMENT_CONFIRMED = "assignment_confirmed", "분담안 확정"
    WEEKLY_REPORT = "weekly_report", "주간 리포트"
    REWARD_ACHIEVED = "reward_achieved", "리워드 달성"


class RequestStatus(models.TextChoices):
    """조율 카드(도움/교환) 상태."""

    PENDING = "pending", "대기"
    ACCEPTED = "accepted", "수락됨"
    REJECTED = "rejected", "거절됨"
    EXPIRED = "expired", "만료됨"


class BotCard(models.Model):
    """봇이 발행하는 시스템 카드.

    본문 수치(총 집안일 수, MVP, 완료율 등)는 발행 시점 스냅샷을 `payload` 에
    담는다 — 나중에 분담안이 바뀌어도 과거 카드 문구가 흔들리면 안 된다.

    Attributes:
        home: 대상 집.
        kind: 카드 종류 (봇 카드 4종).
        week_start: 카드가 가리키는 주차의 월요일 (피드의 주차 구분선 기준).
        payload: 화면 문구용 스냅샷 (예: {"total_count": 25, "mvp_name": "..."}).
        created_at: 발행 시각.
    """

    home = models.ForeignKey(Home, on_delete=models.CASCADE, related_name="bot_cards")
    kind = models.CharField(max_length=30, choices=BotCardKind.choices)
    week_start = models.DateField()
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "board_bot_cards"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["home", "kind", "week_start"],
                name="uniq_bot_card_per_home_kind_week",
            ),
        ]

    def __str__(self) -> str:
        return f"bot_card:{self.pk}:{self.kind}"


class HelpRequest(models.Model):
    """도움 요청 카드 — "내 집안일을 대신해 줄 사람?".

    수락되면 대상 항목의 담당자가 수락자로 바뀐다. 아무도 수락하지 않으면
    **대상 집안일 날짜의 다음 날 23:59** 에 자동 만료된다.

    Attributes:
        home: 대상 집.
        item: 대상 분담안 항목 (원본 삭제 시 카드도 함께 삭제).
        requester: 요청자 (= 요청 시점 담당자).
        message: 메시지 (선택, 최대 30자 — 화면 카운터 0/30).
        status: pending / accepted / expired.
        accepted_by: 수락자 (탈퇴 시 NULL).
        resolved_at: 수락·만료 시각.
    """

    home = models.ForeignKey(Home, on_delete=models.CASCADE, related_name="help_requests")
    item = models.ForeignKey(AssignmentItem, on_delete=models.CASCADE, related_name="help_requests")
    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name="help_requests")
    message = models.CharField(max_length=30, blank=True, default="")
    status = models.CharField(max_length=10, choices=RequestStatus.choices, default=RequestStatus.PENDING)
    accepted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_help_requests",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "board_help_requests"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["item"],
                condition=models.Q(status="pending"),
                name="uniq_pending_help_request_per_item",
            ),
        ]

    def __str__(self) -> str:
        return f"help_request:{self.pk}:{self.status}"


class SwapRequest(models.Model):
    """교환 요청 카드 — 내 집안일과 상대 집안일의 담당자를 맞바꾼다.

    수락되면 두 항목의 담당자가 서로 교환된다. 거절하면 "아쉽지만 다음에
    교환해요" 카드로 남고, 응답이 없으면 **더 이른 쪽 집안일 날짜의 다음 날
    23:59** 에 만료된다.

    Attributes:
        home: 대상 집.
        requester_item / target_item: 교환할 두 항목.
        requester: 요청자 (= `requester_item` 의 담당자).
        message: 메시지 (선택, 최대 30자).
        status: pending / accepted / rejected / expired.
        responded_by: 수락·거절한 유저 (탈퇴 시 NULL).
        resolved_at: 응답·만료 시각.
    """

    home = models.ForeignKey(Home, on_delete=models.CASCADE, related_name="swap_requests")
    requester_item = models.ForeignKey(
        AssignmentItem, on_delete=models.CASCADE, related_name="swap_requests_as_source"
    )
    target_item = models.ForeignKey(
        AssignmentItem, on_delete=models.CASCADE, related_name="swap_requests_as_target"
    )
    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name="swap_requests")
    message = models.CharField(max_length=30, blank=True, default="")
    status = models.CharField(max_length=10, choices=RequestStatus.choices, default=RequestStatus.PENDING)
    responded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="responded_swap_requests",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "board_swap_requests"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["requester_item"],
                condition=models.Q(status="pending"),
                name="uniq_pending_swap_request_per_item",
            ),
        ]

    def __str__(self) -> str:
        return f"swap_request:{self.pk}:{self.status}"

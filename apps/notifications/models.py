from django.db import models

from apps.homes.models import Home
from apps.users.models import User


class NotificationCategory(models.TextChoices):
    """알림 카테고리 — 알림함 필터와 푸시 설정 토글이 같은 분류를 쓴다.

    Figma N1_NotificationInbox 의 드롭다운: 전체 / 집·구성원 / 분담안 / 보드 조율 /
    리워드 / 리포트. `전체` 는 필터 값일 뿐 저장되는 카테고리가 아니다.
    """

    HOME_MEMBER = "home_member", "집·구성원"
    ASSIGNMENT = "assignment", "분담안"
    BOARD = "board", "보드 조율"
    REWARD = "reward", "리워드"
    REPORT = "report", "리포트"


class Notification(models.Model):
    """인앱 알림 한 건.

    알림은 **발생 7일 후 삭제**된다 (화면 하단 "7일 전 알림까지 확인 가능해요").
    정렬은 미확인 우선 > 최신순이다.

    `deep_link` 는 알림 탭 시 이동할 목적지를 앱이 해석할 수 있는 문자열이며,
    대상 주차가 지났거나 이미 처리된 카드처럼 랜딩할 수 없는 경우 앱이 만료
    토스트를 대신 노출한다.

    Attributes:
        home: 알림이 발생한 집.
        recipient: 수신자 (탈퇴 시 알림도 함께 삭제).
        category: 알림 카테고리.
        title: 알림 제목 (예: "다음 주 분담안이 생성됐어요").
        body: 보조 문구.
        deep_link: 이동 목적지 (예: "assignment:2026-02-02").
        read_at: 확인 시각. null 이면 미확인.
        created_at: 발생 시각.
    """

    home = models.ForeignKey(Home, on_delete=models.CASCADE, related_name="notifications")
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    category = models.CharField(max_length=20, choices=NotificationCategory.choices)
    title = models.CharField(max_length=100)
    body = models.CharField(max_length=200, blank=True, default="")
    deep_link = models.CharField(max_length=200, blank=True, default="")
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["recipient", "created_at"])]

    def __str__(self) -> str:
        return f"notification:{self.pk}:{self.category}"


class NotificationSetting(models.Model):
    """유저별 푸시 알림 설정 (T5_My).

    마스터 토글(`push_enabled`) 하나와 카테고리별 토글 5개로 구성된다.
    마스터가 꺼져 있으면 카테고리 값과 무관하게 모두 발송하지 않는다.

    Attributes:
        user: 대상 유저 (1:1).
        push_enabled: 푸시 전체 on/off.
        home_member / assignment / board / reward / report: 카테고리별 on/off.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="notification_setting")
    push_enabled = models.BooleanField(default=True)
    home_member = models.BooleanField(default=True)
    assignment = models.BooleanField(default=True)
    board = models.BooleanField(default=True)
    reward = models.BooleanField(default=True)
    report = models.BooleanField(default=True)

    class Meta:
        db_table = "notification_settings"

    def __str__(self) -> str:
        return f"notification_setting:{self.pk}"

    def allows(self, category: str) -> bool:
        """해당 카테고리 푸시가 허용되는지 여부 (마스터 토글 우선)."""
        return self.push_enabled and bool(getattr(self, category, True))

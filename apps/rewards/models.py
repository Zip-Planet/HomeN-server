from django.db import models

from apps.homes.models import Home
from apps.users.models import User


class Reward(models.Model):
    """리워드 — 집 구성원이 포인트를 모아 교환하는 보상.

    최종 디자인(W2_RewardCreateEdit)의 입력은 **이름 + 목표 포인트** 두 가지다.
    수령은 집당 1회로, 한 번 수령되면 `claim` 이 생기고 잠긴다.

    본 모델은 원래 `apps.homes` 에 있었고 테이블명(`rewards`) 을 그대로 유지한
    채 앱만 이동했다 (state-only 마이그레이션 — 데이터 이관 없음).

    Attributes:
        home: 소속 집.
        name: 리워드 이름 (컬럼은 50자. 화면 카운터는 0/20 이라 입력 검증은
            시리얼라이저에서 20자로 제한한다).
        goal_point: 목표 포인트.
        created_by: 등록한 유저 (탈퇴 시 NULL).
        created_at / updated_at: 생성·수정 일시.
    """

    home = models.ForeignKey(Home, on_delete=models.CASCADE, related_name="rewards")
    name = models.CharField(max_length=50)
    goal_point = models.PositiveIntegerField()
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_rewards",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rewards"

    def __str__(self) -> str:
        return f"reward:{self.pk}:{self.name}"


class RewardClaim(models.Model):
    """리워드 수령 이력 — 리워드당 최대 1건.

    수령 시점의 목표 포인트를 스냅샷으로 남긴다 (`claimed_point`). 이후 리워드가
    수정돼도 "얼마를 쓰고 받았는지" 가 흔들리지 않아야 하기 때문이다.
    수령자가 탈퇴해도 이력은 보존한다 (`SET_NULL`).

    Attributes:
        reward: 대상 리워드 (1:1 — 집당 1회 수령).
        claimed_by: 수령한 User (탈퇴 시 NULL).
        claimed_point: 수령 시점 목표 포인트 스냅샷 (차감 포인트).
        claimed_at: 수령 일시.
    """

    reward = models.OneToOneField(Reward, on_delete=models.CASCADE, related_name="claim")
    claimed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reward_claims",
    )
    claimed_point = models.PositiveIntegerField()
    claimed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reward_claims"

    def __str__(self) -> str:
        return f"reward_claim:{self.pk}"

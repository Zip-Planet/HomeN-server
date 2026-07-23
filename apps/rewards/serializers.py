"""리워드 입출력 스키마.

화면 매핑:
- `T4_RewardMain` (목록) — 헤더의 내 포인트/상태별 개수, 항목별 상태 배지.
- `W1_RewardDetail` (상세) — 목표 대비 내 달성률, 구성원 현황 랭킹, 상태별 CTA.
- `W2_RewardCreateEdit` (등록/수정) — 입력은 이름(0/20) + 목표 포인트 뿐이다.
"""

from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers

from apps.rewards.models import Reward


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "리워드 등록",
            value={"name": "저녁 더치페이 1회 면제권", "goal_point": 1600},
            request_only=True,
        ),
    ]
)
class RewardCreateSerializer(serializers.Serializer):
    """리워드 등록 요청. 화면 입력은 이름과 목표 포인트 두 가지뿐이다."""

    name = serializers.CharField(max_length=20, help_text="리워드 이름 (최대 20자).")
    goal_point = serializers.IntegerField(min_value=1, help_text="목표 포인트 (1 이상).")


class RewardUpdateSerializer(serializers.Serializer):
    """리워드 수정 요청 (PATCH — 부분 수정). 전달된 키만 반영된다."""

    name = serializers.CharField(max_length=20, required=False, help_text="리워드 이름 (최대 20자).")
    goal_point = serializers.IntegerField(min_value=1, required=False, help_text="목표 포인트 (1 이상).")


class RewardMemberProgressSerializer(serializers.Serializer):
    """리워드 상세의 구성원 현황 한 줄."""

    rank = serializers.IntegerField(help_text="보유 포인트 기준 순위 (1등부터).")
    uid = serializers.CharField(help_text="유저 uid.")
    name = serializers.CharField(help_text="닉네임.")
    profile_image = serializers.IntegerField(allow_null=True, help_text="프로필 이미지 enum.")
    point = serializers.IntegerField(help_text="보유 포인트 잔액.")
    achievement_rate = serializers.IntegerField(help_text="목표 대비 달성률 % (최대 100).")


class RewardClaimOutputSerializer(serializers.Serializer):
    """수령 이력 응답."""

    claimed_by = serializers.DictField(allow_null=True, help_text="수령자 {uid, name, profile_image}.")
    claimed_point = serializers.IntegerField(help_text="수령 시점 목표 포인트 스냅샷.")
    claimed_at = serializers.DateTimeField(help_text="수령 일시.")


class RewardOutputSerializer(serializers.ModelSerializer):
    """리워드 목록/단건 응답.

    `status` 는 저장값이 아니라 요청 유저 기준 파생값이다:
    `claimed`(수령 완료) / `claimable`(받기 가능) / `in_progress`(진행 중).
    `remaining_point` 는 목표까지 남은 포인트로, 받기 가능/수령 완료면 0이다.
    """

    status = serializers.SerializerMethodField(
        help_text="claimed / claimable / in_progress — 요청 유저 기준 파생 상태.",
    )
    remaining_point = serializers.SerializerMethodField(
        help_text="목표까지 남은 포인트 (요청 유저 기준). 달성했으면 0.",
    )
    created_by = serializers.SerializerMethodField(
        help_text="등록자 {uid, name, profile_image}. 탈퇴 시 null.",
    )
    claim = serializers.SerializerMethodField(
        help_text="수령 이력. 미수령이면 null.",
    )

    class Meta:
        model = Reward
        fields = [
            "id",
            "name",
            "goal_point",
            "status",
            "remaining_point",
            "created_by",
            "claim",
            "created_at",
        ]
        extra_kwargs = {
            "id": {"help_text": "리워드 PK."},
            "name": {"help_text": "리워드 이름."},
            "goal_point": {"help_text": "목표 포인트."},
            "created_at": {"help_text": "등록 일시."},
        }

    def _balance(self) -> int:
        return self.context.get("balance", 0)

    def get_status(self, obj: Reward) -> str:
        if getattr(obj, "claim", None) is not None:
            return "claimed"
        return "claimable" if self._balance() >= obj.goal_point else "in_progress"

    def get_remaining_point(self, obj: Reward) -> int:
        return max(obj.goal_point - self._balance(), 0)

    def get_created_by(self, obj: Reward) -> dict | None:
        if obj.created_by is None:
            return None
        return {
            "uid": str(obj.created_by.uid),
            "name": obj.created_by.name,
            "profile_image": obj.created_by.profile_image,
        }

    def get_claim(self, obj: Reward) -> dict | None:
        claim = getattr(obj, "claim", None)
        if claim is None:
            return None
        claimed_by = None
        if claim.claimed_by is not None:
            claimed_by = {
                "uid": str(claim.claimed_by.uid),
                "name": claim.claimed_by.name,
                "profile_image": claim.claimed_by.profile_image,
            }
        return {
            "claimed_by": claimed_by,
            "claimed_point": claim.claimed_point,
            "claimed_at": claim.claimed_at,
        }


class RewardDetailOutputSerializer(RewardOutputSerializer):
    """리워드 상세 응답 — 목록 응답 + 구성원 현황 랭킹."""

    member_progress = serializers.SerializerMethodField(
        help_text="구성원별 보유 포인트·달성률·순위 (보유 포인트 내림차순).",
    )

    class Meta(RewardOutputSerializer.Meta):
        fields = RewardOutputSerializer.Meta.fields + ["member_progress"]

    def get_member_progress(self, obj: Reward) -> list[dict]:
        return self.context.get("member_progress", [])


class RewardListOutputSerializer(serializers.Serializer):
    """리워드 탭 응답 — 헤더 요약 + 목록."""

    my_point = serializers.IntegerField(help_text="내 리워드 포인트 잔액.")
    claimable_count = serializers.IntegerField(help_text="받기 가능 개수.")
    in_progress_count = serializers.IntegerField(help_text="진행 중 개수.")
    claimed_count = serializers.IntegerField(help_text="받기 완료 개수.")
    rewards = RewardOutputSerializer(many=True, help_text="리워드 목록 (받기 가능 > 진행 중 > 완료 순).")

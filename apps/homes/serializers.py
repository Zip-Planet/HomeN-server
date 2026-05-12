"""홈(집) / 집안일 / 스타터팩 컨텍스트 시리얼라이저.

본 모듈은 다음 흐름의 입출력 스키마를 모아둔다.

- **집 생성·조회·삭제** : `/api/v1/homes/`, `/api/v1/homes/mine/`
- **초대 / 참여 / 나가기** : `/api/v1/homes/invite/{code}/`, `/api/v1/homes/join/`,
  `/api/v1/homes/mine/leave/`
- **관리자 양도** : `/api/v1/homes/mine/transfer-admin/`
- **집안일** : `/api/v1/homes/mine/chores/`, `/api/v1/homes/mine/chores/{id}/`
- **스타터팩 (프리셋)** : `/api/v1/starter-packs/`

도메인 규칙(서비스 레이어에서 강제) 요약:

- 한 유저는 단 하나의 집에만 속한다 (`HomeMember.unique_together(home, user)` 추가).
- 집당 관리자는 1명. 관리자만 집 삭제·집안일 생성·양도가 가능하다.
- 집 삭제는 구성원이 없을 때만, 관리자 본인의 집 탈퇴는 양도 후에만 가능.
"""

import re

from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers

from apps.homes.models import Chore, ChoreCategory, Home, HomeChore, HomeMember, HomeImageType, Reward, StarterPack


# ── 집 생성 ──────────────────────────────────────────────────────────────────


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "집 + 집안일 + 리워드",
            summary="생성 시 집안일·리워드를 함께 등록하는 전형적 케이스",
            value={
                "name": "우리집",
                "image_id": 1,
                "chores": [
                    {
                        "category": 3,
                        "name": "거실 청소",
                        "description": "주 1회",
                        "repeat_days": [0, 3],
                        "difficulty": 2,
                    }
                ],
                "rewards": [{"name": "치킨 한 마리", "goal_point": 50}],
            },
            request_only=True,
        ),
        OpenApiExample(
            "집만 생성",
            summary="집안일·리워드는 나중에 추가하는 케이스",
            value={"name": "우리집", "image_id": 2, "chores": [], "rewards": []},
            request_only=True,
        ),
    ]
)
class HomeCreateSerializer(serializers.Serializer):
    """집 생성 요청.

    `chores` 와 `rewards` 는 선택값이며 빈 리스트로 보내면 집만 생성한다.
    내부 nested 시리얼라이저는 본 시리얼라이저 안에서만 사용된다.
    """

    class ChoreInputSerializer(serializers.Serializer):
        """집 생성 시 함께 등록할 집안일 한 건."""

        category = serializers.ChoiceField(
            choices=ChoreCategory.choices,
            help_text="집안일 카테고리 (1=쓰레기, 2=욕실, 3=청소, 4=주방, 5=세탁).",
        )
        name = serializers.CharField(max_length=20, help_text="집안일 제목 (1~20자).")
        description = serializers.CharField(
            max_length=20,
            default="",
            allow_blank=True,
            help_text="집안일 설명 (선택, 최대 20자).",
        )
        repeat_days = serializers.ListField(
            child=serializers.ChoiceField(choices=Chore.Weekday.choices),
            default=list,
            help_text="반복 요일 정수 목록 (0=월 ~ 6=일). 비반복이면 빈 배열.",
        )
        difficulty = serializers.ChoiceField(
            choices=Chore.Difficulty.choices,
            help_text="난이도 (1=하, 2=중하, 3=중, 4=중상, 5=상).",
        )

    class RewardInputSerializer(serializers.Serializer):
        """집 생성 시 함께 등록할 리워드 한 건."""

        name = serializers.CharField(max_length=50, help_text="리워드 이름 (최대 50자).")
        goal_point = serializers.IntegerField(min_value=1, help_text="목표 포인트 (1 이상).")

    name = serializers.CharField(
        max_length=10,
        help_text="집 이름. 한글·영문·숫자·공백, 최대 10자. 공백 단독 불가.",
    )
    image_id = serializers.ChoiceField(
        choices=HomeImageType.choices,
        help_text="집 이미지 enum 값 (1~8). `/homes/images/` 의 응답 중 하나.",
    )
    chores = ChoreInputSerializer(many=True, default=list, help_text="함께 등록할 집안일 목록 (선택).")
    rewards = RewardInputSerializer(many=True, default=list, help_text="함께 등록할 리워드 목록 (선택).")

    def validate_name(self, value: str) -> str:
        """집 이름 규칙: 한글·영문·숫자·공백만 허용, 공백 단독 불가."""
        if not re.match(r"^[가-힣a-zA-Z0-9 ]+$", value):
            raise serializers.ValidationError("집 이름은 한글, 영문, 숫자, 띄어쓰기만 사용할 수 있습니다.")
        if value.strip() == "":
            raise serializers.ValidationError("집 이름을 입력해 주세요.")
        return value


# ── 집 조회 / 응답 ────────────────────────────────────────────────────────────


class HomeMemberSerializer(serializers.ModelSerializer):
    """집 구성원 한 건의 응답.

    `HomeOutputSerializer.members` 와 `HomeInviteDetailSerializer.members` 내부에서
    재사용된다.
    """

    name = serializers.CharField(source="user.name", help_text="구성원 닉네임.")
    profile_image = serializers.IntegerField(
        source="user.profile_image",
        allow_null=True,
        help_text="프로필 이미지 enum 값 (미설정 시 null).",
    )
    role_label = serializers.SerializerMethodField(help_text="역할 한국어 표시 (예: '관리자', '구성원').")

    class Meta:
        model = HomeMember
        fields = ["name", "profile_image", "role", "role_label"]

    def get_role_label(self, obj: HomeMember) -> str:
        return obj.get_role_display()


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "관리자 본인 + 구성원 1명",
            value={
                "id": 12,
                "name": "우리집",
                "image": 1,
                "invite_code": "AB12CD",
                "status": "active",
                "created_at": "2026-05-12T12:00:00Z",
                "members": [
                    {"name": "홍길동", "profile_image": 3, "role": 1, "role_label": "관리자"},
                    {"name": "김철수", "profile_image": 2, "role": 2, "role_label": "구성원"},
                ],
            },
            response_only=True,
        )
    ]
)
class HomeOutputSerializer(serializers.ModelSerializer):
    """집 단건 응답.

    `members` 는 관리자 포함 전체 구성원 목록이다.
    """

    members = HomeMemberSerializer(
        many=True,
        read_only=True,
        help_text="구성원 목록 (관리자 포함).",
    )

    class Meta:
        model = Home
        fields = ["id", "name", "image", "invite_code", "status", "created_at", "members"]
        extra_kwargs = {
            "id": {"help_text": "집 PK."},
            "name": {"help_text": "집 이름."},
            "image": {"help_text": "집 이미지 enum (1~8)."},
            "invite_code": {"help_text": "6자리 대문자+숫자 초대코드."},
            "status": {"help_text": "집 상태 (`active`=활성, `draft`=생성 중)."},
            "created_at": {"help_text": "집 생성 일시 (ISO 8601)."},
        }


# ── 스타터팩 / 집안일 ──────────────────────────────────────────────────────────


class StarterPackSerializer(serializers.ModelSerializer):
    """스타터팩 메타 응답.

    `/api/v1/starter-packs/` 가 반환하는 목록 원소. 실제 집안일 리스트는
    `/starter-packs/{id}/chores/` 로 별도 호출한다.
    """

    class Meta:
        model = StarterPack
        fields = ["id", "name", "description"]
        extra_kwargs = {
            "id": {"help_text": "스타터팩 PK."},
            "name": {"help_text": "스타터팩 이름."},
            "description": {"help_text": "스타터팩 설명 (없으면 빈 문자열)."},
        }


class ChoreOutputSerializer(serializers.ModelSerializer):
    """집안일 마스터(`Chore`) 응답.

    스타터팩 미리보기 등 `HomeChore` 가 아직 만들어지지 않은 시점에 사용된다.
    """

    difficulty_label = serializers.CharField(
        source="get_difficulty_display",
        read_only=True,
        help_text="난이도 한국어 표시 (예: '중', '상').",
    )
    category_label = serializers.CharField(
        source="get_category_display",
        read_only=True,
        help_text="카테고리 한국어 표시 (예: '청소', '주방').",
    )

    class Meta:
        model = Chore
        fields = [
            "id",
            "category",
            "category_label",
            "name",
            "description",
            "repeat_days",
            "difficulty",
            "difficulty_label",
        ]
        extra_kwargs = {
            "id": {"help_text": "집안일 마스터 PK."},
            "category": {"help_text": "카테고리 enum 정수 (1~5)."},
            "name": {"help_text": "집안일 제목."},
            "description": {"help_text": "집안일 설명 (없으면 빈 문자열)."},
            "repeat_days": {"help_text": "반복 요일 정수 배열 (0=월 ~ 6=일)."},
            "difficulty": {"help_text": "난이도 enum 정수 (1=하 ~ 5=상)."},
        }


class RewardOutputSerializer(serializers.ModelSerializer):
    """리워드 응답."""

    class Meta:
        model = Reward
        fields = ["id", "name", "goal_point"]
        extra_kwargs = {
            "id": {"help_text": "리워드 PK."},
            "name": {"help_text": "리워드 이름."},
            "goal_point": {"help_text": "달성 목표 포인트."},
        }


class ImageIdSerializer(serializers.Serializer):
    """선택 가능한 집 이미지 enum 한 건.

    `/api/v1/homes/images/` 의 응답 배열 원소. FE 는 이 값을 그대로
    `HomeCreate.image_id` 로 전송한다.
    """

    id = serializers.IntegerField(help_text="집 이미지 enum ID (1~8).")


# ── 집 참여 ──────────────────────────────────────────────────────────────────


@extend_schema_serializer(
    examples=[
        OpenApiExample("초대코드로 참여", value={"invite_code": "AB12CD"}, request_only=True),
    ]
)
class HomeJoinSerializer(serializers.Serializer):
    """집 참여 요청.

    이미 집에 속한 유저가 호출하면 400 (`already_has_home`) — 먼저 나가야 한다.
    유효하지 않은 초대코드는 404.
    """

    invite_code = serializers.CharField(
        max_length=6,
        help_text="6자리 대문자+숫자 초대코드 (예: 'AB12CD').",
    )


# ── 관리자 양도 ──────────────────────────────────────────────────────────────


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "같은 집 구성원에게 양도",
            value={"user_id": "8f3e2b1a-1234-4abc-9def-1234567890ab"},
            request_only=True,
        ),
    ]
)
class TransferAdminSerializer(serializers.Serializer):
    """관리자 양도 요청.

    대상은 반드시 **같은 집의 구성원** 이어야 한다 (서비스 레이어에서 검증, 위반 시 400).
    """

    user_id = serializers.UUIDField(
        help_text="양도받을 대상 유저의 `uid` (UUID). 반드시 같은 집의 구성원.",
    )


# ── 집안일 생성 / 수정 ────────────────────────────────────────────────────────


class HomeChoreCreateSerializer(serializers.Serializer):
    """집안일 생성 요청 한 건.

    `HomeChoreListCreateSerializer` 안에서 단건/복수 공통으로 재사용된다.
    """

    category = serializers.ChoiceField(
        choices=ChoreCategory.choices,
        help_text="카테고리 enum (1=쓰레기 ~ 5=세탁).",
    )
    name = serializers.CharField(max_length=20, help_text="집안일 제목 (1~20자).")
    description = serializers.CharField(
        max_length=20,
        default="",
        allow_blank=True,
        help_text="집안일 설명 (선택, 최대 20자).",
    )
    repeat_days = serializers.ListField(
        child=serializers.ChoiceField(choices=Chore.Weekday.choices),
        default=list,
        help_text="반복 요일 정수 배열 (0=월 ~ 6=일). 비반복이면 빈 배열.",
    )
    difficulty = serializers.ChoiceField(
        choices=Chore.Difficulty.choices,
        help_text="난이도 enum (1=하 ~ 5=상).",
    )


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "복수 등록",
            value={
                "chores": [
                    {
                        "category": 3,
                        "name": "현관 청소",
                        "description": "",
                        "repeat_days": [5, 6],
                        "difficulty": 1,
                    },
                    {
                        "category": 4,
                        "name": "설거지",
                        "description": "식후 즉시",
                        "repeat_days": [0, 1, 2, 3, 4, 5, 6],
                        "difficulty": 2,
                    },
                ]
            },
            request_only=True,
        )
    ]
)
class HomeChoreListCreateSerializer(serializers.Serializer):
    """집안일 리스트 생성 요청.

    단건 등록도 길이 1 의 `chores` 배열로 보낸다 — 응답은 동일하게 배열.
    """

    chores = HomeChoreCreateSerializer(many=True, help_text="추가할 집안일 목록.")


class HomeChoreOutputSerializer(serializers.ModelSerializer):
    """집에 배정된 집안일(`HomeChore`) 응답.

    `Chore` 의 마스터 정보(이름/카테고리 등)와 `HomeChore` 의 인스턴스 정보(`memo`,
    PK 등)를 평탄화해 한 객체로 응답한다.
    """

    category = serializers.IntegerField(source="chore.category", help_text="카테고리 enum 정수.")
    category_label = serializers.CharField(source="chore.get_category_display", help_text="카테고리 한국어.")
    name = serializers.CharField(source="chore.name", help_text="집안일 제목.")
    description = serializers.CharField(source="chore.description", help_text="집안일 설명.")
    repeat_days = serializers.ListField(source="chore.repeat_days", help_text="반복 요일 정수 배열.")
    difficulty = serializers.IntegerField(source="chore.difficulty", help_text="난이도 enum 정수.")
    difficulty_label = serializers.CharField(source="chore.get_difficulty_display", help_text="난이도 한국어.")

    class Meta:
        model = HomeChore
        fields = [
            "id",
            "category",
            "category_label",
            "name",
            "description",
            "repeat_days",
            "difficulty",
            "difficulty_label",
            "memo",
        ]
        extra_kwargs = {
            "id": {"help_text": "HomeChore PK — 메모 수정 등에 사용."},
            "memo": {"help_text": "집안일 인스턴스 단위 메모 (최대 200자, 빈 문자열 가능)."},
        }


@extend_schema_serializer(
    examples=[
        OpenApiExample("메모 입력", value={"memo": "주방 세제 떨어짐 — 사 와야 함"}, request_only=True),
        OpenApiExample("메모 비우기", value={"memo": ""}, request_only=True),
    ]
)
class ChoreMemoUpdateSerializer(serializers.Serializer):
    """집안일 메모 수정 요청."""

    memo = serializers.CharField(
        max_length=200,
        allow_blank=True,
        help_text="새 메모 (최대 200자). 빈 문자열을 보내면 메모를 비운다.",
    )


# ── 멤버십 / 초대 미리보기 ───────────────────────────────────────────────────


class HomeMembershipSerializer(serializers.Serializer):
    """집 소속 여부 응답.

    소속 집이 없어도 200 + `{ "has_home": false }` 를 돌려준다 (404 가 아님).
    """

    has_home = serializers.BooleanField(
        help_text="현재 유저가 집 관리자 또는 구성원인지 여부.",
    )


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "초대코드 미리보기",
            value={
                "invite_code": "AB12CD",
                "name": "우리집",
                "image": 1,
                "member_count": 2,
                "created_at": "2026-05-12T12:00:00Z",
                "members": [
                    {"name": "홍길동", "profile_image": 3, "role": 1, "role_label": "관리자"},
                    {"name": "김철수", "profile_image": 2, "role": 2, "role_label": "구성원"},
                ],
            },
            response_only=True,
        )
    ]
)
class HomeInviteDetailSerializer(serializers.ModelSerializer):
    """초대코드로 조회한 집 미리보기.

    참여 확정 전에 FE 가 보여줄 정보 — 집 이름/이미지/구성원 수 등을 노출한다.
    `invite_code` 는 검색에 쓰인 코드 그대로 에코백된다.
    """

    member_count = serializers.SerializerMethodField(help_text="전체 구성원 수(관리자 포함).")
    members = serializers.SerializerMethodField(help_text="구성원 목록(관리자 포함).")

    class Meta:
        model = Home
        fields = ["invite_code", "name", "image", "member_count", "created_at", "members"]
        extra_kwargs = {
            "invite_code": {"help_text": "조회에 사용된 초대코드."},
            "name": {"help_text": "집 이름."},
            "image": {"help_text": "집 이미지 enum (1~8)."},
            "created_at": {"help_text": "집 생성 일시 (ISO 8601)."},
        }

    def get_member_count(self, obj: Home) -> int:
        return obj.members.count()

    def get_members(self, obj: Home) -> list:
        return HomeMemberSerializer(obj.members.all(), many=True).data

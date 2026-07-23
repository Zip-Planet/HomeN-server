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
from datetime import timedelta

from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers

from apps.homes.models import (
    AssignmentItem,
    Chore,
    ChoreCategory,
    Home,
    HomeChore,
    HomeChoreNote,
    HomeMember,
    HomeImageType,
    StarterPack,
    WeeklyAssignment,
)


# ── 출력 매핑 (난이도 → 포인트 / 3단계 라벨, 요일 → 한글) ─────────────────────
#
# 디자인이 노출하는 표현은 5단계 난이도와 다르다.
# - 난이도(1~5) 는 화면에서 3단계 라벨(쉬움/중간/어려움) 로 묶여 보이며,
# - 포인트는 난이도에 1:1 로 묶인 고정 값이다 ("포인트는 난이도에 따라 자동 고정돼요").
#   매핑의 원본은 `Chore.POINT_BY_DIFFICULTY` — 분담안 스냅샷 등 도메인 로직과
#   응답 직렬화가 같은 값을 쓴다.
# - 요일은 정수 배열(0=월 ~ 6=일) 외에 한글 라벨을 함께 노출한다.

_DIFFICULTY_LABEL_BY_DIFFICULTY: dict[int, str] = {
    1: "쉬움",
    2: "쉬움",
    3: "중간",
    4: "중간",
    5: "어려움",
}


def _difficulty_label(value: int) -> str:
    return _DIFFICULTY_LABEL_BY_DIFFICULTY.get(value, "")


def _point_for_difficulty(value: int) -> int:
    return Chore.POINT_BY_DIFFICULTY.get(value, 0)


def _weekday_labels(repeat_days: list[int]) -> list[str]:
    labels = []
    for day in repeat_days:
        try:
            labels.append(Chore.Weekday(day).label)
        except ValueError:
            continue
    return labels


# ── 집 생성 ──────────────────────────────────────────────────────────────────


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "스타터팩 적용 + 리워드",
            summary="스타터팩 적용 시점 (chores 는 빈 배열)",
            value={
                "name": "우리집",
                "image_id": 1,
                "starter_pack_id": 1,
                "chores": [],
                "rewards": [{"name": "치킨 한 마리", "goal_point": 50}],
            },
            request_only=True,
        ),
        OpenApiExample(
            "커스텀 집안일 + 리워드",
            summary="스타터팩 대신 사용자 정의 chore 배열 사용",
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

    집안일 입력은 다음 둘 중 **하나만** 허용한다 (둘 다 비어 있어도 됨):
    - `starter_pack_id`: 스타터팩 ID — 해당 팩의 chore 들이 일괄로 HomeChore 로 연결.
    - `chores`: 사용자 정의 chore 정의 배열.

    둘 다 지정되면 400 (`ambiguous_chore_input`). 리워드는 별개로 동시 등록 가능.
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
            allow_empty=False,
            help_text="반복 요일 정수 목록 (0=월 ~ 6=일). 최소 1개 필수.",
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
    starter_pack_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        default=None,
        help_text="적용할 스타터팩 PK (선택). 지정 시 해당 팩의 chore 들이 일괄 연결되며 `chores` 와 동시 사용 불가.",
    )
    starter_pack_chore_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_null=True,
        default=None,
        help_text=(
            "스타터팩에서 실제로 적용할 Chore PK 목록 (미리보기에서 체크된 항목). "
            "생략/null 이면 팩 전체, 빈 배열이면 아무것도 적용하지 않는다."
        ),
    )
    chores = ChoreInputSerializer(many=True, default=list, help_text="사용자 정의 집안일 목록 (선택, `starter_pack_id` 와 동시 사용 불가).")
    rewards = RewardInputSerializer(many=True, default=list, help_text="함께 등록할 리워드 목록 (선택).")

    def validate_name(self, value: str) -> str:
        """집 이름 규칙: 한글·영문·숫자·공백만 허용, 공백 단독 불가."""
        if not re.match(r"^[가-힣a-zA-Z0-9 ]+$", value):
            raise serializers.ValidationError("집 이름은 한글, 영문, 숫자, 띄어쓰기만 사용할 수 있습니다.")
        if value.strip() == "":
            raise serializers.ValidationError("집 이름을 입력해 주세요.")
        return value

    def validate(self, attrs: dict) -> dict:
        """`starter_pack_id` 와 `chores` 는 동시에 지정할 수 없다."""
        if attrs.get("starter_pack_id") is not None and attrs.get("chores"):
            raise serializers.ValidationError(
                {"ambiguous_chore_input": "starter_pack_id 와 chores 는 동시에 지정할 수 없습니다."}
            )
        return attrs


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

    난이도/포인트/요일 표현 규칙:
    - `difficulty_label`: 1~2='쉬움', 3~4='중간', 5='어려움' (3단계 매핑).
    - `point`: 1=40, 2=80, 3=120, 4=160, 5=200 (난이도 1:1 고정).
    - `repeat_days_label`: `repeat_days` 의 한글 라벨 배열 (예: [0,5] → ["월","토"]).
    """

    category_label = serializers.CharField(
        source="get_category_display",
        read_only=True,
        help_text="카테고리 한국어 표시 (예: '청소', '주방').",
    )
    difficulty_label = serializers.SerializerMethodField(
        help_text="난이도 화면 라벨 (3단계 매핑): 1~2='쉬움', 3~4='중간', 5='어려움'.",
    )
    point = serializers.SerializerMethodField(
        help_text="난이도 고정 포인트: 1=40, 2=80, 3=120, 4=160, 5=200.",
    )
    repeat_days_label = serializers.SerializerMethodField(
        help_text="반복 요일 한글 라벨 배열 (예: ['월','토']).",
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
            "repeat_days_label",
            "difficulty",
            "difficulty_label",
            "point",
        ]
        extra_kwargs = {
            "id": {"help_text": "집안일 마스터 PK."},
            "category": {"help_text": "카테고리 enum 정수 (1~5)."},
            "name": {"help_text": "집안일 제목."},
            "description": {"help_text": "집안일 설명 (없으면 빈 문자열)."},
            "repeat_days": {"help_text": "반복 요일 정수 배열 (0=월 ~ 6=일)."},
            "difficulty": {"help_text": "난이도 enum 정수 (1=하 ~ 5=상)."},
        }

    def get_difficulty_label(self, obj: Chore) -> str:
        return _difficulty_label(obj.difficulty)

    def get_point(self, obj: Chore) -> int:
        return _point_for_difficulty(obj.difficulty)

    def get_repeat_days_label(self, obj: Chore) -> list[str]:
        return _weekday_labels(obj.repeat_days)


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
        allow_empty=False,
        help_text="반복 요일 정수 배열 (0=월 ~ 6=일). 최소 1개 필수.",
    )
    difficulty = serializers.ChoiceField(
        choices=Chore.Difficulty.choices,
        help_text="난이도 enum (1=하 ~ 5=상).",
    )


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "이름·요일만 부분 수정",
            value={"name": "거실 청소", "repeat_days": [0, 3]},
            request_only=True,
        ),
        OpenApiExample(
            "난이도만 부분 수정",
            value={"difficulty": 4},
            request_only=True,
        ),
    ]
)
class HomeChoreUpdateSerializer(serializers.Serializer):
    """집안일 수정 요청 (PATCH — 부분 수정).

    모든 필드가 optional 이며, 전달된 키만 적용된다. 스타터팩에서 비롯된 chore 는
    서비스 레이어에서 copy-on-write 로 처리되어 본인 집 전용 사본이 생성된다.
    """

    category = serializers.ChoiceField(
        choices=ChoreCategory.choices,
        required=False,
        help_text="카테고리 enum (1=쓰레기 ~ 5=세탁).",
    )
    name = serializers.CharField(
        max_length=20,
        required=False,
        help_text="집안일 제목 (1~20자).",
    )
    description = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        help_text="집안일 설명 (최대 20자, 빈 문자열 허용).",
    )
    repeat_days = serializers.ListField(
        child=serializers.ChoiceField(choices=Chore.Weekday.choices),
        required=False,
        allow_empty=False,
        help_text="반복 요일 정수 배열 (0=월 ~ 6=일). 전달 시 최소 1개 필수.",
    )
    difficulty = serializers.ChoiceField(
        choices=Chore.Difficulty.choices,
        required=False,
        help_text="난이도 enum (1=하 ~ 5=상).",
    )


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "스타터팩 적용",
            summary="스타터팩 ID 만 보내 일괄 적용",
            value={"starter_pack_id": 1},
            request_only=True,
        ),
        OpenApiExample(
            "커스텀 복수 등록",
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
        ),
    ]
)
class HomeChoreListCreateSerializer(serializers.Serializer):
    """집안일 추가 요청.

    다음 둘 중 **정확히 하나** 만 지정한다:
    - `starter_pack_id`: 스타터팩 일괄 적용 (기존 chore 와 중복되면 skip — 멱등).
    - `chores`: 사용자 정의 chore 배열 (단건도 길이 1 배열).

    둘 다 지정되거나 둘 다 비어 있으면 400.
    """

    starter_pack_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        default=None,
        help_text="적용할 스타터팩 PK. `chores` 와 동시 사용 불가.",
    )
    starter_pack_chore_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_null=True,
        default=None,
        help_text=(
            "스타터팩에서 실제로 적용할 Chore PK 목록 (미리보기에서 체크된 항목). "
            "생략/null 이면 팩 전체, 빈 배열이면 아무것도 적용하지 않는다. "
            "`starter_pack_id` 와 함께 사용한다."
        ),
    )
    chores = HomeChoreCreateSerializer(
        many=True,
        default=list,
        help_text="추가할 사용자 정의 집안일 목록. `starter_pack_id` 와 동시 사용 불가.",
    )

    def validate(self, attrs: dict) -> dict:
        starter_pack_id = attrs.get("starter_pack_id")
        chores = attrs.get("chores") or []
        if starter_pack_id is not None and chores:
            raise serializers.ValidationError(
                {"ambiguous_chore_input": "starter_pack_id 와 chores 는 동시에 지정할 수 없습니다."}
            )
        if starter_pack_id is None and not chores:
            raise serializers.ValidationError(
                {"missing_chore_input": "starter_pack_id 또는 chores 중 하나는 반드시 지정해야 합니다."}
            )
        return attrs


class HomeChoreOutputSerializer(serializers.ModelSerializer):
    """집에 배정된 집안일(`HomeChore`) 응답.

    `Chore` 의 마스터 정보(이름/카테고리 등) 와 `HomeChore` 의 인스턴스 정보(PK 등)
    를 평탄화해 한 객체로 응답한다.

    메모는 본 응답에 포함되지 않는다 — 다중 작성자/수정 가능 메모는 별도 1:N 모델
    (`HomeChoreNote`) 로 노출되며 `GET /homes/mine/chores/{id}/notes/` 로 조회한다.

    난이도/포인트/요일 표현은 `ChoreOutputSerializer` 와 동일한 매핑을 사용한다.
    """

    category = serializers.IntegerField(source="chore.category", help_text="카테고리 enum 정수.")
    category_label = serializers.CharField(source="chore.get_category_display", help_text="카테고리 한국어.")
    name = serializers.CharField(source="chore.name", help_text="집안일 제목.")
    description = serializers.CharField(source="chore.description", help_text="집안일 설명.")
    repeat_days = serializers.ListField(source="chore.repeat_days", help_text="반복 요일 정수 배열.")
    repeat_days_label = serializers.SerializerMethodField(
        help_text="반복 요일 한글 라벨 배열 (예: ['월','토']).",
    )
    difficulty = serializers.IntegerField(source="chore.difficulty", help_text="난이도 enum 정수.")
    difficulty_label = serializers.SerializerMethodField(
        help_text="난이도 화면 라벨 (3단계 매핑): 1~2='쉬움', 3~4='중간', 5='어려움'.",
    )
    point = serializers.SerializerMethodField(
        help_text="난이도 고정 포인트: 1=40, 2=80, 3=120, 4=160, 5=200.",
    )

    class Meta:
        model = HomeChore
        fields = [
            "id",
            "category",
            "category_label",
            "name",
            "description",
            "repeat_days",
            "repeat_days_label",
            "difficulty",
            "difficulty_label",
            "point",
            "is_active",
        ]
        extra_kwargs = {
            "id": {"help_text": "HomeChore PK — 메모 컬렉션 경로의 부모 식별자."},
            "is_active": {"help_text": "활성 여부. False 면 삭제(비활성화)된 집안일 — 상세 화면에서 안내 필요."},
        }

    def get_difficulty_label(self, obj: HomeChore) -> str:
        return _difficulty_label(obj.chore.difficulty)

    def get_point(self, obj: HomeChore) -> int:
        return _point_for_difficulty(obj.chore.difficulty)

    def get_repeat_days_label(self, obj: HomeChore) -> list[str]:
        return _weekday_labels(obj.chore.repeat_days)


class HomeChoreDetailOutputSerializer(HomeChoreOutputSerializer):
    """집안일 상세조회 전용 응답 — 이번 주(월~일) 진행상태 포함.

    목록/PATCH 응답은 기존 `HomeChoreOutputSerializer` 를 그대로 사용한다.
    상세 화면이 일주일 요일 칸 + 완료자(닉네임/프로필) 표시를 요구해 별도
    시리얼라이저로 분리했다.

    `weekly_progress` 의 각 원소는 다음 키를 가진다.
    - `weekday`: 0(월) ~ 6(일).
    - `label`: 한글 요일 라벨.
    - `status`: `completed` / `incomplete` / `not_scheduled`.
        - `not_scheduled` 는 배정도 `chore.repeat_days` 도 아닌 요일.
    - `assignee`: 이번 주 분담안에서 그 요일의 담당자 `{uid, name, profile_image}`.
        분담안이 없거나 배정되지 않은 요일이면 `null`. 실제 완료자와 다를 수 있다.
    - `completed_by`: `status=completed` 일 때 완료자 정보 `{uid, name, profile_image}`,
        그 외엔 `null`. 완료자 유저가 탈퇴(SET_NULL) 된 경우에도 `null`.
    """

    weekly_progress = serializers.SerializerMethodField(
        help_text=(
            "이번 주(월~일) 요일별 7개 진행상태. status 값: "
            "completed/incomplete/not_scheduled. 각 원소에 담당자(assignee) 포함."
        ),
    )

    class Meta(HomeChoreOutputSerializer.Meta):
        fields = HomeChoreOutputSerializer.Meta.fields + ["weekly_progress"]

    def get_weekly_progress(self, obj: HomeChore) -> list[dict]:
        from apps.homes import selectors

        return selectors.get_weekly_progress(obj)


# ── 집안일 메모 (1:N) ──────────────────────────────────────────────────────────


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "메모 응답",
            value={
                "id": 12,
                "author": {"uid": "8f3e2b1a-1234-4abc-9def-1234567890ab", "name": "홍길동", "profile_image": 3},
                "content": "주방 세제 떨어짐 — 사 와야 함",
                "created_at": "2026-05-13T12:00:00Z",
                "updated_at": "2026-05-13T12:00:00Z",
            },
            response_only=True,
        ),
    ]
)
class HomeChoreNoteOutputSerializer(serializers.ModelSerializer):
    """집안일 메모 한 건의 응답.

    `author` 는 닉네임 + 프로필 이미지 + uid 를 내려 FE 가 작성자 표시·본인 여부
    판별에 사용한다 (수정·삭제 버튼 권한 분기).
    """

    author = serializers.SerializerMethodField(
        help_text="작성자 정보 (uid / name / profile_image).",
    )

    class Meta:
        model = HomeChoreNote
        fields = ["id", "author", "content", "created_at", "updated_at"]
        extra_kwargs = {
            "id": {"help_text": "HomeChoreNote PK."},
            "content": {"help_text": "메모 본문 (1~200자, 빈 문자열 불가)."},
            "created_at": {"help_text": "생성 일시 (ISO 8601)."},
            "updated_at": {"help_text": "최종 수정 일시 (ISO 8601)."},
        }

    def get_author(self, obj: HomeChoreNote) -> dict:
        author = obj.author
        return {
            "uid": str(author.uid),
            "name": author.name,
            "profile_image": author.profile_image,
        }


@extend_schema_serializer(
    examples=[OpenApiExample("메모 작성", value={"content": "락스 사용 시 환기 필수"}, request_only=True)]
)
class HomeChoreNoteCreateSerializer(serializers.Serializer):
    """집안일 메모 작성 요청."""

    content = serializers.CharField(
        max_length=200,
        help_text="메모 본문 (1~200자, 빈 문자열 불가).",
    )


@extend_schema_serializer(
    examples=[OpenApiExample("메모 수정", value={"content": "수정된 내용"}, request_only=True)]
)
class HomeChoreNoteUpdateSerializer(serializers.Serializer):
    """집안일 메모 수정 요청 (작성자만 가능)."""

    content = serializers.CharField(
        max_length=200,
        help_text="새 메모 본문 (1~200자, 빈 문자열 불가).",
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


# ── 분담안 (WeeklyAssignment) ─────────────────────────────────────────────────


class AssignmentWeekQuerySerializer(serializers.Serializer):
    """분담안 조회 쿼리 파라미터.

    `week_start` 는 조회할 주차의 월요일 날짜. 생략 시 **이번 주차**를 조회한다
    (분담안 탭의 기본 진입 탭이 `이번 주`).

    `assignee` 는 항목 목록을 담당자로 좁히는 필터 — `me` 또는 구성원 uid.
    멤버 필터 칩(전체/나/멤버별)에 대응하며, `member_points` 는 항상 전체
    구성원 기준으로 반환된다.
    """

    week_start = serializers.DateField(
        required=False,
        help_text="조회할 주차의 월요일 날짜 (YYYY-MM-DD). 생략 시 이번 주차.",
    )
    assignee = serializers.CharField(
        required=False,
        help_text="항목 담당자 필터 — `me` 또는 구성원 uid. 생략 시 전체.",
    )

    def validate_week_start(self, value):
        if value.weekday() != 0:
            raise serializers.ValidationError("week_start 는 월요일 날짜여야 합니다.")
        return value


class AssignmentHistoryQuerySerializer(serializers.Serializer):
    """분담안 히스토리 조회 쿼리 파라미터.

    화면(T3C_PlanHistory)은 `1주 전 >` 형태의 주차 셀렉터로 과거 분담안을
    조회하며, **최대 4주 전까지** 지원한다.
    """

    weeks_ago = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=4,
        default=1,
        help_text="조회할 과거 주차 (1=지난 주 ~ 4=4주 전). 생략 시 1.",
    )


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "다음 주 분담안 수동 생성",
            value={"week_start": "2026-07-13"},
            request_only=True,
        ),
    ]
)
class AssignmentCreateSerializer(serializers.Serializer):
    """분담안 수동 생성 요청 (관리자 전용).

    `week_start` 생략 시 다음 주차 분담안을 생성한다. 과거 주차는 불가.
    수동 생성된 주차는 일요일 자동 생성에서 스킵된다.
    """

    week_start = serializers.DateField(
        required=False,
        help_text="대상 주차의 월요일 날짜 (YYYY-MM-DD). 생략 시 다음 주차. 과거 주차 불가.",
    )


class AssignmentItemOutputSerializer(serializers.ModelSerializer):
    """분담안 항목(주차별 실행 집안일) 응답.

    집안일명/카테고리/난이도/포인트는 분담안 생성 시점 **스냅샷** — 이후 원본
    수정·삭제에 영향받지 않는다. `is_completed` 는 `ChoreCompletion` 과 조인해
    계산한다 (context["completed_keys"] 필요).
    """

    weekday_label = serializers.SerializerMethodField(help_text="요일 한글 라벨 (예: '월').")
    category_label = serializers.CharField(source="get_category_display", help_text="카테고리 한국어.")
    difficulty_label = serializers.SerializerMethodField(
        help_text="난이도 화면 라벨 (3단계 매핑): 1~2='쉬움', 3~4='중간', 5='어려움'.",
    )
    assignee = serializers.SerializerMethodField(
        help_text="담당자 {uid, name, profile_image}. 탈퇴한 유저면 null.",
    )
    date = serializers.SerializerMethodField(help_text="실행 날짜 (week_start + weekday).")
    is_completed = serializers.SerializerMethodField(
        help_text="완료 여부 — 해당 날짜의 ChoreCompletion 존재 여부.",
    )
    change_type = serializers.SerializerMethodField(
        help_text=(
            "생성 시점 이후 원본 변경 표시 — `updated`(수정됨, 화면 UPDATE 배지) / "
            "`removed`(원본 삭제됨) / null(변경 없음)."
        ),
    )

    class Meta:
        model = AssignmentItem
        fields = [
            "id",
            "home_chore_id",
            "weekday",
            "weekday_label",
            "chore_name",
            "category",
            "category_label",
            "difficulty",
            "difficulty_label",
            "point",
            "assignee",
            "date",
            "is_completed",
            "change_type",
        ]
        extra_kwargs = {
            "id": {"help_text": "분담안 항목 PK."},
            "weekday": {"help_text": "실행 요일 (0=월 ~ 6=일)."},
            "chore_name": {"help_text": "생성 시점 집안일명 (스냅샷)."},
            "category": {"help_text": "생성 시점 카테고리 enum (스냅샷)."},
            "difficulty": {"help_text": "생성 시점 난이도 enum (스냅샷)."},
            "point": {"help_text": "생성 시점 포인트 (스냅샷)."},
        }

    def get_weekday_label(self, obj: AssignmentItem) -> str:
        return Chore.Weekday(obj.weekday).label

    def get_difficulty_label(self, obj: AssignmentItem) -> str:
        return _difficulty_label(obj.difficulty)

    def get_assignee(self, obj: AssignmentItem) -> dict | None:
        if obj.assignee is None:
            return None
        return {
            "uid": str(obj.assignee.uid),
            "name": obj.assignee.name,
            "profile_image": obj.assignee.profile_image,
        }

    def get_date(self, obj: AssignmentItem) -> str:
        return str(obj.assignment.week_start + timedelta(days=obj.weekday))

    def get_is_completed(self, obj: AssignmentItem) -> bool:
        completed_keys = self.context.get("completed_keys", set())
        item_date = obj.assignment.week_start + timedelta(days=obj.weekday)
        return (obj.home_chore_id, item_date) in completed_keys

    def get_change_type(self, obj: AssignmentItem) -> str | None:
        changes = self.context.get("changes")
        if not changes:
            return None
        if obj.id in set(changes.get("removed_item_ids", [])):
            return "removed"
        if obj.id in set(changes.get("updated_item_ids", [])):
            return "updated"
        return None


class WeeklyAssignmentOutputSerializer(serializers.ModelSerializer):
    """분담안 응답 — 항목 목록과 멤버별 예상 포인트 합계 포함."""

    items = AssignmentItemOutputSerializer(many=True, help_text="분담안 항목 목록 (요일순).")
    member_points = serializers.SerializerMethodField(
        help_text="멤버별 예상 배정 포인트 합계 [{uid, name, profile_image, expected_point}].",
    )
    changes = serializers.SerializerMethodField(
        help_text=(
            "생성 시점 이후 집안일 변경 요약. `new_entries` 는 분담안에 없는 신규 "
            "(집안일, 요일) 행 — 화면에서 NEW 배지로 노출한다. `has_changes` 가 true 면 "
            "확정 시 409(chores_changed) 가 발생하므로 재생성을 유도한다."
        ),
    )

    class Meta:
        model = WeeklyAssignment
        fields = [
            "id",
            "week_start",
            "status",
            "generated_at",
            "confirmed_at",
            "items",
            "member_points",
            "changes",
        ]
        extra_kwargs = {
            "id": {"help_text": "분담안 PK."},
            "week_start": {"help_text": "적용 주차의 월요일 날짜."},
            "status": {"help_text": "proposed(제안됨) / confirmed(확정됨) / expired(만료됨)."},
            "generated_at": {"help_text": "분담안 생성(재생성) 시점."},
            "confirmed_at": {"help_text": "확정 시각. 미확정이면 null."},
        }

    def get_member_points(self, obj: WeeklyAssignment) -> list[dict]:
        totals: dict[str, dict] = {}
        for item in obj.items.all():
            if item.assignee is None:
                continue
            uid = str(item.assignee.uid)
            entry = totals.setdefault(
                uid,
                {
                    "uid": uid,
                    "name": item.assignee.name,
                    "profile_image": item.assignee.profile_image,
                    "expected_point": 0,
                },
            )
            entry["expected_point"] += item.point
        return sorted(totals.values(), key=lambda e: e["uid"])

    def get_changes(self, obj: WeeklyAssignment) -> dict:
        return self.context.get(
            "changes",
            {"has_changes": False, "new_entries": [], "updated_item_ids": [], "removed_item_ids": []},
        )


# ── 집안일 완료 처리 ─────────────────────────────────────────────────────────


@extend_schema_serializer(
    examples=[
        OpenApiExample("오늘 완료", value={}, request_only=True),
        OpenApiExample("특정 날짜 완료", value={"date": "2026-07-15"}, request_only=True),
    ]
)
class ChoreCompletionCreateSerializer(serializers.Serializer):
    """집안일 완료 처리 요청.

    `date` 생략 시 서버 로컬 날짜(오늘) 로 기록한다. 완료는 **확정된 분담안의
    담당자**만 가능하며, 같은 (집안일, 날짜) 는 1건만 기록된다.
    """

    date = serializers.DateField(
        required=False,
        help_text="완료 기준 날짜 (YYYY-MM-DD). 생략 시 오늘.",
    )


class ChoreCompletionOutputSerializer(serializers.Serializer):
    """집안일 완료 이력 응답."""

    id = serializers.IntegerField(help_text="완료 이력 PK.")
    home_chore_id = serializers.IntegerField(help_text="완료된 HomeChore PK.")
    date = serializers.DateField(help_text="완료 기준 날짜.")
    point = serializers.IntegerField(help_text="획득 포인트 (분담안 항목 스냅샷 포인트).")
    completed_by = serializers.DictField(
        help_text="완료자 {uid, name, profile_image}.",
    )


# ── 홈 대시보드 ──────────────────────────────────────────────────────────────


class DashboardMemberSerializer(serializers.Serializer):
    """대시보드에 노출되는 구성원 표현."""

    uid = serializers.CharField(help_text="유저 uid.")
    name = serializers.CharField(help_text="닉네임.")
    profile_image = serializers.IntegerField(allow_null=True, help_text="프로필 이미지 enum.")


class DashboardMvpSerializer(DashboardMemberSerializer):
    """우리집 MVP — 이번 주 완료 포인트가 가장 높은 구성원."""

    point = serializers.IntegerField(help_text="이번 주 완료 포인트 합.")
    completed_count = serializers.IntegerField(help_text="이번 주 완료 건수.")


class DashboardHomeSerializer(serializers.Serializer):
    """대시보드 상단 집 정보."""

    id = serializers.IntegerField(help_text="집 PK.")
    name = serializers.CharField(help_text="집 이름.")
    image = serializers.IntegerField(help_text="집 이미지 enum.")
    member_count = serializers.IntegerField(help_text="구성원 수.")


class DashboardThisWeekSerializer(serializers.Serializer):
    """이번 주 진행 요약."""

    week_start = serializers.DateField(help_text="이번 주 월요일 날짜.")
    assignment_id = serializers.IntegerField(allow_null=True, help_text="이번 주 분담안 PK. 없으면 null.")
    status = serializers.CharField(
        allow_null=True, help_text="proposed / confirmed / expired. 분담안이 없으면 null."
    )
    total_count = serializers.IntegerField(help_text="이번 주 전체 항목 수.")
    completed_count = serializers.IntegerField(help_text="완료 항목 수.")
    progress_rate = serializers.IntegerField(help_text="진행률 % (완료/전체, 반올림).")
    my_contribution_rate = serializers.IntegerField(
        help_text="내 기여도 % (내 완료 포인트 / 집 전체 완료 포인트, 반올림).",
    )
    mvp = DashboardMvpSerializer(allow_null=True, help_text="우리집 MVP. 완료 이력이 없으면 null.")


class DashboardNextWeekSerializer(serializers.Serializer):
    """다음 주 분담안 상태 라벨용 요약."""

    week_start = serializers.DateField(help_text="다음 주 월요일 날짜.")
    assignment_id = serializers.IntegerField(allow_null=True, help_text="다음 주 분담안 PK. 없으면 null.")
    status = serializers.CharField(
        allow_null=True,
        help_text="proposed(제안됨) / confirmed(확정됨). null 이면 화면에 '생성 필요' + 레드닷.",
    )


class HomeDashboardOutputSerializer(serializers.Serializer):
    """홈 대시보드(T1_HomeDashboard) 응답."""

    home = DashboardHomeSerializer(help_text="집 정보.")
    this_week = DashboardThisWeekSerializer(help_text="이번 주 진행 요약.")
    next_week = DashboardNextWeekSerializer(help_text="다음 주 분담안 상태.")
    items = AssignmentItemOutputSerializer(
        many=True,
        help_text="이번 주 분담안 항목 목록 (멤버 필터 탭용). 분담안이 없으면 빈 배열.",
    )


class AssignmentHistoryWeekSerializer(serializers.Serializer):
    """히스토리 주차 셀렉터 한 칸."""

    week_start = serializers.DateField(help_text="해당 주차의 월요일 날짜.")
    weeks_ago = serializers.IntegerField(help_text="1(지난 주) ~ 4(4주 전).")
    assignment_id = serializers.IntegerField(allow_null=True, help_text="분담안 PK. 없으면 null.")
    status = serializers.CharField(
        allow_null=True, help_text="confirmed / expired / proposed. 분담안이 없으면 null."
    )


class AssignmentHistoryOutputSerializer(serializers.Serializer):
    """분담안 히스토리 응답 — 주차 셀렉터 + 선택된 주차의 분담안."""

    weeks = AssignmentHistoryWeekSerializer(many=True, help_text="조회 가능한 과거 4주차 목록.")
    selected = WeeklyAssignmentOutputSerializer(
        allow_null=True, help_text="선택된 주차의 분담안. 기록이 없으면 null."
    )

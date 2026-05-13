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

from apps.homes.models import (
    Chore,
    ChoreCategory,
    Home,
    HomeChore,
    HomeChoreNote,
    HomeMember,
    HomeImageType,
    Reward,
    StarterPack,
)


# ── 출력 매핑 (난이도 → 포인트 / 3단계 라벨, 요일 → 한글) ─────────────────────
#
# 디자인이 노출하는 표현은 5단계 난이도와 다르다.
# - 난이도(1~5) 는 화면에서 3단계 라벨(쉬움/중간/어려움) 로 묶여 보이며,
# - 포인트는 난이도에 1:1 로 묶인 고정 값이다 ("포인트는 난이도에 따라 자동 고정돼요").
# - 요일은 정수 배열(0=월 ~ 6=일) 외에 한글 라벨을 함께 노출한다.
# 본 매핑은 응답 직렬화 시에만 사용한다 — Chore 모델 자체에는 보관하지 않는다.

_POINT_BY_DIFFICULTY: dict[int, int] = {1: 40, 2: 80, 3: 120, 4: 160, 5: 200}
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
    return _POINT_BY_DIFFICULTY.get(value, 0)


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
    starter_pack_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        default=None,
        help_text="적용할 스타터팩 PK (선택). 지정 시 해당 팩의 chore 들이 일괄 연결되며 `chores` 와 동시 사용 불가.",
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
        ]
        extra_kwargs = {
            "id": {"help_text": "HomeChore PK — 메모 컬렉션 경로의 부모 식별자."},
        }

    def get_difficulty_label(self, obj: HomeChore) -> str:
        return _difficulty_label(obj.chore.difficulty)

    def get_point(self, obj: HomeChore) -> int:
        return _point_for_difficulty(obj.chore.difficulty)

    def get_repeat_days_label(self, obj: HomeChore) -> list[str]:
        return _weekday_labels(obj.chore.repeat_days)


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

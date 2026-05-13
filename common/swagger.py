"""drf-spectacular postprocessing hook — field-level example 일괄 주입.

DRF 의 `serializers.Field` 는 `example=` 인자를 받지 않아 Pydantic 의
`Field(..., examples=[...])` 같은 일대일 매핑을 줄 수 없다. drf-spectacular 의
postprocessing 훅으로 schema 생성 후 component property 의 이름이 본 모듈의
예시 매핑과 매칭되면 OpenAPI `example` 키워드를 자동 주입한다.

규칙
----
- `FIELD_EXAMPLES_BY_COMPONENT[component_name][prop_name]`: 컴포넌트별 override.
  같은 `name` 필드도 Home 에서는 '우리집', User 에서는 '홍길동' 처럼 다른 값.
- `FIELD_EXAMPLES_GLOBAL[prop_name]`: 컨텍스트 무관 공통 예시 (UUID, 토큰, enum 정수 등).
- 컴포넌트별이 먼저, 글로벌이 fallback.
- 이미 `example` 이 정의된 필드는 건드리지 않는다.

Swagger UI 효과: `Schemas` 탭의 각 필드에 example 이 노출되며, 요청 본문 편집기는
별도의 `OpenApiExample` (body-level) 가 우선 사용된다.
"""

from typing import Any

# 모든 컨텍스트에서 같은 값을 써도 무방한 공통 예시.
FIELD_EXAMPLES_GLOBAL: dict[str, Any] = {
    "id": 12,
    "uid": "8f3e2b1a-1234-4abc-9def-1234567890ab",
    "created_at": "2026-05-13T12:00:00Z",
    "updated_at": "2026-05-13T12:00:00Z",
    # Auth / Token
    "access": "eyJhbGciOiJIUzI1NiIs...access...",
    "refresh": "eyJhbGciOiJIUzI1NiIs...refresh...",
    "code": "abc123XYZ_kakao_authorization_code",
    "is_profile_set": True,
    "has_home": True,
    "is_available": True,
    "is_staff": False,
    "is_active": True,
    "profile_image": 3,
    "home_role": 1,
    "user_id": "8f3e2b1a-1234-4abc-9def-1234567890ab",
    # Home enums
    "image": 1,
    "image_id": 1,
    "invite_code": "AB12CD",
    "status": "active",
    "member_count": 2,
    "starter_pack_id": 1,
    # Chore
    "category": 3,
    "category_label": "청소",
    "repeat_days": [0, 5],
    "repeat_days_label": ["월", "토"],
    "difficulty": 2,
    "difficulty_label": "쉬움",
    "point": 80,
    # Membership
    "role": 1,
    "role_label": "관리자",
}

# 컴포넌트별 override — schema 의 component name 키와 매칭.
FIELD_EXAMPLES_BY_COMPONENT: dict[str, dict[str, Any]] = {
    # Home / 멤버
    "Home": {"name": "우리집"},
    "HomeCreateRequest": {"name": "우리집"},
    "HomeOutput": {"name": "우리집"},
    "HomeInviteDetail": {"name": "우리집"},
    "HomeMember": {"name": "홍길동"},
    # User
    "User": {"name": "홍길동"},
    "UserProfileOutput": {"name": "홍길동"},
    "UserProfileUpdateRequest": {"name": "홍길동"},
    # Chore / HomeChore
    "Chore": {"name": "거실 청소", "description": "주 1회"},
    "ChoreOutput": {"name": "거실 청소", "description": "주 1회"},
    "ChoreInputRequest": {"name": "거실 청소", "description": "주 1회"},
    "HomeChoreCreateRequest": {"name": "거실 청소", "description": "주 1회"},
    "HomeChoreOutput": {"name": "거실 청소", "description": "주 1회"},
    # Reward
    "Reward": {"name": "치킨", "goal_point": 100},
    "RewardOutput": {"name": "치킨", "goal_point": 100},
    "RewardInputRequest": {"name": "치킨", "goal_point": 100},
    # StarterPack
    "StarterPack": {"name": "룸메이트 기본팩", "description": "2~4인 공용 공간을 깔끔하게 유지하는 표준 루틴"},
    # Note
    "HomeChoreNoteOutput": {"content": "락스 사용 시 환기 필수"},
    "HomeChoreNoteCreateRequest": {"content": "락스 사용 시 환기 필수"},
    "HomeChoreNoteUpdateRequest": {"content": "수정된 메모"},
}


def add_field_examples(result: dict, generator, request, public) -> dict:
    """OpenAPI schema 의 모든 component property 에 `example` 키워드를 주입."""
    schemas = (result.get("components") or {}).get("schemas") or {}
    for component_name, component in schemas.items():
        properties = component.get("properties") or {}
        for prop_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict):
                continue
            if "example" in prop_schema:
                continue
            comp_examples = FIELD_EXAMPLES_BY_COMPONENT.get(component_name, {})
            if prop_name in comp_examples:
                prop_schema["example"] = comp_examples[prop_name]
            elif prop_name in FIELD_EXAMPLES_GLOBAL:
                prop_schema["example"] = FIELD_EXAMPLES_GLOBAL[prop_name]
    return result

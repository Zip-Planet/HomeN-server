# Swagger / OpenAPI Conventions

본 문서는 본 repo 의 OpenAPI 문서화 규칙을 정의한다. `drf-spectacular` 의 자동 추출을 기본으로 하되, **모든 엔드포인트가 명시적 `summary` / `description` / `responses` 를 갖도록** 강제한다. 자동 추출만 의존하면 "이게 무슨 에러죠?" "이 응답에 뭐가 들어있죠?" 같은 질문이 코드 리뷰에서 반복된다.

## 0. 노출 URL

| URL | 용도 |
|---|---|
| `/api/docs/` | Swagger UI (사람이 보는 화면) |
| `/api/schema/` | OpenAPI 3.0 raw schema (YAML) |

설정: `config/settings.py` 의 `SPECTACULAR_SETTINGS`. TITLE / DESCRIPTION / TAGS / CONTACT / Swagger UI 옵션을 한 곳에서 관리한다.

## 1. 컨트롤러 (View) — `@extend_schema` 필수 항목

```python
@extend_schema(
    tags=["Homes"],
    summary="집 생성 (호출자를 관리자로 등록)",
    description=(
        "집을 생성하고 호출자를 관리자로 자동 등록한다. ...\n\n"
        "**검증**\n"
        "- 이름: 한글·영문·숫자·공백, 1~10자.\n"
        "- ...\n\n"
        "**에러**\n"
        "- 400 `already_has_home`: 이미 다른 집에 속해 있음.\n"
    ),
    request=HomeCreateSerializer,
    responses={
        201: OpenApiResponse(response=HomeOutputSerializer, description="생성된 집."),
        400: OpenApiResponse(description="이미 집이 있거나 입력 유효성 실패."),
        401: OpenApiResponse(description="access 토큰 누락/만료."),
    },
    examples=[
        OpenApiExample("정상 요청", value={...}, request_only=True),
    ],
)
def post(self, request):
    ...
```

### 1.1 필드별 규칙

- **`tags`**: 4종만 사용. 새 태그 추가 시 `SPECTACULAR_SETTINGS["TAGS"]` 에 description 도 함께 등록.
  - `Auth`, `Users`, `Homes`, `StarterPacks`
- **`summary`**: 1줄, ~40자. Swagger UI 의 endpoint 라인에 그대로 노출되는 텍스트.
- **`description`**: markdown 허용. **플로우 / 검증 / 에러** 3개 섹션을 의식적으로 채운다.
- **`request`**: 입력 시리얼라이저 (없으면 생략).
- **`responses`**: 모든 의미 있는 상태코드를 명시. `200/201/204` 정상 응답 + 도메인 예외에 매핑되는 4xx 를 빠짐없이 기재. `OpenApiResponse(response=..., description=...)` 형태가 표준.
- **`examples`**: `OpenApiExample(name, value=..., request_only=True | response_only=True)` 로 분리. 한 엔드포인트에 정상 케이스 1개 + 대표 에러 1개 정도가 적정.

### 1.2 View 클래스 / 모듈 docstring

- **모듈 docstring**: 본 모듈이 다루는 API 묶음의 개요, 컨트롤러 책임의 약속(검증 → 서비스 호출 → 도메인 예외 매핑) 을 명시한다. `apps/users/views.py` / `apps/homes/views.py` 참고.
- **클래스 docstring**: 본 View 가 다루는 도메인 동작과 선결 조건을 적는다. swagger 의 `description` 과 일부 중복돼도 좋다 — 코드 독자와 API 소비자 양쪽이 별도로 본다.

## 2. 시리얼라이저 — `help_text` + `@extend_schema_serializer`

drf-spectacular 는 시리얼라이저 필드의 `help_text` 를 OpenAPI `description` 으로 자동 변환한다. 모든 필드에 `help_text` 를 부착한다.

```python
class HomeJoinSerializer(serializers.Serializer):
    """집 참여 요청.

    이미 집에 속한 유저가 호출하면 400 — 먼저 나가야 한다.
    유효하지 않은 초대코드는 404.
    """

    invite_code = serializers.CharField(
        max_length=6,
        help_text="6자리 대문자+숫자 초대코드 (예: 'AB12CD').",
    )
```

### 2.1 examples 부착

```python
@extend_schema_serializer(
    examples=[
        OpenApiExample("초대코드로 참여", value={"invite_code": "AB12CD"}, request_only=True),
    ]
)
class HomeJoinSerializer(serializers.Serializer):
    ...
```

`ModelSerializer` 의 자동 생성 필드는 `Meta.extra_kwargs` 를 사용한다:

```python
class Meta:
    model = Home
    fields = ["id", "name", "image", "invite_code", "status", "created_at"]
    extra_kwargs = {
        "id": {"help_text": "집 PK."},
        "name": {"help_text": "집 이름."},
        "invite_code": {"help_text": "6자리 대문자+숫자 초대코드."},
    }
```

## 3. 도메인 enum 노출

`models.IntegerChoices` / `TextChoices` 는 자동으로 OpenAPI `enum` 으로 추출된다. 사람이 읽는 라벨이 필요하면 별도 `*_label` 필드를 `SerializerMethodField` 또는 `source="get_*_display"` 로 노출한다 (현재 `HomeChoreOutputSerializer` 참조).

## 4. URL 패턴

URL 명명 규칙은 [`api-conventions.md §1`](api-conventions.md#1-uri-규칙) 을 따른다. `extend_schema` 가 자동으로 path 파라미터를 추출하지만, 의미 있는 description 을 부여하려면 다음을 명시한다:

```python
parameters=[
    OpenApiParameter("home_chore_id", int, OpenApiParameter.PATH, description="대상 HomeChore PK."),
]
```

## 5. 외부 View 의 swagger 부착

`SimpleJWT` 등 외부 라이브러리 View 는 `urls.py` 에서 `@extend_schema(...)` 데코레이터로 래핑한 뒤 등록한다 — `apps/users/urls.py` 의 `TokenRefreshView` 참조.

## 6. 검증 (PR 전 확인)

```bash
# 스키마 생성이 깨지지 않는지 확인 — 에러/경고가 0 이어야 함
python manage.py spectacular --file /tmp/schema.yml --validate

# 또는 docker 환경
docker compose run --rm app python manage.py spectacular --file /tmp/schema.yml --validate
```

- 새 엔드포인트 추가 시 위 명령이 무경고로 통과해야 한다.
- 깨진 경우 대부분 원인: 누락된 `request=` / `responses=`, 또는 미선언 시리얼라이저 import.

## 7. 점검 체크리스트 (PR 리뷰용)

- [ ] 새 엔드포인트에 `@extend_schema` 가 부착되어 있다.
- [ ] `tags` 가 `SPECTACULAR_SETTINGS["TAGS"]` 의 정의된 태그를 사용한다 (또는 신규 태그 정의가 추가됨).
- [ ] `summary` / `description` 이 채워져 있다 (`description` 이 한 줄이면 부족).
- [ ] 모든 4xx 도메인 분기가 `responses` 에 명시되어 있다.
- [ ] 시리얼라이저 필드에 `help_text` (또는 `Meta.extra_kwargs[<field>]["help_text"]`) 가 있다.
- [ ] request/response 예시가 최소 1개 이상 부착되어 있다 (선택, 단 신규 도메인은 권장).
- [ ] `python manage.py spectacular --validate` 통과.

## 8. 함정

- **`responses=` 가 dict 가 아닌 단일 시리얼라이저**: `responses=FooSerializer` 만 적으면 swagger 가 `200` 으로만 노출한다 — 4xx/5xx 도 노출하려면 반드시 dict.
- **`OpenApiResponse(response=FooSerializer)` vs `OpenApiResponse(description=...)`**: 본문이 있는 응답은 `response=`, 본문이 없는 응답(`204` 등) 은 `description=` 만.
- **`extend_schema_serializer` 가 ModelSerializer 의 자동 example 을 덮어쓰지 않음**: 명시한 example 이 우선.
- **`COMPONENT_SPLIT_REQUEST=True`** (본 repo 설정): 같은 시리얼라이저라도 request 와 response 컴포넌트가 분리되어 노출된다. snake 케이스 vs camel 케이스 등 컨벤션 충돌을 줄여준다.

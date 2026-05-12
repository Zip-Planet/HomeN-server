# API Conventions

본 서비스가 따르는 REST/HTTP 컨벤션의 단일 출처(Single Source of Truth) 다. RFC 9110(HTTP Semantics), Microsoft / Google / Zalando API 가이드라인 을 기반으로 한다.

> 코드 구조(앱 레이아웃, services / selectors 분리) 는 [architecture.md](architecture.md) 에 있다. 본 문서는 외부 계약(URI, method, status, 본문 형태) 에만 집중한다.

## 1. URI 규칙

- **명사**만 사용. 행위는 HTTP method 로 표현 (`GET /homes` ⭕ / `GET /getHomes` ❌)
- **소문자**만, 다중 단어는 `-`(하이픈) 사용 (`/starter-packs` ⭕ / `/starterPacks` ❌ / `/starter_packs` ❌)
- **컬렉션 리소스는 복수형** (`/homes`, `/users`, `/starter-packs`)
- 리소스 식별자는 path 파라미터: `/homes/mine/chores/{home_chore_id}`
- 하위 리소스는 중첩으로 표현, 깊이는 최대 2단계 권장: `/starter-packs/{id}/chores`
- 마지막 문자에 `/` 강제 — Django `APPEND_SLASH` 기본값 (redirect 회피 위해 클라이언트도 trailing slash 로 호출)
- 액션을 표현해야 하는 비-CRUD 엔드포인트는 `/{resource}/{id}/<verb>/` 형태로 마지막 segment 에만 동사 허용 (예: `/homes/mine/leave/`, `/homes/mine/transfer-admin/`). 남용 금지.

## 2. HTTP Method 의미론 (RFC 9110 §9)

| Method | 용도 | 안전 | 멱등 |
|---|---|---|---|
| `GET` | 조회 (단일/리스트) | ✅ | ✅ |
| `POST` | 생성, 또는 비-멱등 액션 | ❌ | ❌ |
| `PUT` | 전체 교체 (모든 필드 제공) | ❌ | ✅ |
| `PATCH` | 부분 갱신 | ❌ | ❌ (권장은 멱등 설계) |
| `DELETE` | 삭제 | ❌ | ✅ |

`GET` 은 절대 상태를 변경하지 않는다. 상태를 바꾸는 조회가 필요하면 `POST`.

## 3. Path 파라미터 vs Query 파라미터

| 종류 | 용도 | 예 |
|---|---|---|
| Path | 리소스 식별자 (없으면 그 리소스가 성립하지 않는 값) | `/homes/mine/chores/{home_chore_id}/` |
| Query | 필터링·페이지네이션·정렬·sparse-field 선택 | `?status=active&page=1` |

검색·필터 조합이 많아 query string 이 긴 경우에만 예외적으로 `POST /resource/search/` 로 본문에 조건을 받는다.

## 4. 페이지네이션 / 정렬 / 필터링

리스트 엔드포인트는 다음 query 파라미터를 표준으로 사용한다.

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `page` | int | `1` | 1-base 페이지 번호 |
| `page_size` | int | `15` | 페이지당 항목 수 (상한은 도메인별 결정) |
| `sort_by` | str | 도메인 PK | 정렬 기준 컬럼명 |
| `sort_order` | `asc` \| `desc` | `asc` | 정렬 방향 |

필터는 도메인별 컬럼명을 그대로 사용 (`?status=active&created_after=2026-01-01`). 다중 값은 콤마 분리 (`?status=active,pending`).

리스트 응답 본문은 §7 의 envelope 안에 다음 메타를 포함한다:

```json
{
  "data": {
    "items": [...],
    "total": 123,
    "page": 1,
    "page_size": 15
  }
}
```

## 5. API 버저닝

- **모든 라우터는 `/api/v1` prefix 필수.** 헬스체크 포함 예외 없음.
- 호환성을 깨는 변경이 발생하면 `/api/v2` 새 prefix 를 도입하고 `/api/v1` 은 deprecation 기간을 유지한다.
- prefix 는 `config/urls.py` 의 `include()` 시점에 박는다.

```python
path("api/v1/homes/", include(home_urlpatterns)),
```

## 6. 상태 코드

표준 코드만 사용한다 (본 프로젝트는 비표준 business 코드 채택 없음 — 일반 4xx/5xx 로 충분).

| 코드 | 사용 시점 |
|---|---|
| `200 OK` | 성공 (조회·갱신 후 본문 반환) |
| `201 Created` | 자원 생성 성공 (생성된 리소스 반환) |
| `204 No Content` | 성공 + 본문 없음 (삭제·일부 액션) |
| `400 Bad Request` | 요청 파싱/validation 실패, 도메인 입력 충돌 (`already_has_home` 등) |
| `401 Unauthorized` | 인증 누락/실패 |
| `403 Forbidden` | 인증은 됐으나 권한 없음 (예: 관리자 전용 작업) |
| `404 Not Found` | 리소스 미존재 |
| `409 Conflict` | 동시성/중복 충돌 |
| `500 Internal Server Error` | 처리되지 않은 서버 오류 |

도메인 예외 → DRF 표준 예외 매핑 가이드는 [`apps/<app>/views.py`](../apps) 의 핸들러 예시 참고:

| 도메인 상황 | 컨트롤러에서 발생시키는 예외 | 응답 |
|---|---|---|
| 입력 유효성 / 도메인 입력 충돌 | `rest_framework.exceptions.ValidationError({...})` | `400` |
| 인증 실패 (SSO 등) | `AuthenticationFailed` | `401` |
| 권한 없음 (관리자 전용 등) | `PermissionDenied` | `403` |
| 리소스 없음 / 잘못된 ID | `NotFound` | `404` |

## 7. 응답 본문

### 7.1 성공 응답

- 단일 / 리스트 응답은 **시리얼라이저의 출력을 그대로** 반환한다 (envelope 미사용).
- 본 repo 는 envelope 을 채택하지 않으며, FE 가 직접 시리얼라이저 결과를 소비한다. 추후 envelope 도입 시 본 문서를 먼저 개정한다.

```python
return Response(HomeOutputSerializer(home).data, status=status.HTTP_201_CREATED)
```

### 7.2 에러 응답

DRF 기본 + `common.exceptions.custom_exception_handler` 가 다음 형태로 통일한다 (실제 형태는 핸들러 구현 참조):

```json
{
  "detail": "유효하지 않은 초대코드입니다."
}
```

`ValidationError({...})` 로 발생시킨 경우 key-value 가 그대로 노출된다:

```json
{
  "already_has_home": "이미 다른 집에 속해 있습니다."
}
```

## 8. 인증

- 헤더: `Authorization: Bearer <access_token>`
- 검증: `rest_framework_simplejwt.authentication.JWTAuthentication` (default authentication 으로 settings 에 wired)
- access 토큰은 `/api/v1/auth/kakao/`, `/api/v1/auth/apple/` 로 발급, `/api/v1/auth/token/refresh/` 로 갱신.
- 로그아웃 (`/api/v1/auth/logout/`) 은 refresh 토큰을 `token_blacklist` 에 등록.

## 9. Content-Type

- 요청·응답 본문 기본값: `application/json; charset=utf-8`
- 파일 업로드는 현재 미사용 — 도입 시 `multipart/form-data` + DRF `parser_classes` 명시.
- 다른 포맷은 사용하지 않는다 (XML, form-urlencoded 일반 페이로드 등 ❌).

## 10. 컨트롤러 작성 패턴

모든 DRF View 는 다음 4단계를 따른다.

1. `serializer = FooSerializer(data=request.data); serializer.is_valid(raise_exception=True)` 로 요청 검증.
2. `services.<verb>(user=request.user, **serializer.validated_data)` 로 서비스 호출.
3. 도메인 예외를 DRF 표준 예외(`ValidationError`, `PermissionDenied`, `NotFound`) 로 매핑.
4. `Response(OutputSerializer(result).data, status=...)` 로 응답.

```python
class HomeJoinView(APIView):
    @extend_schema(
        tags=["Homes"],
        summary="초대코드로 집 참여",
        request=HomeJoinSerializer,
        responses={200: HomeOutputSerializer, 400: OpenApiResponse(description="이미 집이 있음"), 404: OpenApiResponse(description="유효하지 않은 초대코드")},
    )
    def post(self, request):
        invite_code = request.data.get("invite_code", "")
        try:
            services.join_home(user=request.user, invite_code=invite_code)
        except services.AlreadyHasHomeError as e:
            raise ValidationError({"already_has_home": str(e)}) from e
        except services.HomeNotFoundError as e:
            raise NotFound(str(e)) from e
        home = selectors.get_user_home(request.user)
        return Response(HomeOutputSerializer(home).data)
```

> 🚫 시리얼라이저를 service 에 직접 넘기지 않는다 — use case 가 HTTP 계약과 결합된다. 항상 `validated_data` 를 풀어서 전달.

## 11. Swagger 문서화 규칙

상세 규칙은 [`swagger-conventions.md`](swagger-conventions.md) 참고.

- 문서 노출: `/api/docs/` (Swagger UI), `/api/schema/` (raw OpenAPI)
- 라우터는 도메인별 prefix 로 분리 (`config/urls.py`)
- **모든 엔드포인트에 `summary` + `description` 필수**
  - `summary`: 1줄, 메뉴 목록에 노출
  - `description`: markdown 가능. 플로우 / 검증 / 에러 케이스를 포함
- 시리얼라이저 필드는 `help_text=` 로 OpenAPI `description` 을 채운다.
- request/response 예시는 `@extend_schema_serializer(examples=[OpenApiExample(...)])` 또는 `@extend_schema(examples=[...])` 로 부착.

## 12. 함정 (Pitfalls)

- **Trailing slash 자동 redirect** — Django `APPEND_SLASH=True` (기본값) 이라 `/homes` 로 들어오면 `/homes/` 로 301 redirect 한다. 클라이언트가 `Authorization` 헤더를 redirect 에 실어 보내지 않을 수 있으니, **항상 trailing slash 로 호출하도록** SDK/문서를 통일한다.
- **CSRF**: API 는 `SessionAuthentication` 을 사용하지 않으므로 CSRF 미적용. JWT 만 사용한다.
- **`PermissionDenied` 메시지 노출**: DRF 의 `PermissionDenied(str(e))` 메시지는 응답 본문에 노출된다. 도메인 메시지가 내부 정보를 흘리지 않도록 메시지를 의식적으로 작성한다.

## 참고 자료

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
- [Microsoft REST API Guidelines](https://github.com/microsoft/api-guidelines/blob/vNext/Guidelines.md)
- [Google API Design Guide](https://google.aip.dev/)
- [Zalando RESTful API Guidelines](https://opensource.zalando.com/restful-api-guidelines/)
- [JSON:API 1.1](https://jsonapi.org/)
- [Django REST Framework — Views](https://www.django-rest-framework.org/api-guide/views/)
- [drf-spectacular — Customization](https://drf-spectacular.readthedocs.io/en/latest/customization.html)

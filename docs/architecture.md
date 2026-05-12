# Architecture

본 프로젝트는 **Django + DRF** 기반의 모놀리식 백엔드다. 거대한 추상화 대신 Django 가 제공하는 기본 분리(앱·모델·뷰) 위에 얇은 **selectors / services 패턴** 을 얹어, 조회와 변경 책임을 모듈 단위로 분리한다.

## 디렉터리 구조 (요약)

```
HomeN-server/
├─ apps/
│  ├─ users/                # Auth + 본인 프로필
│  │  ├─ models.py          # User, SocialAccount, UserProfileImage enum
│  │  ├─ selectors.py       # 순수 조회 함수 (read-only)
│  │  ├─ services.py        # 변경 + 도메인 예외
│  │  ├─ serializers.py     # DRF 입출력 + swagger help_text
│  │  ├─ views.py           # APIView + @extend_schema
│  │  ├─ urls.py            # auth_urlpatterns, user_urlpatterns
│  │  ├─ migrations/
│  │  └─ tests/
│  └─ homes/                # 집 + 집안일 + 스타터팩
│     ├─ models.py
│     ├─ selectors.py
│     ├─ services.py
│     ├─ serializers.py
│     ├─ views.py
│     ├─ urls.py
│     ├─ migrations/
│     └─ tests/
├─ common/
│  └─ exceptions.py         # DRF custom_exception_handler
├─ config/
│  ├─ settings.py           # Django settings + SPECTACULAR_SETTINGS
│  ├─ urls.py               # /api/v1/<context>/ 마운트, /api/docs/, /api/schema/
│  ├─ asgi.py / wsgi.py
├─ specs/                   # SDD 스펙 문서 (도메인 명세)
├─ docs/                    # 본 문서들
└─ manage.py / main.py
```

## 레이어 책임 (각 앱 내부)

| 파일 | 책임 | 절대 하지 말 것 |
|---|---|---|
| `models.py` | DB 스키마, enum (`IntegerChoices`/`TextChoices`), 프로퍼티 (`is_profile_set` 같은 파생 값). | HTTP / 시리얼라이저 import |
| `selectors.py` | **읽기 전용** 함수. ORM 쿼리, `select_related`/`prefetch_related`, 단순 변환. | `save()`, `delete()`, transaction. |
| `services.py` | 변경 함수 (생성·수정·삭제). 도메인 예외 정의·발생. transaction 경계. | DRF / `Request` import. View 가 의존하는 시리얼라이저 import 도 ❌. |
| `serializers.py` | DRF 입력 유효성, 출력 직렬화, swagger `help_text` / `examples`. | services 호출. |
| `views.py` | 요청 검증 → `services.*` 호출 → 도메인 예외를 DRF 표준 예외(`ValidationError`, `PermissionDenied`, `NotFound`) 로 매핑 → 응답. | 비즈니스 로직 직접 작성. |
| `urls.py` | path 매핑. 외부 라이브러리 View 에 swagger 데코레이터 부착. | View 로직 인라인. |

## 도메인 예외 → HTTP 매핑

모든 도메인 예외는 `services.py` 안에 정의된 **앱-내부 Exception 클래스**다. 컨트롤러가 이를 catch 해서 DRF 표준 예외로 매핑한다. 매핑 표는 [`api-conventions.md §6`](api-conventions.md#6-상태-코드) 참조.

예: `apps/homes/services.py` 의 도메인 예외들

| 예외 | 의미 | 매핑되는 응답 |
|---|---|---|
| `AlreadyHasHomeError` | 이미 다른 집에 속함 | `400` `{ "already_has_home": "..." }` |
| `HomeNotFoundError` | 초대코드/집 미존재 | `404` |
| `NotHomeAdminError` | 관리자 전용 작업 위반 | `403` |
| `HomeHasMembersError` | 집 삭제 시 구성원 남아 있음 | `400` `{ "home_has_members": "..." }` |
| `AdminCannotLeaveError` | 관리자가 양도 없이 나가려 함 | `403` |
| `TransferAdminTargetError` | 양도 대상이 같은 집의 구성원이 아님 | `400` `{ "transfer_admin_target": "..." }` |
| `HomeChoreNotFoundError` | 집안일 PK 가 없거나 다른 집 소유 | `404` |

## Request 라이프사이클

1. `rest_framework_simplejwt.authentication.JWTAuthentication` 이 `Authorization: Bearer ...` 를 검증.
2. View 의 `permission_classes` (기본 `IsAuthenticated`, 소셜 로그인만 `AllowAny`) 가 권한 게이트.
3. `*Serializer(data=request.data).is_valid(raise_exception=True)` 로 입력 유효성 검증.
4. `services.<verb>(user=request.user, **validated_data)` 호출. 트랜잭션이 필요하면 `services` 내부에서 `transaction.atomic()`.
5. 도메인 예외 → DRF 표준 예외 매핑.
6. `Response(OutputSerializer(result).data, status=...)` 응답.
7. 처리되지 않은 예외는 `common.exceptions.custom_exception_handler` 가 잡아 표준 형식으로 응답.

## 인증

- **JWT (SimpleJWT)**: access (1h) + refresh (7d). `SIMPLE_JWT.AUTH_HEADER_TYPES=("Bearer",)`.
- **소셜 로그인**: 카카오/애플 인가코드 → 서버가 SSO 토큰 교환 → `SocialAccount` 와 매칭되는 `User` 발견/생성 → JWT 발급.
- **로그아웃**: `rest_framework_simplejwt.token_blacklist` 의 블랙리스트에 refresh 등록.
- **회원 탈퇴**: 집 관리자는 직접 탈퇴 불가 (양도 또는 집 삭제 선행). Apple 가입자는 `SocialAccount.refresh_token` 으로 token revocation 호출.

## 새 코드는 어디에? (빠른 결정 가이드)

1. `from django.db import models` 만 사용하는 데이터 정의 → `models.py`
2. SELECT 만 하는 함수 → `selectors.py`
3. INSERT/UPDATE/DELETE 또는 transaction 이 필요한 변경 함수 → `services.py`
4. 새 예외 — 도메인 의미를 갖는다면 `services.py` 의 Exception 클래스로 정의 → `views.py` 가 catch 후 DRF 표준 예외로 매핑
5. DRF 입출력 — `serializers.py` (swagger `help_text` 필수, examples 권장)
6. HTTP 라우팅 → `urls.py`
7. 컨트롤러 본체 (`@extend_schema` + method 핸들러) → `views.py`
8. 여러 앱이 공유하는 유틸/예외 핸들러 → `common/`

## 알려진 단순화 / 약속

- **DTO 레이어 없음**: services 가 시리얼라이저의 `validated_data` 를 kwargs 로 풀어 받는다. 도메인 객체로의 변환은 services 내부에서 수행한다. DTO 클래스를 별도로 두지 않는 이유는 Django ORM 객체가 이미 도메인 객체로 충분하기 때문.
- **Repository 패턴 없음**: ORM 쿼리는 `selectors.py` / `services.py` 안에서 직접 호출한다. 추상화 비용 대비 이득이 크지 않음.
- **services 가 `request.user` 의 ORM 객체를 직접 받음**: 테스트에서 `MagicMock(User)` 대신 실제 `User` 인스턴스를 픽스처로 만든다 (`factories.py` 참조).
- **transaction 경계**: 기본은 Django 의 ATOMIC_REQUESTS 미사용. `services` 함수가 다단계 쓰기를 한다면 `@transaction.atomic` 또는 `with transaction.atomic():` 로 명시한다.

## 참고 자료

- [Django Documentation](https://docs.djangoproject.com/)
- [Django REST Framework](https://www.django-rest-framework.org/)
- [SimpleJWT](https://django-rest-framework-simplejwt.readthedocs.io/)
- [drf-spectacular](https://drf-spectacular.readthedocs.io/)
- HackSoftware, "Django Styleguide" — https://github.com/HackSoftware/Django-Styleguide (selectors/services 패턴의 정본)

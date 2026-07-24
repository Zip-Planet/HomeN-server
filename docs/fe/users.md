# 유저 / 인증(Users · Auth) FE 연동 가이드

> 대상: 프론트엔드
> 앱 경로: `apps/users/`
> 관련 코드: `apps/users/urls.py`, `apps/users/views.py`, `apps/users/serializers.py`
> 스펙: `specs/users.md`

---

## 1. 개요

카카오 / 애플 **소셜 로그인(SSO) 전용** 도메인이다. 이메일·비밀번호 인증은 지원하지 않는다.
소셜 제공자의 고유 ID(`provider_id`)로 유저를 식별하며, 인증 성공 시 서버가 자체 JWT
(access + refresh)를 발급한다.

- **인증 방식**: 발급받은 access 토큰을 `Authorization: Bearer <access>` 헤더로 전달한다.
- **온보딩 분기**: 로그인 응답의 `is_profile_set`(닉네임+이미지 설정 여부)과 `has_home`
  (집 소속 여부)로 온보딩 / 메인 진입을 결정한다.
- **카카오·애플은 별개 계정**으로 관리된다(자동 연동 없음). 이메일은 저장하지 않는다.

---

## 2. 공통

### 2.1 Base URL prefix

| 그룹 | prefix | 엔드포인트 |
| --- | --- | --- |
| Auth | `/api/v1/auth/` | `kakao/`, `apple/`, `logout/`, `token/refresh/` |
| Users | `/api/v1/users/` | `me/`, `profile-images/`, `nicknames/<nickname>/` |

### 2.2 공통 헤더

| 헤더 | 값 | 적용 대상 |
| --- | --- | --- |
| `Authorization` | `Bearer <access>` | 인증 필요 엔드포인트 (`logout`, `users/me`, `nicknames`) |
| `Content-Type` | `application/json` | body 를 보내는 POST/PATCH |

### 2.3 토큰 정책

| 항목 | 값 | 비고 |
| --- | --- | --- |
| access 토큰 만료 | 기본 1시간 | `SIMPLE_JWT.ACCESS_TOKEN_LIFETIME` |
| refresh 토큰 만료 | 기본 7일 | 로그아웃 시 블랙리스트 등록 |
| 갱신 | `POST /auth/token/refresh/` | refresh 회전(rotation) 여부는 서버 설정에 의존 |

### 2.4 에러 응답 공통 형식

모든 에러는 다음 형태로 내려온다.

```json
{ "error": { "code": "authentication_failed", "message": "..." } }
```

---

## 3. 엔드포인트별 상세

### 3.1 `POST /api/v1/auth/kakao/`

카카오 OAuth2 인가 코드(`code`)로 access/refresh JWT 를 발급한다. 신규 유저는 자동
가입되며, 재로그인은 `provider_id` 로 매칭된다. **인증 불필요**(AllowAny).

**요청 (body)**

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| body | `code` | string | ✓ | 카카오 OAuth2 콜백으로 전달된 1회용 인가 코드 |
| body | `redirect_uri` | string |  | FE 가 authorize 에 쓴 redirect_uri. **인가 코드 발급 때와 글자 단위로 동일**해야 함(불일치 시 카카오 KOE320). 접속 위치(집 LAN·외부)별로 값이 다른 환경에서 함께 전송. 생략/빈 문자열 시 서버 `KAKAO_REDIRECT_URI` 폴백. 네이티브 스킴(`kakao{앱키}://...`)이면 네이티브 앱 키로 교환 |

**응답 (200)**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `access` | string | JWT 액세스 토큰 (기본 1시간) |
| `refresh` | string | JWT 리프레시 토큰 (기본 7일) |
| `is_profile_set` | boolean | 닉네임+이미지 모두 설정됐는지 여부 (false면 온보딩) |
| `has_home` | boolean | 집 관리자/구성원으로 소속됐는지 여부 |

```json
{
  "access": "eyJhbGciOiJIUzI1NiIs...",
  "refresh": "eyJhbGciOiJIUzI1NiIs...",
  "is_profile_set": false,
  "has_home": false
}
```

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 400 | `invalid` | `code` 누락/빈 문자열 |
| 401 | `authentication_failed` | 카카오 토큰 교환 실패, 만료된 코드 |

---

### 3.2 `POST /api/v1/auth/apple/`

Apple Sign In 인가 코드(`code`)로 access/refresh JWT 를 발급한다. Apple `refresh_token`
은 탈퇴 시 token revocation 을 위해 서버에 저장된다. **인증 불필요**(AllowAny).

**요청 (body)**

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| body | `code` | string | ✓ | Apple Sign In 콜백으로 전달된 1회용 인가 코드 |

**응답 (200)**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `access` | string | JWT 액세스 토큰 (기본 1시간) |
| `refresh` | string | JWT 리프레시 토큰 (기본 7일) |
| `is_profile_set` | boolean | 닉네임+이미지 모두 설정됐는지 여부 |
| `has_home` | boolean | 집 관리자/구성원으로 소속됐는지 여부 |

```json
{
  "access": "eyJhbGciOiJIUzI1NiIs...",
  "refresh": "eyJhbGciOiJIUzI1NiIs...",
  "is_profile_set": false,
  "has_home": false
}
```

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 400 | `invalid` | `code` 누락 |
| 401 | `authentication_failed` | Apple 토큰 교환 실패, id_token 검증 실패 |

---

### 3.3 `POST /api/v1/auth/token/refresh/`

보유 중인 refresh 토큰으로 새 access 토큰을 발급한다. refresh 회전(rotation) 여부는
서버 `SIMPLE_JWT` 설정에 의존한다. **인증 불필요**(refresh 토큰 자체로 검증).

**요청 (body)**

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| body | `refresh` | string | ✓ | JWT refresh 토큰 |

**응답 (200)**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `access` | string | 신규 access 토큰 |
| `refresh` | string | (회전 ON 시에만) 신규 refresh 토큰 |

```json
{ "access": "eyJhbGciOiJIUzI1NiIs...new_access..." }
```

회전(rotation) ON 설정일 경우:

```json
{
  "access": "eyJhbGciOiJIUzI1NiIs...new_access...",
  "refresh": "eyJhbGciOiJIUzI1NiIs...new_refresh..."
}
```

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 400 | `invalid` | refresh 형식 오류 (필드 누락 등) |
| 401 | `token_not_valid` | refresh 만료/위조/블랙리스트 |

---

### 3.4 `POST /api/v1/auth/logout/`

보유 중인 refresh 토큰을 SimpleJWT 블랙리스트에 등록해 추가 갱신을 차단한다. access
토큰은 자체 무효화 없이 만료까지 유효하다. **인증 필요**(Bearer access).

**요청 (body)**

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| body | `refresh` | string | ✓ | 블랙리스트에 등록할 refresh 토큰 |

**응답 (204)**

응답 본문 없음.

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 400 | `invalid_token` | 토큰이 유효하지 않거나 이미 블랙리스트 |
| 401 | `authentication_failed` | access 토큰 누락/만료 |

---

### 3.5 `GET /api/v1/users/me/`

현재 access 토큰 소유 유저의 프로필을 반환한다. 신규 가입 직후에는 `name` 이 빈 문자열,
`profile_image`/`home_role` 이 null 일 수 있다. **인증 필요**(Bearer access).

**요청**: 요청 본문 없음.

**응답 (200)**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `uid` | string (uuid) | 유저 고유 식별자. 클라이언트와의 모든 매칭은 이 값으로 수행 |
| `name` | string | 닉네임 (1~8자, 미설정 시 빈 문자열 `""`) |
| `profile_image` | integer \| null | 프로필 이미지 enum (미설정 시 null) |
| `is_profile_set` | boolean | 닉네임+이미지 모두 설정 여부 |
| `has_home` | boolean | 집 소속 여부 |
| `home_role` | integer \| null | 1=관리자, 2=구성원, 집 없으면 null |

```json
{
  "uid": "8f3e2b1a-1234-4abc-9def-1234567890ab",
  "name": "홍길동",
  "profile_image": 3,
  "is_profile_set": true,
  "has_home": true,
  "home_role": 1
}
```

온보딩 미완료(신규 가입 직후) 예시:

```json
{
  "uid": "8f3e2b1a-1234-4abc-9def-1234567890ab",
  "name": "",
  "profile_image": null,
  "is_profile_set": false,
  "has_home": false,
  "home_role": null
}
```

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | access 토큰 누락/만료 |

---

### 3.6 `PATCH /api/v1/users/me/`

닉네임과 프로필 이미지를 함께 갱신한다. **온보딩(최초 설정)과 변경 모두 동일
엔드포인트**를 사용한다. **인증 필요**(Bearer access).

**요청 (body)**

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| body | `name` | string | ✓ | 닉네임 (한글·영문·숫자 1~8자, 공백/특수문자 불가, 전역 유일) |
| body | `profile_image` | integer | ✓ | 프로필 이미지 enum. `/users/profile-images/` 목록 중 하나 |

**응답 (200)**

변경 후 최신 프로필. 필드 구조는 `GET /users/me/` 와 동일하다.

```json
{
  "uid": "8f3e2b1a-1234-4abc-9def-1234567890ab",
  "name": "홍길동",
  "profile_image": 3,
  "is_profile_set": true,
  "has_home": true,
  "home_role": 1
}
```

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 400 | `invalid` | 형식 위반 (특수문자, 길이 초과 등) |
| 400 | `duplicate_nickname` | 이미 사용 중인 닉네임 |
| 401 | `authentication_failed` | access 토큰 누락/만료 |

---

### 3.7 `DELETE /api/v1/users/me/`

현재 유저를 탈퇴 처리한다. **집 관리자는 직접 탈퇴할 수 없고** 관리자 양도 또는 집
삭제가 선결되어야 한다. Apple 가입자는 저장된 refresh_token 으로 token revocation 까지
처리한다. **인증 필요**(Bearer access).

**요청**: 요청 본문 없음.

**응답 (204)**

응답 본문 없음.

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | access 토큰 누락/만료 |
| 403 | `home_admin_cannot_withdraw` | 집 관리자는 양도 또는 집 삭제 후 탈퇴 가능 |

---

### 3.8 `GET /api/v1/users/profile-images/`

선택 가능한 프로필 이미지 enum 정수 목록을 반환한다. **인증 불필요**(AllowAny) —
회원가입 전 온보딩 미리보기에도 사용된다. FE 는 응답의 `id` 를 그대로
`PATCH /users/me/` 의 `profile_image` 로 전송한다.

**요청**: 파라미터 없음.

**응답 (200)** — 배열

| 위치 | 필드 | 타입 | 설명 |
| --- | --- | --- | --- |
| body[*] | `id` | integer | 프로필 이미지 enum ID |

```json
[{ "id": 1 }, { "id": 2 }, { "id": 3 }, { "id": 4 }, { "id": 5 }]
```

---

### 3.9 `GET /api/v1/users/nicknames/<nickname>/`

주어진 닉네임을 다른 유저가 점유 중인지 확인한다. **존재 여부만** 확인하며, 형식
검증(특수문자 등)은 `PATCH /users/me/` 시점에 수행된다. **인증 필요**(Bearer access).

**요청 (path)**

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| path | `nickname` | string | ✓ | 확인할 닉네임 (URL 인코딩 가능) |

**응답 (200)**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `is_available` | boolean | true=사용 가능, false=이미 사용 중 |

```json
{ "is_available": true }
```

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | access 토큰 누락/만료 |

---

## 4. enum / 상태값 정리

### 4.1 `home_role` (내 프로필의 집 역할)

| 값 | 의미 |
| --- | --- |
| `1` | 관리자 |
| `2` | 구성원 |
| `null` | 집에 소속되지 않음 |

### 4.2 `profile_image`

- 프로필 이미지 enum **정수**로 내려온다. FE 는 정수 → 실제 이미지 매핑을 담당한다.
- 선택 가능한 값 목록은 `GET /users/profile-images/` 응답의 `id` 로 확인한다.
- 미설정 시 `null`.

### 4.3 로그인 응답 분기 플래그

| 필드 | true 조건 | FE 처리 |
| --- | --- | --- |
| `is_profile_set` | 닉네임+이미지 모두 설정 | false면 온보딩(프로필 설정) 화면으로 |
| `has_home` | 집 관리자/구성원 소속 | false면 집 생성/참여 화면으로 |

---

## 5. FE 연동 팁 / 주의사항

### 5.1 소셜 로그인 흐름

1. 카카오/애플 OAuth2 로 인가 코드(`code`)를 획득한다.
2. `POST /auth/kakao/` 또는 `POST /auth/apple/` 로 `code` 를 전달해 access/refresh 를 받는다.
   - 카카오는 접속 환경별로 `redirect_uri` 가 다르면 **authorize 때와 동일한 값**을 함께 보낸다.
3. 응답의 `is_profile_set` → false면 온보딩, `has_home` → false면 집 생성/참여로 분기한다.

### 5.2 토큰 갱신 흐름

- access 만료(기본 1시간) 시 `POST /auth/token/refresh/` 로 새 access 를 발급받아 재요청한다.
- 회전(rotation) ON 설정이면 응답에 새 `refresh` 도 포함되므로, **응답에 `refresh` 가 있으면
  저장 값을 교체**한다.
- refresh 가 401(`token_not_valid`)이면 재로그인으로 유도한다.

### 5.3 로그아웃

- `POST /auth/logout/` 은 Bearer access 헤더와 body 의 `refresh` 를 **모두** 필요로 한다.
- 성공 시 204(본문 없음). access 토큰은 만료 전까지 유효하므로 클라이언트에서도 폐기한다.

### 5.4 온보딩 / 프로필 수정

- 닉네임 실시간 검증은 `GET /users/nicknames/<nickname>/` 로 사용 가능 여부를 미리 확인하되,
  **형식 검증(특수문자·길이)은 `PATCH /users/me/` 가 최종 판정**한다. 사전 확인은 존재 여부만 반영한다.
- 프로필 이미지는 `GET /users/profile-images/` 의 `id` 를 그대로 `profile_image` 로 전송한다.

### 5.5 회원 탈퇴

- 집 관리자는 `DELETE /users/me/` 시 403(`home_admin_cannot_withdraw`)이 발생한다.
  관리자 양도 또는 집 삭제를 먼저 유도한다.

### 5.6 Swagger 예시 주의

- 자동 생성 문서(Swagger)의 일부 응답 예시에는 `is_profile_set`/`has_home` 가 누락되거나,
  `home_role` 이 문자열(`"admin"`/`"member"`)로 표기된 축약본이 섞여 있다.
  **실제 응답은 위 표 기준**이며 `home_role` 은 정수(1/2/null)로 내려오므로, 실제 응답을 기준으로 파싱한다.
</content>
</invoke>

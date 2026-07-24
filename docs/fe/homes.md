# Homes 도메인 FE 연동 가이드

> 대상: 프론트엔드
> 앱: `apps/homes/`
> Base URL: `/api/v1/homes/`, `/api/v1/starter-packs/`
> 관련 코드: `apps/homes/urls.py`, `apps/homes/views.py`, `apps/homes/serializers.py`, `specs/homes.md`

---

## 1. 개요

집(Home) 도메인은 **집 생성/관리 → 구성원 초대/참여 → 집안일 등록/수정/완료 처리 → 메모 → 대시보드**
까지의 흐름을 담당한다. 스타터팩(집안일 프리셋)도 본 도메인에서 조회한다.

핵심 도메인 규칙:

- **한 유저는 하나의 집에만 속한다.** 다른 집에 참여하려면 먼저 나가야 한다.
- **집당 관리자(role=1)는 1명.** 집 생성자가 자동으로 관리자가 된다.
- **관리자 전용 동작**: 집 삭제, 관리자 양도, (분담안 생성/재생성/확정 → `assignments.md`).
- **구성원 누구나 가능**: 집안일 추가/수정/삭제/복구, 메모 작성, 완료 처리(단, 본인 배정분).
- 집안일 **삭제는 soft-delete**(이력 있으면 `is_active=false`), **수정은 copy-on-write**(원본 보존).

> **분담안(주차별 집안일 배정)** 관련 엔드포인트(`GET/POST /mine/assignments/...`,
> 재생성/확정/히스토리)는 본 문서에서 다루지 않는다. **분담안은 `assignments.md` 참조.**

---

## 2. 공통

### 2.1 Base URL / 인증

| 항목 | 값 |
| --- | --- |
| 집 관련 prefix | `/api/v1/homes/` |
| 스타터팩 prefix | `/api/v1/starter-packs/` |
| 인증 헤더 | `Authorization: Bearer <access>` (모든 엔드포인트 필수) |
| 요청 본문 타입 | `Content-Type: application/json` |

토큰 누락/만료 시 공통으로 **401 `authentication_failed`** 를 반환한다. 아래 각 엔드포인트의
에러 표에서 401 은 이 공통 케이스이며 별도 반복 설명은 생략할 수 있다.

### 2.2 에러 응답 포맷

모든 에러는 다음 공통 구조로 내려온다.

```json
{ "error": { "code": "already_has_home", "message": "이미 속한 집이 있습니다." } }
```

FE 는 `error.code` 로 분기하고, `error.message` 는 사용자 노출용 문구로 사용한다.

### 2.3 권한 구분

| 구분 | 대상 | 해당 엔드포인트 |
| --- | --- | --- |
| **관리자 전용** | role=1 | 집 삭제, 관리자 양도 |
| **구성원 누구나** | role=1·2 | 집안일 CRUD·복구, 메모 작성, 집/집안일 조회, 대시보드 |
| **작성자 본인만** | 메모 author | 메모 수정/삭제 |
| **담당자 본인만** | 분담안 배정자 | 완료 처리 |
| **완료자 본인만** | 완료 기록자 | 완료 취소 |

### 2.4 공통 객체 구조

**구성원(member)** — 집 조회/초대 미리보기의 `members[]` 원소:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `name` | string | 닉네임 |
| `profile_image` | integer\|null | 프로필 이미지 enum (미설정 시 null) |
| `role` | integer | 1=관리자, 2=구성원 |
| `role_label` | string | '관리자' / '구성원' |

**작성자/담당자/완료자(user)** — 메모·완료·분담안 항목의 유저 표현:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `uid` | string(uuid) | 유저 uid |
| `name` | string | 닉네임 |
| `profile_image` | integer\|null | 프로필 이미지 enum |

---

# 📦 섹션 A. 집 관리

## A-1. `GET /api/v1/homes/images/`

선택 가능한 **집 프로필 이미지 enum 목록**을 반환한다. 집 생성 시 `image_id` 로 그대로 전송한다.

### 요청
파라미터 없음.

### 응답 (200)

배열. 각 원소 `{ "id": integer }` (1~8).

```json
[{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}, {"id": 5}, {"id": 6}, {"id": 7}, {"id": 8}]
```

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 토큰 누락/만료 |

---

## A-2. `POST /api/v1/homes/`

집을 생성한다. **호출자가 자동으로 관리자(role=1)로 등록**된다. 집안일은
`starter_pack_id` 또는 `chores` 중 **하나만** 지정하며, 둘 다 비워도 된다(집만 생성).

### 요청 (body)

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `name` | string | ✓ | 집 이름 (한글·영문·숫자·공백 1~10자, 공백 단독 불가) |
| `image_id` | integer | ✓ | 집 이미지 enum (1~8) |
| `starter_pack_id` | integer\|null | - | 적용할 스타터팩 PK. `chores` 와 동시 사용 불가 |
| `starter_pack_chore_ids` | integer[]\|null | - | 스타터팩 중 실제 적용할 Chore PK 목록. 생략/null=팩 전체, `[]`=아무것도 미적용 |
| `chores` | array | - | 사용자 정의 집안일 목록. `starter_pack_id` 와 동시 사용 불가 |
| `chores[].category` | integer | ✓ | 카테고리 (1=쓰레기, 2=욕실, 3=청소, 4=주방, 5=세탁) |
| `chores[].name` | string | ✓ | 집안일 제목 (1~20자) |
| `chores[].description` | string | - | 설명 (최대 20자, 기본 "") |
| `chores[].repeat_days` | integer[] | ✓ | 반복 요일 (0=월 ~ 6=일). 최소 1개 |
| `chores[].difficulty` | integer | ✓ | 난이도 (1=하 ~ 5=상) |
| `rewards` | array | - | 함께 등록할 리워드 목록 |
| `rewards[].name` | string | ✓ | 리워드 이름 (최대 50자) |
| `rewards[].goal_point` | integer | ✓ | 목표 포인트 (1 이상) |

### 응답 (201)

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | integer | 집 PK |
| `name` | string | 집 이름 |
| `image` | integer | 집 이미지 enum |
| `invite_code` | string | 6자리 대문자+숫자 초대코드 |
| `status` | string | `active`(활성) / `draft`(생성 중) |
| `created_at` | string(datetime) | 생성 일시 (ISO 8601) |
| `members` | array | 구성원 목록 (관리자 본인 포함, [공통 member 구조](#24-공통-객체-구조)) |

```json
{
  "id": 12,
  "name": "우리집",
  "image": 1,
  "invite_code": "AB12CD",
  "status": "active",
  "created_at": "2026-05-13T12:00:00Z",
  "members": [
    {"name": "홍길동", "profile_image": 3, "role": 1, "role_label": "관리자"}
  ]
}
```

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 400 | `already_has_home` | 이미 다른 집에 속해 있음 |
| 400 | `ambiguous_chore_input` | `starter_pack_id` 와 `chores` 동시 지정 |
| 400 | `invalid` | 이름 형식 위반 / image_id 무효 등 |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 404 | `not_found` | `starter_pack_id` 에 해당하는 스타터팩 없음 |

---

## A-3. `GET /api/v1/homes/mine/`

본인이 속한 집의 상세 정보를 조회한다. **속한 집이 없으면 404** — 소속 여부만 확인하려면
`A-5 membership` 사용.

### 요청
본문 없음.

### 응답 (200)

필드는 **A-2 응답과 동일** (`id`, `name`, `image`, `invite_code`, `status`, `created_at`, `members`).

```json
{
  "id": 12,
  "name": "우리집",
  "image": 1,
  "invite_code": "AB12CD",
  "status": "active",
  "created_at": "2026-05-13T12:00:00Z",
  "members": [
    {"name": "홍길동", "profile_image": 3, "role": 1, "role_label": "관리자"},
    {"name": "김철수", "profile_image": 2, "role": 2, "role_label": "구성원"}
  ]
}
```

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 404 | `not_found` | 속한 집 없음 |

---

## A-4. `DELETE /api/v1/homes/mine/` (관리자 전용)

본인이 관리자인 집을 삭제한다. **구성원이 남아있으면 삭제 불가**(400) — 양도 후 나가거나
구성원이 모두 나간 뒤 호출한다.

### 요청
본문 없음.

### 응답 (204)
본문 없음.

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 400 | `home_has_members` | 구성원이 남아있어 삭제 불가 |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 403 | `permission_denied` | 관리자만 삭제 가능 |

---

## A-5. `GET /api/v1/homes/mine/membership/`

집 소속 여부만 가볍게 확인한다. **속한 집이 없어도 404 가 아닌 200** 을 반환한다.
로그인 후 홈 진입 vs 온보딩(집 생성/참여) 화면 분기용.

### 요청
본문 없음.

### 응답 (200)

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `has_home` | boolean | 집 관리자/구성원 소속 여부 |

```json
{"has_home": true}
```

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 토큰 누락/만료 |

---

## A-6. `POST /api/v1/homes/mine/leave/` (구성원 전용)

현재 유저가 집을 나간다. **관리자는 직접 나갈 수 없다** — 양도(A-7) 후 호출하거나
단독이면 집을 삭제(A-4)해야 한다.

### 요청
본문 없음.

### 응답 (204)
본문 없음.

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 403 | `admin_cannot_leave` | 관리자는 양도 또는 집 삭제 후 나가야 함 |
| 404 | `not_found` | 속한 집 없음 |

---

## A-7. `POST /api/v1/homes/mine/transfer-admin/` (관리자 전용)

관리자 권한을 **같은 집의 구성원**에게 양도한다. 완료 시 호출자는 구성원, 대상은 관리자가 된다.

### 요청 (body)

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `user_id` | string(uuid) | ✓ | 양도받을 대상 유저의 uid. 반드시 같은 집의 구성원 |

### 응답 (204)
본문 없음.

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 400 | `transfer_admin_target` | 대상이 같은 집 구성원이 아니거나 본인 |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 403 | `permission_denied` | 관리자만 양도 가능 |

---

## A-8. `GET /api/v1/homes/mine/dashboard/`

홈 탭 상단(T1_HomeDashboard)을 한 번에 그리기 위한 집계 응답. 이번 주 진행률·내 기여도·
MVP·다음 주 분담안 상태·이번 주 항목 목록을 함께 반환한다.

### 요청
본문 없음.

### 응답 (200)

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `home` | object | `{id, name, image, member_count}` |
| `this_week.week_start` | date | 이번 주 월요일 |
| `this_week.assignment_id` | integer\|null | 이번 주 분담안 PK. 없으면 null |
| `this_week.status` | string\|null | `proposed`/`confirmed`/`expired`. 없으면 null |
| `this_week.total_count` | integer | 이번 주 전체 항목 수 |
| `this_week.completed_count` | integer | 완료 항목 수 |
| `this_week.progress_rate` | integer | 진행률 % (완료/전체, 반올림) |
| `this_week.my_contribution_rate` | integer | 내 기여도 % (내 완료 포인트/집 전체 완료 포인트) |
| `this_week.mvp` | object\|null | `{uid, name, profile_image, point, completed_count}`. 완료 이력 없으면 null |
| `next_week.week_start` | date | 다음 주 월요일 |
| `next_week.assignment_id` | integer\|null | 다음 주 분담안 PK. 없으면 null |
| `next_week.status` | string\|null | `proposed`/`confirmed`. null 이면 화면에 '생성 필요' + 레드닷 |
| `items[]` | array | 이번 주 분담안 항목 목록(멤버 필터 탭용). 분담안 없으면 `[]` |

> `items[]` 원소 구조는 분담안 항목과 동일하다 → **`assignments.md` 참조.**
> (`id, home_chore_id, weekday, weekday_label, chore_name, category, difficulty, point, assignee, date, is_completed` 등)

```json
{
  "home": {"id": 1, "name": "골든빌401", "image": 1, "member_count": 3},
  "this_week": {
    "week_start": "2026-01-26",
    "assignment_id": 7,
    "status": "confirmed",
    "total_count": 25,
    "completed_count": 16,
    "progress_rate": 64,
    "my_contribution_rate": 72,
    "mvp": {"uid": "…", "name": "투다리김치우동", "profile_image": 1, "point": 560, "completed_count": 7}
  },
  "next_week": {"week_start": "2026-02-02", "assignment_id": 8, "status": "proposed"},
  "items": []
}
```

- **진행률** = 완료 항목 수 / 전체 항목 수.
- **기여도** = 내가 완료한 포인트 / 집 전체 완료 포인트 (배정 담당자가 아닌 **실제 완료자** 기준).
- **MVP** = 완료 포인트 최고 구성원 (동점이면 완료 건수 우선).

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 404 | `not_found` | 속한 집 없음 |

---

# 🧹 섹션 B. 집안일

집안일은 마스터 `Chore` 를 집에 연결한 `HomeChore` 단위로 노출된다. 응답의 `id` 는 항상
**HomeChore PK** 이며, 메모·완료·복구 경로의 부모 식별자로 쓰인다.

**공통 집안일 응답 필드** (B-1 목록 / B-2 추가 / B-3 상세 / B-4 수정 / B-6 복구 공용):

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | integer | HomeChore PK |
| `category` | integer | 카테고리 enum (1=쓰레기 ~ 5=세탁) |
| `category_label` | string | 카테고리 한글 |
| `name` | string | 집안일 제목 |
| `description` | string | 설명 (없으면 "") |
| `repeat_days` | integer[] | 반복 요일 (0=월 ~ 6=일) |
| `repeat_days_label` | string[] | 반복 요일 한글 (예: `["월","목"]`) |
| `difficulty` | integer | 난이도 enum (1~5) |
| `difficulty_label` | string | 3단계 라벨: '쉬움'(1~2)/'중간'(3~4)/'어려움'(5) |
| `point` | integer | 난이도 고정 포인트: 40/80/120/160/200 |
| `is_active` | boolean | 활성 여부. false 면 삭제(비활성)된 집안일 (상세·목록/추가/수정 응답 중 상세·복구에 포함) |

> `point` 는 난이도에 1:1 로 묶인 자동 고정 값이며 **직접 입력 불가**.
> `is_active` 는 목록/상세/복구 응답에 포함되고, 목록(B-1)은 활성 항목만 반환한다.

---

## B-1. `GET /api/v1/homes/mine/chores/`

속한 집의 **활성** 집안일을 PK 오름차순으로 반환한다. 삭제(비활성)된 집안일은 제외.
비어 있으면 `200 + []`.

### 요청
본문 없음.

### 응답 (200)

배열. 각 원소는 위 [공통 집안일 응답 필드](#-섹션-b-집안일).

```json
[
  {
    "id": 1,
    "category": 3, "category_label": "청소",
    "name": "거실 청소", "description": "주 1회",
    "repeat_days": [0, 3], "repeat_days_label": ["월", "목"],
    "difficulty": 2, "difficulty_label": "쉬움", "point": 80,
    "is_active": true
  }
]
```

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 404 | `not_found` | 속한 집 없음 |

---

## B-2. `POST /api/v1/homes/mine/chores/`

집에 집안일을 추가한다. **`starter_pack_id` 또는 `chores` 중 정확히 하나**만 지정한다
(둘 다 비면 400). 스타터팩 적용 시 이미 있는 chore 는 skip(멱등).

### 요청 (body)

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `starter_pack_id` | integer\|null | - | 적용할 스타터팩 PK. `chores` 와 동시 사용 불가 |
| `starter_pack_chore_ids` | integer[]\|null | - | 팩 중 적용할 Chore PK 목록. 생략/null=팩 전체, `[]`=미적용 |
| `chores` | array | - | 사용자 정의 집안일 목록 (단건도 길이 1 배열) |
| `chores[].category` | integer | ✓ | 카테고리 (1~5) |
| `chores[].name` | string | ✓ | 집안일 제목 (1~20자) |
| `chores[].description` | string | - | 설명 (최대 20자, 기본 "") |
| `chores[].repeat_days` | integer[] | ✓ | 반복 요일 (0=월 ~ 6=일). 최소 1개 |
| `chores[].difficulty` | integer | ✓ | 난이도 (1~5) |

### 응답 (201)

배열 — 신규 생성된 HomeChore 만 (스타터팩 skip 항목 제외). 각 원소는 공통 집안일 필드.

```json
[
  {
    "id": 1, "category": 3, "category_label": "청소",
    "name": "거실 청소", "description": "",
    "repeat_days": [0], "repeat_days_label": ["월"],
    "difficulty": 2, "difficulty_label": "쉬움", "point": 80
  }
]
```

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 400 | `ambiguous_chore_input` | `starter_pack_id` 와 `chores` 동시 지정 |
| 400 | `missing_chore_input` | 둘 다 비어 있음 |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 404 | `not_found` | 속한 집 없음 또는 `starter_pack_id` 미존재 |

---

## B-3. `GET /api/v1/homes/mine/chores/{home_chore_id}/`

집안일 한 건 상세조회. 본인 집이 아니면 **존재 비노출로 항상 404**. 삭제(비활성)된
집안일도 상세 조회는 가능하다(`is_active=false`). **이번 주 진행상태**(`weekly_progress`)를 포함한다.

### 요청 (path)

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `home_chore_id` | integer | ✓ | 조회할 HomeChore PK |

### 응답 (200)

공통 집안일 필드 + `weekly_progress` (월~일 7개 원소).

`weekly_progress[]` 원소:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `weekday` | integer | 0=월 ~ 6=일 |
| `label` | string | 한글 요일 |
| `status` | string | `completed` / `incomplete` / `not_scheduled` |
| `completed_by` | object\|null | `status=completed` 시 완료자 `{uid, name, profile_image}`. 아니면(또는 탈퇴 유저) null |

상태값 정의:
- `completed` — 그 요일의 이번 주 날짜에 완료 이력이 있다(**집 단위** — 누가 끝내도 completed).
- `incomplete` — `repeat_days` 에 포함되지만 이번 주 완료 이력 없음.
- `not_scheduled` — `repeat_days` 에 포함되지 않은 요일.

```json
{
  "id": 12, "category": 3, "category_label": "청소",
  "name": "거실 청소", "description": "주 1회",
  "repeat_days": [0, 3], "repeat_days_label": ["월", "목"],
  "difficulty": 2, "difficulty_label": "쉬움", "point": 80,
  "is_active": true,
  "weekly_progress": [
    {"weekday": 0, "label": "월", "status": "completed",
     "completed_by": {"uid": "8f3e…", "name": "홍길동", "profile_image": 3}},
    {"weekday": 1, "label": "화", "status": "not_scheduled", "completed_by": null},
    {"weekday": 2, "label": "수", "status": "not_scheduled", "completed_by": null},
    {"weekday": 3, "label": "목", "status": "incomplete", "completed_by": null},
    {"weekday": 4, "label": "금", "status": "not_scheduled", "completed_by": null},
    {"weekday": 5, "label": "토", "status": "not_scheduled", "completed_by": null},
    {"weekday": 6, "label": "일", "status": "not_scheduled", "completed_by": null}
  ]
}
```

> 상세 화면의 요일 담당자(`assignee`)는 이 응답에는 없다. `weekly_progress` 는 완료자
> 중심이며, 요일별 담당자는 분담안(`assignments.md`)에서 조회한다.

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 404 | `not_found` | 집안일 미존재 또는 다른 집의 집안일 |

---

## B-4. `PATCH /api/v1/homes/mine/chores/{home_chore_id}/`

집안일 메타를 부분 수정한다. **구성원 누구나** 가능. 모든 필드 optional, 전달된 키만 적용.
수정은 항상 **copy-on-write** — 원본 Chore 는 보존(과거 이력·분담안 히스토리 유지)되고 본인 집
전용 사본이 생성되며 응답의 `id` 는 그대로다. `point` 는 난이도에 따라 자동 재계산.
삭제(비활성)된 집안일은 404.

### 요청

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| path | `home_chore_id` | integer | ✓ | 수정할 HomeChore PK |
| body | `category` | integer | - | 카테고리 (1~5) |
| body | `name` | string | - | 집안일 제목 (1~20자) |
| body | `description` | string | - | 설명 (최대 20자, 빈 문자열 허용) |
| body | `repeat_days` | integer[] | - | 반복 요일 (0=월 ~ 6=일). 전달 시 최소 1개 |
| body | `difficulty` | integer | - | 난이도 (1~5) |

### 응답 (200)

수정된 집안일 (공통 집안일 필드).

```json
{
  "id": 12, "category": 3, "category_label": "청소",
  "name": "거실 대청소", "description": "주 1회",
  "repeat_days": [0, 3], "repeat_days_label": ["월", "목"],
  "difficulty": 2, "difficulty_label": "쉬움", "point": 80
}
```

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 400 | `invalid` | 필드 형식 위반 (잘못된 enum, 길이 초과 등) |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 404 | `not_found` | 집안일 미존재 또는 다른 집의 집안일 |

---

## B-5. `DELETE /api/v1/homes/mine/chores/{home_chore_id}/`

집안일을 삭제한다. **구성원 누구나** 가능. 완료/분담안 이력이 있으면 물리 삭제 대신
**비활성화(soft-delete, `is_active=false`)** — 리포트/기여도/히스토리 보존. 이력이 전혀 없으면
물리 삭제. 비활성 집안일은 목록·다음 분담안에서 제외되고 상세 조회만 가능하다.

### 요청 (path)

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `home_chore_id` | integer | ✓ | 삭제할 HomeChore PK |

### 응답 (204)
본문 없음.

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 404 | `not_found` | 집안일 미존재 또는 다른 집의 집안일 |

---

## B-6. `POST /api/v1/homes/mine/chores/{home_chore_id}/restore/`

비활성화된 집안일을 다시 활성화한다 — 삭제 스낵바의 **실행 취소**. 같은 집 구성원이면 누구나
가능. 이미 활성이면 그대로 `200`(멱등). **물리 삭제된 집안일은 복구 불가**(404).

### 요청 (path)

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `home_chore_id` | integer | ✓ | 복구할 HomeChore PK |

### 응답 (200)

복구된 집안일 (공통 집안일 필드, `is_active=true`).

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 404 | `not_found` | 본인 집의 집안일이 아니거나 물리 삭제됨 |

---

# ✅ 섹션 C. 완료 처리 · 메모

## C-1. `POST /api/v1/homes/mine/chores/{home_chore_id}/completions/` (담당자 전용)

확정된 분담안에서 **본인에게 배정된** 집안일을 완료 처리한다. 같은 (집안일, 날짜)는 1건만
기록되며 중복은 409. 완료 후 진행률·기여도·MVP·리포트·리워드 포인트에 즉시 반영된다.

### 요청

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| path | `home_chore_id` | integer | ✓ | 대상 HomeChore PK |
| body | `date` | date | - | 완료 기준 날짜 (YYYY-MM-DD). 생략 시 오늘 |

### 응답 (201)

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | integer | 완료 이력 PK |
| `home_chore_id` | integer | 완료된 집안일 PK |
| `date` | date | 완료 기준 날짜 |
| `point` | integer | 획득 포인트 (분담안 항목 스냅샷) — 스낵바 `완료! +120pt` 용 |
| `completed_by` | object | 완료자 `{uid, name, profile_image}` |

```json
{
  "id": 12,
  "home_chore_id": 3,
  "date": "2026-07-15",
  "point": 120,
  "completed_by": {"uid": "8f3e…", "name": "김현수", "profile_image": 2}
}
```

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 400 | `assignment_not_confirmed` | 해당 주차에 확정된 분담안이 없음 |
| 400 | `not_assigned_on_date` | 그 날짜에 배정되지 않은 집안일 |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 403 | `not_assignee` | 담당자가 아님 |
| 404 | `not_found` | 본인 집의 활성 집안일이 아님 |
| 409 | `already_completed` | 이미 완료 처리됨 |

---

## C-2. `DELETE /api/v1/homes/mine/chores/{home_chore_id}/completions/{completion_date}/` (완료자 전용)

완료 처리를 되돌린다 — 스낵바의 **실행 취소**. 완료를 기록한 본인만 취소할 수 있다.

### 요청 (path)

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `home_chore_id` | integer | ✓ | 대상 HomeChore PK |
| `completion_date` | date | ✓ | 취소할 완료 이력의 날짜 (YYYY-MM-DD) |

### 응답 (204)
본문 없음.

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 400 | `invalid` | 날짜 형식 오류 (YYYY-MM-DD 아님) |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 403 | `not_assignee` | 완료를 기록한 본인이 아님 |
| 404 | `not_found` | 집안일 또는 완료 이력 미존재 |

---

## C-3. `GET /api/v1/homes/mine/chores/{home_chore_id}/notes/`

집안일 메모 목록을 PK 오름차순으로 반환한다. 본인 집이 아니면 404. 0개여도 `200 + []`.

### 요청 (path)

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `home_chore_id` | integer | ✓ | 대상 HomeChore PK |

### 응답 (200)

배열. 각 원소:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | integer | HomeChoreNote PK |
| `author` | object | 작성자 `{uid, name, profile_image}` |
| `content` | string | 메모 본문 (1~200자) |
| `created_at` | string(datetime) | 생성 일시 |
| `updated_at` | string(datetime) | 최종 수정 일시 |

```json
[
  {
    "id": 1,
    "author": {"uid": "8f3e…", "name": "홍길동", "profile_image": 3},
    "content": "락스 사용 시 환기 필수",
    "created_at": "2026-05-13T12:00:00Z",
    "updated_at": "2026-05-13T12:00:00Z"
  }
]
```

> `author.uid` 로 **본인 작성 여부**를 판별해 수정/삭제 버튼 노출을 분기한다.

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 404 | `not_found` | 해당 집안일이 본인 집에 없음 |

---

## C-4. `POST /api/v1/homes/mine/chores/{home_chore_id}/notes/`

메모를 작성한다. 작성자는 호출자로 자동 설정된다.

### 요청

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| path | `home_chore_id` | integer | ✓ | 대상 HomeChore PK |
| body | `content` | string | ✓ | 메모 본문 (1~200자, 빈 문자열 불가) |

### 응답 (201)

C-3 응답의 단일 원소와 동일 구조.

```json
{
  "id": 1,
  "author": {"uid": "8f3e…", "name": "홍길동", "profile_image": 3},
  "content": "락스 사용 시 환기 필수",
  "created_at": "2026-05-13T12:00:00Z",
  "updated_at": "2026-05-13T12:00:00Z"
}
```

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 400 | `invalid` | content 길이 위반 또는 빈 문자열 |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 404 | `not_found` | 해당 집안일이 본인 집에 없음 |

---

## C-5. `PATCH /api/v1/homes/mine/chores/{home_chore_id}/notes/{note_id}/` (작성자 전용)

메모 본문을 변경한다. **본인이 작성한 메모만** 수정 가능(위반 시 403).

### 요청

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| path | `home_chore_id` | integer | ✓ | 대상 HomeChore PK |
| path | `note_id` | integer | ✓ | 대상 메모 PK |
| body | `content` | string | ✓ | 새 메모 본문 (1~200자) |

### 응답 (200)

C-3 응답의 단일 원소와 동일 (`updated_at` 갱신).

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 400 | `invalid` | content 길이 위반 또는 빈 문자열 |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 403 | `permission_denied` | 작성자만 수정 가능 |
| 404 | `not_found` | 집안일/메모 미존재 |

---

## C-6. `DELETE /api/v1/homes/mine/chores/{home_chore_id}/notes/{note_id}/` (작성자 전용)

메모를 삭제한다. **본인이 작성한 메모만** 삭제 가능(위반 시 403).

### 요청 (path)

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `home_chore_id` | integer | ✓ | 대상 HomeChore PK |
| `note_id` | integer | ✓ | 대상 메모 PK |

### 응답 (204)
본문 없음.

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 403 | `permission_denied` | 작성자만 삭제 가능 |
| 404 | `not_found` | 집안일/메모 미존재 |

---

# 🔗 섹션 D. 초대 · 가입

## D-1. `GET /api/v1/homes/invite/{code}/`

초대코드로 집을 조회해 **참여 전 미리보기** 정보를 반환한다. 본 호출만으로는 참여되지 않으며,
확정은 `POST /homes/join/`(D-2)으로 한다.

### 요청 (path)

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `code` | string | ✓ | 6자리 대문자+숫자 초대코드 (예: `AB12CD`) |

### 응답 (200)

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `invite_code` | string | 조회에 사용된 초대코드 (에코백) |
| `name` | string | 집 이름 |
| `image` | integer | 집 이미지 enum (1~8) |
| `member_count` | integer | 전체 구성원 수 (관리자 포함) |
| `created_at` | string(datetime) | 집 생성 일시 |
| `members` | array | 구성원 목록 ([공통 member 구조](#24-공통-객체-구조)) |

```json
{
  "invite_code": "AB12CD",
  "name": "우리집",
  "image": 1,
  "member_count": 2,
  "created_at": "2026-05-12T12:00:00Z",
  "members": [
    {"name": "홍길동", "profile_image": 3, "role": 1, "role_label": "관리자"},
    {"name": "김철수", "profile_image": 2, "role": 2, "role_label": "구성원"}
  ]
}
```

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 404 | `not_found` | 유효하지 않은 초대코드 |

---

## D-2. `POST /api/v1/homes/join/`

초대코드로 집에 **구성원(role=2)으로 참여**한다. 이미 다른 집에 속했다면 먼저 나가야 한다.

### 요청 (body)

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `invite_code` | string | ✓ | 6자리 대문자+숫자 초대코드 |

### 응답 (200)

참여 후 최신 집 정보. 필드는 **A-3 `GET /homes/mine/` 와 동일**.

```json
{
  "id": 12,
  "name": "우리집",
  "image": 1,
  "invite_code": "AB12CD",
  "status": "active",
  "created_at": "2026-05-12T12:00:00Z",
  "members": [
    {"name": "홍길동", "profile_image": 3, "role": 1, "role_label": "관리자"},
    {"name": "김철수", "profile_image": 2, "role": 2, "role_label": "구성원"}
  ]
}
```

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 400 | `already_has_home` | 이미 다른 집에 속해 있음 |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 404 | `not_found` | 유효하지 않은 초대코드 |

---

# 🎁 섹션 E. 스타터팩

## E-1. `GET /api/v1/starter-packs/`

사전 등록된 스타터팩(집안일 프리셋 묶음) 메타 목록을 반환한다. 집안일 상세는 E-2 로 별도 조회.

### 요청
본문 없음.

### 응답 (200)

배열. 각 원소:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | integer | 스타터팩 PK |
| `name` | string | 스타터팩 이름 |
| `description` | string | 설명 (없으면 "") |

```json
[
  {"id": 1, "name": "기본 청소", "description": "신혼/1인 가구용 기본 팩"},
  {"id": 2, "name": "패밀리", "description": "아이 있는 가정용 확장 팩"}
]
```

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 토큰 누락/만료 |

---

## E-2. `GET /api/v1/starter-packs/{starter_pack_id}/chores/`

지정한 스타터팩에 묶인 마스터 `Chore` 들을 반환한다. FE 는 이 목록을 사용자에게 보여주고
선택 항목을 `POST /homes/` 또는 `POST /homes/mine/chores/` 의 `starter_pack_chore_ids` 로 전달한다.

### 요청 (path)

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `starter_pack_id` | integer | ✓ | 대상 StarterPack PK |

### 응답 (200)

배열. 각 원소 (여기서 `id` 는 **마스터 Chore PK** — HomeChore 아님):

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | integer | 집안일 마스터 PK |
| `category` | integer | 카테고리 enum (1~5) |
| `category_label` | string | 카테고리 한글 |
| `name` | string | 집안일 제목 |
| `description` | string | 설명 |
| `repeat_days` | integer[] | 반복 요일 (0=월 ~ 6=일) |
| `repeat_days_label` | string[] | 요일 한글 |
| `difficulty` | integer | 난이도 enum (1~5) |
| `difficulty_label` | string | '쉬움'/'중간'/'어려움' |
| `point` | integer | 난이도 고정 포인트 |

```json
[
  {
    "id": 1, "category": 3, "category_label": "청소",
    "name": "거실 청소", "description": "주 1회",
    "repeat_days": [0, 3], "repeat_days_label": ["월", "목"],
    "difficulty": 2, "difficulty_label": "쉬움", "point": 80
  }
]
```

### 에러
| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 토큰 누락/만료 |

---

# 📑 섹션 F. enum / 상태값 정리

## F-1. 집안일 카테고리 (`category`)

| 값 | 라벨 |
| --- | --- |
| 1 | 쓰레기 |
| 2 | 욕실 |
| 3 | 청소 |
| 4 | 주방 |
| 5 | 세탁 |

## F-2. 난이도 (`difficulty`) → 라벨 · 포인트

| DB 값 | 이름 | 화면 라벨(`difficulty_label`) | 포인트(`point`) |
| --- | --- | --- | --- |
| 1 | 하 | 쉬움 | 40 |
| 2 | 중하 | 쉬움 | 80 |
| 3 | 중 | 중간 | 120 |
| 4 | 중상 | 중간 | 160 |
| 5 | 상 | 어려움 | 200 |

> `point` 는 난이도에 1:1 고정. 직접 입력 불가하며 난이도 변경 시 자동 재계산.

## F-3. 요일 (`repeat_days` / `weekday`)

| 값 | 요일 |
| --- | --- |
| 0 | 월 |
| 1 | 화 |
| 2 | 수 |
| 3 | 목 |
| 4 | 금 |
| 5 | 토 |
| 6 | 일 |

## F-4. 역할 (`role`)

| 값 | 라벨(`role_label`) |
| --- | --- |
| 1 | 관리자 |
| 2 | 구성원 |

## F-5. 집 상태 (`status`)

| 값 | 의미 |
| --- | --- |
| `active` | 활성 |
| `draft` | 생성 중 |

## F-6. 집 이미지 (`image` / `image_id`)

정수 enum `1 ~ 8`. 선택 가능한 목록은 `GET /api/v1/homes/images/`(A-1)로 조회.

## F-7. 집안일 이번 주 진행상태 (`weekly_progress[].status`)

| 값 | 의미 |
| --- | --- |
| `completed` | 이번 주 해당 날짜에 완료 이력 존재 |
| `incomplete` | `repeat_days` 에 포함되나 완료 이력 없음 |
| `not_scheduled` | `repeat_days` 에 없는 요일 |

---

# 💡 섹션 G. FE 연동 팁 / 주의사항

- **화면 진입 분기**: 로그인 직후 `A-5 membership` 로 `has_home` 을 먼저 확인해
  홈 진입 / 온보딩(집 생성·초대코드 참여)을 분기한다. `A-3 GET /homes/mine/` 은 집이 없으면
  404 이므로 분기용으로 쓰지 말 것.
- **집안일 `id` 는 항상 HomeChore PK.** 메모·완료·복구 경로의 `home_chore_id` 로 그대로 사용한다.
  단 **스타터팩 조회(E-2)의 `id` 는 마스터 Chore PK** 라 성격이 다르다 — 혼동 주의.
- **스타터팩 부분 적용**: `starter_pack_chore_ids` 를 생략/null 로 두면 팩 전체, `[]` 로 두면
  아무것도 적용하지 않는다(미리보기에서 전체 미선택 시). 값을 넣으면 체크된 항목만 적용.
- **입력 분기 규칙**: 집 생성/집안일 추가에서 `starter_pack_id` 와 `chores` 는 **동시 사용 불가**.
  추가(B-2)는 **둘 중 하나는 필수**(둘 다 비면 `missing_chore_input`), 생성(A-2)은 둘 다 비워도 됨.
- **삭제 UX**: 집안일 삭제(B-5)는 대부분 soft-delete 이므로 스낵바 **실행 취소** → `B-6 restore` 로
  되살릴 수 있다(멱등). 단 이력이 전혀 없어 물리 삭제된 경우 복구 404.
- **완료/취소 UX**: 완료(C-1)는 **확정된 분담안의 담당자 본인만** 가능하고, 취소(C-2)는
  **완료를 기록한 본인만** 가능하다. 중복 완료는 409 `already_completed`.
- **메모 권한 분기**: `author.uid` 와 내 uid 를 비교해 수정/삭제 버튼을 노출한다.
  타인 메모 수정/삭제는 403 `permission_denied`.
- **관리자 흐름**: 관리자는 직접 나갈 수 없다(A-6 `admin_cannot_leave`).
  양도(A-7) 후 나가거나, 단독이면 집 삭제(A-4) → 구성원 잔존 시 400 `home_has_members`.
- **날짜/요일 표기**: 서버는 `repeat_days`/`weekday` 를 **정수(0=월)** 로 내려주고 한글 라벨을
  함께 제공한다. `date`·`week_start` 는 `YYYY-MM-DD`, 타임스탬프는 ISO 8601.
- **분담안 연동**: 대시보드 `items[]`, 집안일 상세의 요일별 담당자, 완료 처리의 배정 판정 등은
  분담안 도메인에 의존한다. **분담안 상세 스펙은 `assignments.md` 참조.**

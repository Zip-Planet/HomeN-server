# 분담안 (주차별 집안일 배정) 연동 가이드

> 대상: 프론트엔드
> 도메인: 분담안(`WeeklyAssignment`) — 한 집의 한 주차에 대한 집안일 배정 묶음
> 관련 코드: `apps/homes/views.py`, `apps/homes/serializers.py`, `apps/homes/selectors.py`, `apps/notifications/views.py`
> 스펙: `specs/assignments.md`
> 변경 감지(`changes` / `change_type`) 상세는 별도 문서 참조 → [assignments-changes.md](./assignments-changes.md)

---

## 1. 개요

**분담안**(`WeeklyAssignment`)은 한 집의 한 주차(월~일)에 대한 집안일 배정 결과다.
활성 집안일 × 반복 요일을 펼쳐 `(집안일, 요일)` 단위 항목(`items[]`)으로 만들고,
멤버별 예상 포인트 총합이 최대한 균등하도록 담당자를 자동 배정한다.

### 상태 머신

| 상태 | 의미 | 허용 액션 |
| --- | --- | --- |
| `proposed` (제안됨) | 생성되어 구성원에게 제안된 분담안 | 조회 / 재생성 / 확정 |
| `confirmed` (확정됨) | 관리자가 확정(고정)한 분담안 | 조회만 (수정/삭제/재생성 불가) |
| `expired` (만료됨) | 적용 주차가 지난 분담안 (히스토리) | 조회만 |

```
(없음) ──생성──▶ proposed ──확정──▶ confirmed ──주차 종료──▶ expired
                    │
                    └─재생성─▶ 기존 proposed 폐기(삭제) + 새 proposed 생성(새 PK)
```

- 한 집·한 주차에는 `proposed` 최대 1건, `confirmed` 최대 1건.
- 재생성 시 기존 `proposed` 는 물리 삭제되고 **새 PK** 의 분담안이 반환된다.
- `confirmed` / `expired` 는 불변 히스토리로 영구 보존된다.
- 자동화: 매주 일요일 다음 주차 분담안이 자동 생성(`proposed`)되고, 매주 월요일
  확정 조건을 만족한 `proposed` 는 자동 확정, 종료된 `confirmed` 는 `expired` 로 전환된다.

### 스냅샷 개념

각 항목(`items[]`)의 `chore_name` · `category` · `difficulty` · `point` 는
**분담안 생성 시점의 값을 복사해 저장한 스냅샷**이다. 생성 이후 원본 집안일이
수정·삭제되어도 확정/만료 분담안의 항목 값은 바뀌지 않는다.

`proposed` 상태에서는 스냅샷과 최신 원본의 차이를 서버가 계산해 `changes` 와
항목별 `change_type` 으로 함께 내려준다(NEW / UPDATE / 삭제 배지).
자세한 변경 감지 규칙은 [assignments-changes.md](./assignments-changes.md) 참조.

---

## 2. 공통

### Base URL / 인증

- Base: `/api/v1/homes/mine/assignments/`
- 헤더: `Authorization: Bearer <access>` (모든 엔드포인트 필수)
- nudge(재촉)만 경로가 다르다: `POST /api/v1/homes/mine/assignments/nudge/` (`Notifications` 태그)

### 권한

| 액션 | 권한 |
| --- | --- |
| 조회 (`GET` assignments / history) | 모든 구성원 |
| 수동 생성 (`POST` assignments) | **관리자 전용** (구성원 403) |
| 재생성 (`POST` .../regenerate/) | **관리자 전용** (구성원 403) |
| 확정 (`POST` .../confirm/) | **관리자 전용** (구성원 403) |
| 생성 재촉 (`POST` .../nudge/) | 구성원 → 관리자 (누구나 호출) |

속한 집이 없으면 조회·생성 계열은 `404 not_found` 를 반환한다.

### 공통 응답 구조 (분담안 객체)

조회 / 생성 / 재생성 / 확정 4개 엔드포인트는 **모두 동일한 분담안 객체**를 반환한다.
아래 표를 각 엔드포인트에서 반복 서술하지 않으므로 여기서 한 번에 정리한다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | integer | 분담안 PK |
| `week_start` | date | 적용 주차의 월요일 날짜 (YYYY-MM-DD) |
| `status` | string | `proposed` / `confirmed` / `expired` |
| `generated_at` | datetime | 분담안 생성(재생성) 시점 |
| `confirmed_at` | datetime\|null | 확정 시각 (미확정이면 null) |
| `items[].id` | integer | 분담안 항목 PK (요일순 정렬) |
| `items[].home_chore_id` | integer\|null | 원본 집안일(HomeChore) PK — 원본 물리 삭제 시 null |
| `items[].weekday` | integer | 실행 요일 (0=월 ~ 6=일) |
| `items[].weekday_label` | string | 요일 한글 라벨 (예: '월') |
| `items[].chore_name` | string | 집안일명 (생성 시점 **스냅샷**) |
| `items[].category` | integer | 카테고리 enum (스냅샷, 1~5) |
| `items[].category_label` | string | 카테고리 한글 |
| `items[].difficulty` | integer | 난이도 enum (스냅샷, 1~5) |
| `items[].difficulty_label` | string | 난이도 3단계 라벨: 1~2='쉬움', 3~4='중간', 5='어려움' |
| `items[].point` | integer | 포인트 (생성 시점 스냅샷) |
| `items[].assignee` | object\|null | 담당자 `{uid, name, profile_image}` — 탈퇴 시 null |
| `items[].date` | date | 실행 날짜 (`week_start + weekday`) |
| `items[].is_completed` | boolean | 완료 여부 (해당 날짜 `ChoreCompletion` 존재) |
| `items[].change_type` | string\|null | `updated` / `removed` / null (제안됨 상태에서만 의미) |
| `member_points[]` | array | 멤버별 예상 포인트 합계 `{uid, name, profile_image, expected_point}` (항상 전체 기준) |
| `changes` | object | 생성 이후 변경 요약 (제안됨 상태에서만 값 존재) → [상세](./assignments-changes.md) |

> `change_type` / `changes` 는 `proposed` 상태에서만 계산되며, `confirmed` / `expired`
> 에서는 각각 `null` / 빈 값으로 내려온다. 상세 규칙은
> [assignments-changes.md](./assignments-changes.md) 참조.

**공통 응답 예시 (proposed):**

```json
{
  "id": 7,
  "week_start": "2026-07-13",
  "status": "proposed",
  "generated_at": "2026-07-12T21:05:00+09:00",
  "confirmed_at": null,
  "items": [
    {
      "id": 31, "home_chore_id": 3,
      "weekday": 0, "weekday_label": "월",
      "chore_name": "분리수거", "category": 1, "category_label": "쓰레기",
      "difficulty": 3, "difficulty_label": "중간", "point": 120,
      "assignee": {"uid": "8f3e…", "name": "김현수", "profile_image": 2},
      "date": "2026-07-13", "is_completed": false, "change_type": null
    }
  ],
  "member_points": [
    {"uid": "8f3e…", "name": "김현수", "profile_image": 2, "expected_point": 120}
  ],
  "changes": {
    "has_changes": false, "new_entries": [],
    "updated_item_ids": [], "removed_item_ids": []
  }
}
```

---

## 3. 엔드포인트별 상세

### 3.1 `GET /api/v1/homes/mine/assignments/` — 주차별 조회

내 집의 특정 주차 분담안을 조회한다. 모든 구성원 조회 가능.

**요청 파라미터**

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| query | `week_start` | date | - | 조회할 주차의 월요일 (YYYY-MM-DD). 생략 시 **이번 주차** |
| query | `assignee` | string | - | 항목 담당자 필터 — `me` 또는 구성원 uid. 생략 시 전체 |

> `assignee` 필터는 `items[]` 만 좁힌다. `member_points` 는 항상 전체 구성원 기준으로 반환된다.
> `week_start` 는 반드시 월요일 날짜여야 한다(아니면 400 `invalid`).

**응답 (200)** — 공통 분담안 객체 (2절 참조)

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 400 | `invalid` | `week_start` 가 월요일이 아님 |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 404 | `not_found` | 속한 집 없음 / 해당 주차 분담안 없음 |

**요청 예시**

```bash
curl -X GET '{host}/api/v1/homes/mine/assignments/?week_start=2026-07-13' \
     -H 'Authorization: Bearer <access>'
```

---

### 3.2 `POST /api/v1/homes/mine/assignments/` — 수동 생성 (관리자 전용)

분담안을 수동 생성한다. `week_start` 생략 시 **다음 주차**, 과거 주차 불가.
수동 생성된 주차는 일요일 자동 생성에서 스킵된다.
배정: 활성 집안일 × 반복 요일을 펼쳐 멤버별 예상 포인트가 균등하도록 배정
(동점 시 최근 3주 기여도가 낮은 멤버 우선). **활성 집안일 3개 이상** 필요.

**요청 파라미터**

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| body | `week_start` | date | - | 대상 주차의 월요일 (YYYY-MM-DD). 생략 시 다음 주차. 과거 불가 |

**응답 (201)** — 생성된 분담안 (`status: "proposed"`, 공통 객체)

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 400 | `invalid_week_start` | 월요일 아님 / 과거 주차 |
| 400 | `assignment_already_exists` | 해당 주차 분담안 이미 존재 |
| 400 | `not_enough_chores` | 활성 집안일 3개 미만 |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 403 | `permission_denied` | 관리자 아님 |
| 404 | `not_found` | 속한 집 없음 |

**요청 예시**

```bash
curl -X POST '{host}/api/v1/homes/mine/assignments/' \
     -H 'Authorization: Bearer <access>' \
     -H 'Content-Type: application/json' \
     -d '{"week_start": "2026-07-13"}'
```

---

### 3.3 `POST /api/v1/homes/mine/assignments/<id>/regenerate/` — 재생성 (관리자 전용)

`proposed` 상태의 분담안을 폐기하고 최신 원본(집안일/구성원) 기준으로 새로 생성한다.
`confirmed` 상태는 재생성 불가. 동점 배정에 무작위성이 있어 동일 결과 반복을 피한다.

**요청 파라미터**

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| path | `assignment_id` | integer | ✓ | 재생성할 분담안 PK (proposed 상태) |

요청 본문 없음.

**응답 (201)** — 기존 분담안은 폐기되고 **새 PK 의 분담안**(`proposed`, 공통 객체)이 반환된다.

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 400 | `not_proposed` | proposed 상태가 아님 |
| 400 | `not_enough_chores` | 활성 집안일 3개 미만 |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 403 | `permission_denied` | 관리자 아님 |
| 404 | `not_found` | 분담안 없음 / 다른 집 |

**요청 예시**

```bash
curl -X POST '{host}/api/v1/homes/mine/assignments/7/regenerate/' \
     -H 'Authorization: Bearer <access>'
```

---

### 3.4 `POST /api/v1/homes/mine/assignments/<id>/confirm/` — 확정 (관리자 전용)

`proposed` 분담안을 확정한다. 확정된 분담안은 수정/삭제/재생성이 불가하다.
확정 조건 6종을 검증하며, 뒤의 3개(변경 감지 계열)는 위반 시 **409** 로 재생성을 유도한다.

**확정 조건**

| 조건 | 위반 시 |
| --- | --- |
| `proposed` 상태 | 400 `not_proposed` |
| 같은 주차에 확정본 없음 | 400 `already_confirmed_week` |
| 구성원 1명 이상 (관리자 혼자도 가능) | — |
| 생성 이후 집안일 변경 없음 | 409 `chores_changed` |
| 활성 집안일 3개 이상 | 409 `not_enough_chores` |
| 생성 이후 구성원 변화 없음 | 409 `members_changed` |

**요청 파라미터**

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| path | `assignment_id` | integer | ✓ | 확정할 분담안 PK (proposed 상태) |

요청 본문 없음.

**응답 (200)** — `status` 가 `confirmed` 로 전이되고 `confirmed_at` 이 채워진 공통 객체.

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 400 | `not_proposed` | proposed 상태가 아님 |
| 400 | `already_confirmed_week` | 같은 주차에 확정본 존재 |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 403 | `permission_denied` | 관리자 아님 |
| 404 | `not_found` | 분담안 없음 / 다른 집 |
| 409 | `chores_changed` | 생성 이후 집안일 변경 감지 — 재생성 필요 |
| 409 | `members_changed` | 생성 이후 구성원 변화 감지 — 재생성 필요 |
| 409 | `not_enough_chores` | 활성 집안일 3개 미만 — 재생성 필요 |

> 409 는 `changes.has_changes === true` 의 주 원인이다. 조회 응답에서 이미
> `has_changes` 로 미리 감지할 수 있다 → [assignments-changes.md](./assignments-changes.md).

**요청 예시**

```bash
curl -X POST '{host}/api/v1/homes/mine/assignments/7/confirm/' \
     -H 'Authorization: Bearer <access>'
```

---

### 3.5 `GET /api/v1/homes/mine/assignments/history/` — 히스토리 조회

분담안 탭의 `히스토리` 화면(T3C_PlanHistory)용. 주차 셀렉터 목록(`weeks`)과
선택된 주차의 분담안(`selected`)을 한 번에 반환한다. **최대 4주 전까지**,
기본 선택은 지난 주(`weeks_ago=1`). 모든 구성원 조회 가능.

**요청 파라미터**

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| query | `weeks_ago` | integer | - | 1(지난 주) ~ 4(4주 전). 생략 시 1 |

**응답 (200)**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `weeks[].week_start` | date | 해당 주차의 월요일 |
| `weeks[].weeks_ago` | integer | 1 ~ 4 |
| `weeks[].assignment_id` | integer\|null | 분담안 PK. 없으면 null |
| `weeks[].status` | string\|null | confirmed / expired / proposed. 없으면 null |
| `selected` | object\|null | 선택 주차의 분담안 (공통 분담안 객체 구조). 없으면 null |

**응답 예시**

```json
{
  "weeks": [
    {"week_start": "2026-07-06", "weeks_ago": 1, "assignment_id": 7, "status": "expired"},
    {"week_start": "2026-06-29", "weeks_ago": 2, "assignment_id": null, "status": null},
    {"week_start": "2026-06-22", "weeks_ago": 3, "assignment_id": 5, "status": "confirmed"},
    {"week_start": "2026-06-15", "weeks_ago": 4, "assignment_id": 4, "status": "expired"}
  ],
  "selected": { "…공통 분담안 객체와 동일 구조…" }
}
```

> 기록이 없는 주차는 `assignment_id` 와 `selected` 가 null (화면: "해당 주차의 분담안 기록이 없어요").

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 400 | `invalid` | `weeks_ago` 가 1~4 범위 밖 |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 404 | `not_found` | 속한 집 없음 |

---

### 3.6 `POST /api/v1/homes/mine/assignments/nudge/` — 생성 재촉

분담안이 아직 없을 때 **구성원이 관리자에게** 생성을 요청한다. 관리자에게
`이번 주 분담안을 기다리고 있어요` 알림이 적재된다.
(경로 주의: `config/urls.py` 에 등록되어 있으며 Swagger 태그는 `Notifications`.)

**요청 파라미터**

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| body | `week_start` | date | - | 대상 주차의 월요일. 생략 시 이번 주차 (월요일 아니면 400) |

**응답 (201)**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `notified_count` | integer | 알림을 받은 관리자 수 |

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 400 | `invalid` | `week_start` 형식/요일 오류 |
| 401 | `authentication_failed` | 토큰 누락/만료 |
| 404 | `not_found` | 속한 집 없음 |

**요청 예시**

```bash
curl -X POST '{host}/api/v1/homes/mine/assignments/nudge/' \
     -H 'Authorization: Bearer <access>' \
     -H 'Content-Type: application/json' \
     -d '{}'
```

---

## 4. 상태 전이 / enum 정리

### 분담안 상태 (`status`)

| 값 | 라벨 | 진입 | 이탈 |
| --- | --- | --- | --- |
| `proposed` | 제안됨 | 생성 / 재생성 | 확정(→confirmed), 재생성(폐기 후 새 proposed) |
| `confirmed` | 확정됨 | 확정 | 주차 종료(→expired) |
| `expired` | 만료됨 | 주차 종료 | (종착) |

### 요일 (`weekday`)

`0`=월, `1`=화, `2`=수, `3`=목, `4`=금, `5`=토, `6`=일. `weekday_label` 로 한글이 함께 온다.

### 카테고리 (`category`)

`1`=쓰레기, `2`=욕실, `3`=청소, `4`=주방, `5`=세탁. `category_label` 로 한글이 함께 온다.

### 난이도 (`difficulty`) / 포인트 (`point`)

- `difficulty` enum 은 1~5, 화면 라벨(`difficulty_label`)은 3단계: 1~2='쉬움', 3~4='중간', 5='어려움'.
- 포인트는 난이도에 1:1 고정: `1`=40, `2`=80, `3`=120, `4`=160, `5`=200.
- 단, 항목의 `point` 는 **생성 시점 스냅샷** 값이라 원본 난이도가 바뀌어도 확정/만료 분담안에서는 유지된다.

### `change_type` (항목별)

`updated`(원본 수정 → UPDATE 배지) / `removed`(원본 삭제) / `null`(변경 없음).
`proposed` 상태에서만 값이 채워진다. 상세 → [assignments-changes.md](./assignments-changes.md).

---

## 5. FE 연동 팁

### 5.1 조회 → 확정 → 재생성 흐름 (T3A 제안됨 화면)

1. `GET /assignments/?week_start=` 로 이번/다음 주차 분담안을 조회한다.
2. `status === "proposed"` 이고 관리자면 **확정** / **재생성** 버튼을 노출한다.
3. `changes.has_changes === true` 면 확정 대신 **"분담안 다시 생성하기"** 를 유도한다
   (확정 시도 시 409 로 차단되기 때문). 확정 모달 2종:
   `이대로 확정할까요?` / `추가된 집안일이 있어요 → 분담안 다시 생성하기`.
4. 재생성은 새 PK 를 반환하므로, 응답의 `id` 로 상태를 갱신하고 이후 확정 호출에 사용한다.

### 5.2 409 처리 (확정 실패)

확정 `POST .../confirm/` 이 409 를 반환하면 `error.code` 로 사유를 구분해 안내한다.

| code | 사용자 안내 | 후속 액션 |
| --- | --- | --- |
| `chores_changed` | 생성 이후 집안일이 변경됨 | 재생성 유도 |
| `members_changed` | 생성 이후 구성원이 바뀜 | 재생성 유도 |
| `not_enough_chores` | 활성 집안일 3개 미만 | 집안일 추가 후 재생성 |

재생성(`POST .../regenerate/`) 후 다시 확정(`POST .../confirm/`)한다.

### 5.3 권한 분기

- 생성 / 재생성 / 확정 버튼은 **관리자에게만** 노출한다 (구성원 호출 시 403 `permission_denied`).
- 구성원은 분담안이 없을 때 `POST .../nudge/` 로 관리자에게 재촉 알림을 보낸다.

### 5.4 조회 계열 공통 주의

- `week_start` / nudge `week_start` 는 **월요일 날짜**만 허용된다(아니면 400).
- `assignee` 필터는 `items[]` 만 좁히고 `member_points` 는 전체 기준을 유지한다.
- 항목의 `chore_name`·`point` 등은 스냅샷이다. 최신 원본 값이 필요하면 집안일 API를 참조한다.

### 5.5 변경 감지(NEW / UPDATE / 삭제)

`changes` 최상단 요약과 항목별 `change_type` 으로 행 배지를 그린다. NEW 행은 항목이
아직 없어 `changes.new_entries` 를 직접 렌더링해야 한다.
**전체 규칙·필드·예시는 [assignments-changes.md](./assignments-changes.md) 를 참조**한다.

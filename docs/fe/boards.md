# 집안 보드(FairBoard) 연동 가이드

> 대상: 프론트엔드
> Base URL: `/api/v1/homes/mine/board/`
> 관련 코드: `apps/boards/urls.py`, `apps/boards/views.py`, `apps/boards/serializers.py`, `apps/boards/selectors.py`, `specs/boards.md`

---

## 1. 개요

집안 보드(`T2_FairBoard`)는 두 종류의 카드가 **시간순으로 섞인 단일 피드**다. 화면은
`week_start` 가 바뀌는 지점에 주차 구분선을 그린다.

1. **봇 카드**(`type=bot`) — 시스템이 발행하는 페어봇 카드 4종.
   분담안 제안 / 분담안 확정 / 주간 리포트 / 리워드 달성. 문구용 수치는 발행 시점
   스냅샷(`payload`)이다.
2. **도움 요청**(`type=help`) — 구성원이 본인 담당 집안일에 대해 "대신 해줄 사람?" 을
   올리는 카드. 수락하면 대상 항목의 담당자가 **수락자로 변경**된다.
3. **교환 요청**(`type=swap`) — 내 항목과 상대 항목의 담당자를 **맞바꾸자**고 제안하는
   카드. 수락하면 두 항목의 담당자가 서로 맞바뀐다.

> 보드는 단순 안내창이 아니라 **배정을 실제로 움직이는 도구**다 — 조율 카드(도움/교환)를
> 수락하면 분담안 항목(`AssignmentItem`)의 담당자가 바뀐다.

조율 카드의 대상은 항상 **확정(confirmed) 분담안의 미완료 항목**이다. 응답이 없으면
대상 집안일 **다음 날 23:59** 에 자동 만료(`expired`)된다(교환은 두 항목 중 더 이른 쪽 기준).

---

## 2. 공통

### Base URL

```
/api/v1/homes/mine/board/
```

### 인증

- 모든 엔드포인트는 **Bearer access 토큰 필수**.
- 헤더: `Authorization: Bearer <access>`
- 대상 집은 토큰의 사용자가 속한 집으로 자동 결정된다(경로에 home id 없음).
- 속한 집이 없으면 `404 not_found`.

### 구성원 표현(member 객체)

카드의 `requester` / `accepted_by` / `responded_by` / `item.assignee` 등 사람 필드는
아래 공통 구조이며, 값이 없으면 `null` 이다.

```json
{ "uid": "8f3e…", "name": "김현수", "profile_image": 2 }
```

### 엔드포인트 요약

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/` | 피드 조회 (봇+조율 병합, 최신순) |
| GET | `/items/` | 조율 대상 항목 목록 (인라인 아코디언용) |
| POST | `/help/` | 도움 요청 생성 |
| DELETE | `/help/{help_request_id}/` | 도움 요청 취소 (본인, 대기 중) |
| POST | `/help/{help_request_id}/accept/` | 도움 수락 → 담당자 변경 |
| POST | `/swap/` | 교환 요청 생성 |
| DELETE | `/swap/{swap_id}/` | 교환 요청 취소 (본인, 대기 중) |
| POST | `/swap/{swap_id}/accept/` | 교환 수락 → 담당자 맞바꿈 |
| POST | `/swap/{swap_id}/reject/` | 교환 거절 |

---

## 3. 엔드포인트 상세

### 3.1 피드 조회

```
GET /api/v1/homes/mine/board/
```

봇 카드와 조율 카드를 **시간순으로 병합**한 단일 피드를 최신순으로 반환한다. 화면은
`week_start` 가 바뀌는 지점에 주차 구분선을 그린다.

**요청 파라미터**: 없음.

**응답 필드** — `cards[]` 배열. 원소는 `type` 으로 구분되며 공통/타입별 필드는 아래와 같다.

| 필드 | 타입 | 대상 type | 설명 |
| --- | --- | --- | --- |
| `type` | string | 공통 | `bot` / `help` / `swap` |
| `id` | integer | 공통 | 카드 PK (종류별 독립) |
| `week_start` | date | 공통 | 카드가 속한 주차의 월요일 (구분선 기준) |
| `created_at` | datetime | 공통 | 발행 시각 (정렬 기준) |
| `kind` | string | bot | 봇 카드 종류 enum (4종, 아래 4장) |
| `kind_label` | string | bot | 봇 카드 종류 한국어 라벨 |
| `payload` | object | bot | 문구용 스냅샷 (종류별 상이) |
| `status` | string | help / swap | `pending` / `accepted` / `rejected` / `expired` |
| `message` | string | help / swap | 작성 메시지 (최대 30자, 빈 문자열 가능) |
| `requester` | object\|null | help / swap | 요청자 (member 객체) |
| `accepted_by` | object\|null | help | 도움 수락자 (member 객체) |
| `responded_by` | object\|null | swap | 교환 응답자(수락/거절) (member 객체) |
| `item` | object | help | 도움 요청 대상 항목 요약 (아래 item 구조) |
| `requester_item` | object | swap | 교환 — 요청자 항목 요약 |
| `target_item` | object | swap | 교환 — 상대 항목 요약 |

**item 요약 구조** (`item` / `requester_item` / `target_item` 공통):

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | integer | 분담안 항목 PK |
| `chore_name` | string | 집안일명 (생성 시점 스냅샷) |
| `weekday` | integer | 실행 요일 (0=월 ~ 6=일) |
| `weekday_label` | string | 요일 한글 라벨 |
| `difficulty` | integer | 난이도 enum (스냅샷) |
| `point` | integer | 포인트 (스냅샷) |
| `date` | date | 실행 날짜 (`week_start + weekday`) |
| `assignee` | object\|null | 현재 담당자 (member 객체) |

**응답 예시** (200):

```json
{
  "cards": [
    {
      "type": "swap",
      "id": 12,
      "week_start": "2026-07-20",
      "created_at": "2026-07-22T09:14:00+09:00",
      "status": "pending",
      "message": "토요일에 일정이 생겨서 바꿔줄 수 있어?",
      "requester": { "uid": "8f3e…", "name": "김현수", "profile_image": 2 },
      "responded_by": null,
      "requester_item": {
        "id": 31, "chore_name": "분리수거", "weekday": 5, "weekday_label": "토",
        "difficulty": 3, "point": 120, "date": "2026-07-25",
        "assignee": { "uid": "8f3e…", "name": "김현수", "profile_image": 2 }
      },
      "target_item": {
        "id": 44, "chore_name": "화장실 청소", "weekday": 2, "weekday_label": "수",
        "difficulty": 4, "point": 160, "date": "2026-07-22",
        "assignee": { "uid": "1a2b…", "name": "김수환", "profile_image": 5 }
      }
    },
    {
      "type": "help",
      "id": 8,
      "week_start": "2026-07-20",
      "created_at": "2026-07-21T20:03:00+09:00",
      "status": "accepted",
      "message": "토요일 출장이라 대신해줄 사람?",
      "requester": { "uid": "8f3e…", "name": "김현수", "profile_image": 2 },
      "accepted_by": { "uid": "1a2b…", "name": "김수환", "profile_image": 5 },
      "item": {
        "id": 33, "chore_name": "설거지", "weekday": 5, "weekday_label": "토",
        "difficulty": 2, "point": 80, "date": "2026-07-25",
        "assignee": { "uid": "1a2b…", "name": "김수환", "profile_image": 5 }
      }
    },
    {
      "type": "bot",
      "id": 5,
      "week_start": "2026-07-20",
      "created_at": "2026-07-20T21:05:00+09:00",
      "kind": "weekly_report",
      "kind_label": "주간 리포트",
      "payload": { "completion_rate": 0.82, "mvp": "김현수" }
    }
  ]
}
```

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 인증 실패 |
| 404 | `not_found` | 속한 집이 없음 |

---

### 3.2 조율 대상 집안일 목록

```
GET /api/v1/homes/mine/board/items/?week_start=YYYY-MM-DD&assignee=me
```

도움/교환 카드 생성 화면의 아코디언에 채울 항목 목록. **확정 분담안의 미완료 항목**만
반환하며, 이미 대기 중인 조율 카드가 걸린 항목은 `is_requested=true` 로 표시된다
(화면의 "이미 도움 요청한 집안일이에요"). 확정 분담안이 없으면 빈 배열을 반환한다.

- 도움 요청 화면: `assignee=me` 로 본인 항목만 조회.
- 교환 대상 선택: 담당자 필터 칩에 맞춰 구성원 `uid` 로 조회.

**요청 파라미터**

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| query | `week_start` | date | - | 대상 주차의 **월요일**. 생략 시 이번 주차 |
| query | `assignee` | string | - | `me` 또는 구성원 uid. 생략 시 전체 구성원 |

> `week_start` 는 반드시 월요일 날짜여야 한다. 월요일이 아니면 `400`.

**응답 필드** — 항목 배열. 각 원소는 3.1의 **item 요약 구조** + 아래 필드.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `is_requested` | boolean | 이미 대기 중인 조율 카드가 걸린 항목이면 `true` (선택 불가 표시) |

**응답 예시** (200):

```json
[
  {
    "id": 31, "chore_name": "분리수거", "weekday": 5, "weekday_label": "토",
    "difficulty": 3, "point": 120, "date": "2026-07-25",
    "assignee": { "uid": "8f3e…", "name": "김현수", "profile_image": 2 },
    "is_requested": false
  },
  {
    "id": 33, "chore_name": "설거지", "weekday": 5, "weekday_label": "토",
    "difficulty": 2, "point": 80, "date": "2026-07-25",
    "assignee": { "uid": "8f3e…", "name": "김현수", "profile_image": 2 },
    "is_requested": true
  }
]
```

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 400 | `validation error` | 쿼리 형식 오류 (예: `week_start` 가 월요일이 아님) |
| 401 | `authentication_failed` | 인증 실패 |
| 404 | `not_found` | 속한 집이 없음 / 구성원 uid 미존재 |

---

### 3.3 도움 요청 카드 생성

```
POST /api/v1/homes/mine/board/help/
```

본인이 담당한 **확정 분담안의 미완료 항목**에 대해 도움 요청 카드를 올린다. 아무도
수락하지 않으면 대상 집안일 **다음 날 23:59** 에 자동 만료된다.

**요청 본문**

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `item_id` | integer | ✓ | 대상 분담안 항목 PK (본인 담당) |
| `message` | string | - | 메시지 (최대 30자, 생략 시 빈 문자열) |

```json
{ "item_id": 31, "message": "토요일 출장이라 대신해줄 사람?" }
```

**응답 필드** (201):

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | integer | 생성된 도움 요청 PK |
| `status` | string | 생성 직후 상태 (`pending`) |

```json
{ "id": 8, "status": "pending" }
```

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 400 | `assignment_not_confirmed` | 확정 분담안이 아님 |
| 400 | `already_completed` | 이미 완료된 집안일 |
| 401 | `authentication_failed` | 인증 실패 |
| 403 | `permission_denied` | 본인 담당 항목이 아님 |
| 404 | `not_found` | 항목 미존재 |
| 409 | `already_requested` | 이미 도움 요청한 집안일 |

---

### 3.4 도움 요청 취소

```
DELETE /api/v1/homes/mine/board/help/{help_request_id}/
```

본인이 올린 **대기 중(pending)** 도움 요청 카드를 취소(삭제)한다. 이미 수락·만료된
카드는 `409`.

**경로 파라미터**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `help_request_id` | integer | 도움 요청 카드 PK |

**응답**: `204 No Content` (본문 없음).

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 인증 실패 |
| 403 | `permission_denied` | 본인이 올린 카드가 아님 |
| 404 | `not_found` | 카드 미존재 |
| 409 | `already_resolved` | 이미 처리된 카드 |

---

### 3.5 도움 요청 수락 (내가 도와줄게)

```
POST /api/v1/homes/mine/board/help/{help_request_id}/accept/
```

도움 요청을 수락한다. 대상 분담안 항목의 **담당자가 수락자로 변경**되고, 요청자에게
`도움 요청이 수락됐어요` 알림이 전달된다. **본인이 올린 요청은 수락할 수 없다.**

**경로 파라미터**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `help_request_id` | integer | 도움 요청 카드 PK |

**요청 본문**: 없음.

**응답 필드** (200):

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | integer | 도움 요청 PK |
| `status` | string | 처리 후 상태 (`accepted`) |

```json
{ "id": 8, "status": "accepted" }
```

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 인증 실패 |
| 403 | `permission_denied` | 본인이 올린 요청 |
| 404 | `not_found` | 카드 미존재 |
| 409 | `already_resolved` | 이미 처리된 카드 |

---

### 3.6 교환 요청 카드 생성

```
POST /api/v1/homes/mine/board/swap/
```

내 항목과 상대 항목의 담당자를 맞바꾸자고 제안한다. 두 항목 모두 **확정 분담안의
미완료 항목**이어야 하며, 상대 항목의 담당자에게만 응답 권한이 있다. 응답이 없으면
두 항목 중 **더 이른 쪽** 집안일 다음 날 23:59 에 만료된다.

**요청 본문**

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `requester_item_id` | integer | ✓ | 내가 넘길 항목 PK (본인 담당) |
| `target_item_id` | integer | ✓ | 내가 대신할 상대 항목 PK (타인 담당) |
| `message` | string | - | 메시지 (최대 30자, 생략 시 빈 문자열) |

```json
{
  "requester_item_id": 31,
  "target_item_id": 44,
  "message": "토요일에 일정이 생겨서 바꿔줄 수 있어?"
}
```

**응답 필드** (201):

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | integer | 생성된 교환 요청 PK |
| `status` | string | 생성 직후 상태 (`pending`) |

```json
{ "id": 12, "status": "pending" }
```

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 400 | `same_item` | 요청/대상 항목이 동일 |
| 400 | `assignment_not_confirmed` | 확정 분담안이 아님 |
| 400 | `already_completed` | 이미 완료된 집안일 |
| 400 | `no_assignee` | 대상 항목에 담당자가 없음 |
| 401 | `authentication_failed` | 인증 실패 |
| 403 | `permission_denied` | 내 항목이 아니거나 상대 항목이 본인 것 |
| 404 | `not_found` | 항목 미존재 |
| 409 | `already_requested` | 이미 교환 요청한 집안일 |

---

### 3.7 교환 요청 취소

```
DELETE /api/v1/homes/mine/board/swap/{swap_id}/
```

본인이 올린 **대기 중(pending)** 교환 요청 카드를 취소(삭제)한다. 이미 응답·만료된
카드는 `409`.

**경로 파라미터**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `swap_id` | integer | 교환 요청 카드 PK |

**응답**: `204 No Content` (본문 없음).

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 인증 실패 |
| 403 | `permission_denied` | 본인이 올린 카드가 아님 |
| 404 | `not_found` | 카드 미존재 |
| 409 | `already_resolved` | 이미 처리된 카드 |

---

### 3.8 교환 요청 수락 (교환할게)

```
POST /api/v1/homes/mine/board/swap/{swap_id}/accept/
```

교환을 수락한다. 두 분담안 항목의 **담당자가 서로 맞바뀌고**, 요청자에게 `교환 요청이
수락됐어요` 알림이 전달된다. **교환 요청을 받은 담당자만** 응답할 수 있다.

**경로 파라미터**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `swap_id` | integer | 교환 요청 카드 PK |

**요청 본문**: 없음.

**응답 필드** (200):

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | integer | 교환 요청 PK |
| `status` | string | 처리 후 상태 (`accepted`) |

```json
{ "id": 12, "status": "accepted" }
```

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 인증 실패 |
| 403 | `permission_denied` | 요청을 받은 담당자가 아님 |
| 404 | `not_found` | 카드 미존재 |
| 409 | `already_resolved` | 이미 처리된 카드 |

---

### 3.9 교환 요청 거절 (아쉽지만 다음에)

```
POST /api/v1/homes/mine/board/swap/{swap_id}/reject/
```

교환을 거절한다. 카드는 "아쉽지만 다음에 교환해요" 상태(`rejected`)로 남고 **담당자는
바뀌지 않는다**. **교환 요청을 받은 담당자만** 응답할 수 있다.

**경로 파라미터**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `swap_id` | integer | 교환 요청 카드 PK |

**요청 본문**: 없음.

**응답 필드** (200):

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | integer | 교환 요청 PK |
| `status` | string | 처리 후 상태 (`rejected`) |

```json
{ "id": 12, "status": "rejected" }
```

**에러**

| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 인증 실패 |
| 403 | `permission_denied` | 요청을 받은 담당자가 아님 |
| 404 | `not_found` | 카드 미존재 |
| 409 | `already_resolved` | 이미 처리된 카드 |

---

## 4. enum / 상태값 정리

### 4.1 카드 종류 (`type`)

| 값 | 의미 |
| --- | --- |
| `bot` | 페어봇 시스템 카드 |
| `help` | 도움 요청 |
| `swap` | 교환 요청 |

### 4.2 조율 카드 상태 (`status`)

| 값 | 대상 | 의미 |
| --- | --- | --- |
| `pending` | help / swap | 대기 중 (응답 전) |
| `accepted` | help / swap | 수락됨 → 담당자 변경/맞바꿈 완료 |
| `rejected` | swap | 거절됨 → 담당자 변화 없음 (교환 전용) |
| `expired` | help / swap | 기한 초과 자동 만료 |

> 도움 요청은 `rejected` 상태가 없다(수락/취소/만료만 존재). 교환 요청만 `rejected` 를 가진다.

### 4.3 봇 카드 종류 (`kind`, `type=bot`)

| `kind` | `kind_label`(예) | 발행 시점 | `payload` 주요 값(예) |
| --- | --- | --- | --- |
| `assignment_created` | 분담안 제안 | 분담안 생성 시 | 주차, 총 집안일 수 |
| `assignment_confirmed` | 분담안 확정 | 분담안 확정 시 | 주차, 총 집안일 수 |
| `weekly_report` | 주간 리포트 | 매일 21:00 리포트 생성 | 진행률, MVP |
| `reward_achieved` | 리워드 달성 | 리워드 수령 시 | 수령자, 리워드명, 포인트 |

> `kind_label` 은 서버가 내려주는 한국어 라벨이며, `payload` 구조는 종류별로 다르다.
> `payload` 는 발행 시점 **스냅샷**이므로 문구 표시용으로만 사용한다.

---

## 5. FE 연동 팁 / 주의사항

- **주차 구분선**: `cards[]` 는 이미 최신순으로 정렬되어 있다. 위에서 아래로 순회하며
  `week_start` 가 바뀌는 지점에 주차 구분선을 렌더한다.
- **카드 렌더 분기**: 항상 `type` 으로 먼저 분기한다. `bot` 은 `kind` + `payload`,
  `help` 는 `item`, `swap` 은 `requester_item` / `target_item` 을 사용한다.
- **id 는 종류별 독립**: `bot` / `help` / `swap` 각각의 PK 이므로 `type` + `id` 조합으로
  키를 만든다.
- **아코디언 선택 불가 처리**: `GET /items/` 의 `is_requested=true` 항목은 이미 대기 중
  조율 카드가 걸린 항목이므로 선택 비활성 + "이미 도움 요청한 집안일이에요" 안내를 표시한다.
- **week_start 는 월요일 고정**: `/items/` 의 `week_start` 는 반드시 월요일 날짜여야 하며,
  아니면 400. 주차 계산 후 항상 월요일로 정규화해서 보낸다.
- **도움 vs 교환 응답 권한**:
  - 도움 수락은 **요청자 본인만 불가**(그 외 구성원 가능).
  - 교환 수락/거절은 **요청을 받은 상대 항목 담당자만 가능**.
  - 위반 시 모두 `403 permission_denied` 이므로, 카드의 `requester` / `assignee` 로 버튼
    노출 여부를 먼저 판단해 불필요한 403을 줄인다.
- **중복 요청 방지**: 생성 API 는 같은 항목에 대기 카드가 있으면 `409 already_requested`.
  `is_requested` 로 미리 걸러도 경합 상황에서 409가 날 수 있으니 에러 처리도 유지한다.
- **처리 완료 카드 재요청**: 이미 수락/거절/만료된 카드에 취소·수락·거절을 호출하면
  `409 already_resolved`. 낙관적 UI 후 409면 피드를 재조회해 최신 상태로 갱신한다.
- **스냅샷 필드**: item의 `chore_name` / `difficulty` / `point` 는 분담안 생성 시점 값이다.
  최신 집안일 값이 필요하면 원본 집안일/분담안 API를 참조한다.
- **취소는 204**: 도움/교환 취소는 본문이 없다(204). 응답 파싱하지 말고 상태 코드로만
  성공을 판단한다.
- **자동 만료**: `expired` 전환은 매일 자정 배치(`expire_board_requests`)가 처리한다.
  실시간이 아니므로 만료 예정 시각이 지났어도 잠시 `pending` 으로 보일 수 있다.

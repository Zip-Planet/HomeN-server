# 분담안 배지 · 확정 플로우 연동 가이드

> 대상: 프론트엔드
> 관련 코드: `apps/homes/models.py`(AssignmentItem.change_type), `apps/homes/services.py`,
> `apps/homes/views.py`(HomeAssignmentConfirmView)

---

## 1. 개요

관리자 화면 `이번 주 분담안 (제안됨)` 은 두 가지를 서버에 의존한다.

1. **행 배지** — 각 항목의 `NEW` / `UPDATE` 표시
2. **확정 팝업 분기** — `분담안 확정` 을 눌렀을 때 재생성 유도 팝업이냐, 확정 확인 팝업이냐

둘은 **서로 다른 것을 뜻한다.**

| | 무엇을 말하나 | 어디서 오나 |
| --- | --- | --- |
| `items[].change_type` | **직전 분담안 대비** 이번 재생성으로 뭐가 바뀌었나 | 조회 응답 (DB 저장값) |
| 확정 팝업 분기 | **지금** 원본 집안일이 분담안과 어긋나 있나 | 확정 API 1차 호출 응답 |

재생성 직후에는 배지가 남아 있지만(1) 원본과는 일치하므로(2) 확정 확인 팝업이 뜬다.
이 구분이 화면2 → 팝업3 흐름의 핵심이다.

> 이전 버전의 최상단 `changes` 요약 객체는 **제거됐다**. `new_entries` 를 따로 렌더링할
> 필요가 없어졌고, 신규 행도 `items[]` 안에 `change_type: "new"` 로 들어온다.

---

## 2. 행 배지 — `items[].change_type`

```
GET /api/v1/homes/mine/assignments/?week_start=YYYY-MM-DD
```

`items[]` 의 각 원소에 실려 온다.

| 값 | 조건 | 화면 |
| --- | --- | --- |
| `"new"` | 재생성으로 새로 추가된 (집안일, 요일) | **NEW** 배지 |
| `"updated"` | 이름·카테고리·난이도·포인트 중 하나가 직전 분담안과 다름 | **UPDATE** 배지 |
| `null` | 직전과 동일 | 배지 없음 |

동작 규칙:

- **최초 생성분은 전부 `null`** 이다 — 비교 대상이 없다. (화면1: 배지 없는 목록)
- **재생성 후에 배지가 실린다.** (화면2) 서버가 재생성 시점에 계산해 DB 에 저장하므로
  이후 몇 번을 조회해도 같은 값이 온다.
- **담당자 변경은 배지가 아니다.** 재생성은 동점 시 무작위 tie-break 이라 담당자가 거의
  매번 바뀐다. 집안일 자체가 바뀐 경우만 표시한다.
- **삭제는 표시되지 않는다.** 원본이 삭제된 집안일은 새 분담안에 항목 자체가 없다.
- 변경 없이 연속 재생성하면 배지가 사라진다 — 배지의 의미가 "이번 재생성으로 무엇이
  바뀌었나" 이기 때문이다.

### 응답 예시 (재생성 후)

```json
{
  "id": 8,
  "week_start": "2026-07-13",
  "status": "proposed",
  "items": [
    {
      "id": 51, "home_chore_id": 9,
      "weekday": 2, "weekday_label": "수",
      "chore_name": "설거지", "category": 3, "category_label": "주방",
      "difficulty": 2, "difficulty_label": "쉬움", "point": 80,
      "assignee": { "uid": "8f3e…", "name": "김현수", "profile_image": 2 },
      "date": "2026-07-15", "is_completed": false,
      "change_type": "new"
    },
    {
      "id": 52, "home_chore_id": 3,
      "weekday": 0, "weekday_label": "월",
      "chore_name": "분리수거", "category": 1, "category_label": "쓰레기",
      "difficulty": 3, "difficulty_label": "중간", "point": 120,
      "assignee": { "uid": "1a2b…", "name": "김수환", "profile_image": 5 },
      "date": "2026-07-13", "is_completed": false,
      "change_type": "updated"
    },
    {
      "id": 53, "home_chore_id": 4,
      "weekday": 5, "weekday_label": "토",
      "chore_name": "화장실 청소", "category": 2, "category_label": "욕실",
      "difficulty": 4, "difficulty_label": "중간", "point": 160,
      "assignee": { "uid": "8f3e…", "name": "김현수", "profile_image": 2 },
      "date": "2026-07-18", "is_completed": false,
      "change_type": null
    }
  ],
  "member_points": [ ... ]
}
```

---

## 3. 확정 플로우 — `POST .../confirm/`

```
POST /api/v1/homes/mine/assignments/{id}/confirm/
```

**관리자 전용.** `분담안 확정` 버튼을 눌러도 곧바로 확정되면 안 되므로(확인 팝업이 먼저다)
요청 본문의 `acknowledged` 로 2단계로 나뉜다.

| 호출 | body | 동작 |
| --- | --- | --- |
| 1차 — `분담안 확정` 버튼 | 없음 또는 `{"acknowledged": false}` | **확정하지 않고** 판단 결과만 반환 |
| 2차 — 확인 팝업의 `확정` | `{"acknowledged": true}` | 실제로 확정 |

1차 호출은 부작용이 없다 — 분담안은 `proposed` 그대로 남는다.

### 응답 필드 (양쪽 공통)

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `confirmed` | boolean | 실제로 확정됐는지. 1차 호출은 항상 `false` |
| `needs_regenerate` | boolean | **분기는 이 필드 하나만 본다.** true → 재생성 팝업 / false → 확정 확인 팝업 |
| `has_changes` | boolean | 생성 이후 집안일 추가·수정·삭제가 있는지 |
| `added_count` | integer | 추가돼 분담안에 없는 (집안일, 요일) 수 |
| `updated_count` | integer | 스냅샷과 원본이 어긋난 항목 수 |
| `removed_count` | integer | 원본이 삭제(비활성화)된 항목 수 |
| `blocked_reason` | string\|null | `chores_changed` / `members_changed` / `not_enough_chores` / null |
| `assignment` | object\|null | 확정된 분담안 (조회 응답과 동일 구조). 1차 호출은 null |

> `needs_regenerate` 는 `has_changes || blocked_reason != null` 이다. `blocked_reason` 은
> 팝업 문구를 바꿀 때만 쓴다 — 예: `members_changed` 면 "구성원이 변경됐어요".

### 화면 시퀀스

```
화면1 (배지 없음)
  │
  └─[분담안 확정]──▶ POST confirm {}
                       │
                       ├─ needs_regenerate: true
                       │    └─▶ 팝업4 "추가된 집안일이 있어요"
                       │          └─[분담안 다시 생성하기]──▶ POST .../regenerate/
                       │                └─▶ 화면2 (NEW/UPDATE 배지)
                       │                      └─[분담안 확정]──▶ POST confirm {}
                       │                            └─ needs_regenerate: false ─┐
                       │                                                        │
                       └─ needs_regenerate: false ───────────────────────────────┤
                                                                                 ▼
                                                            팝업3 "이대로 확정할까요?"
                                                              └─[확정]──▶ POST confirm
                                                                          {"acknowledged": true}
```

### 1차 호출 — 변경 있음

```json
{
  "confirmed": false,
  "needs_regenerate": true,
  "has_changes": true,
  "added_count": 2,
  "updated_count": 1,
  "removed_count": 0,
  "blocked_reason": "chores_changed",
  "assignment": null
}
```

### 1차 호출 — 변경 없음

```json
{
  "confirmed": false,
  "needs_regenerate": false,
  "has_changes": false,
  "added_count": 0,
  "updated_count": 0,
  "removed_count": 0,
  "blocked_reason": null,
  "assignment": null
}
```

### 2차 호출 — 확정 완료

```json
{
  "confirmed": true,
  "needs_regenerate": false,
  "has_changes": false,
  "added_count": 0,
  "updated_count": 0,
  "removed_count": 0,
  "blocked_reason": null,
  "assignment": {
    "id": 8, "week_start": "2026-07-13",
    "status": "confirmed", "confirmed_at": "2026-07-12T22:10:00+09:00",
    "items": [ ... ], "member_points": [ ... ]
  }
}
```

### 에러

| status | code | 의미 |
| --- | --- | --- |
| 400 | `not_proposed` | proposed 상태가 아님 |
| 400 | `already_confirmed_week` | 같은 주차에 확정본 존재 |
| 400 | `no_members` | 집에 구성원이 없음 |
| 403 | `permission_denied` | 관리자 아님 |
| 404 | `not_found` | 분담안 없음 / 다른 집 |
| 409 | `chores_changed` / `members_changed` / `not_enough_chores` | **2차 호출 전용** — 1차와 2차 사이에 원본이 바뀐 경우 |

> 400 계열은 재생성으로 해결되지 않는 상태 오류라 1차 호출에서도 그대로 400 이다.
> 409 는 1차 호출에서 `blocked_reason` 으로 미리 잡히므로 정상 흐름에서는 나오지 않는다.

---

## 4. 재생성

```
POST /api/v1/homes/mine/assignments/{id}/regenerate/
```

**관리자 전용**, `proposed` 상태만 가능. 201 로 새 분담안을 반환한다(`id` 가 바뀐다).
최신 집안일·구성원 기준으로 스냅샷을 다시 만들면서 직전 분담안과 비교해
`items[].change_type` 을 굽는다.

> 응답의 `id` 가 새 분담안 PK 다. 이후 확정 호출은 **새 id** 로 해야 한다.

---

## 5. 마이그레이션 노트 (구버전 대비)

| 변경 | 이전 | 이후 |
| --- | --- | --- |
| 조회 응답의 `changes` 객체 | `{has_changes, new_entries, updated_item_ids, removed_item_ids}` | **제거됨** |
| `NEW` 행 렌더링 | `changes.new_entries` 를 별도 배열로 합성 | `items[]` 안에 `change_type: "new"` |
| `change_type` 값 | `updated` / `removed` / null (조회 시 실시간 계산) | `new` / `updated` / null (재생성 시 DB 저장) |
| 확정 응답 | 분담안 객체가 최상단 | `assignment` 키 아래로 이동, 판단 필드가 최상단 |
| 확정 호출 횟수 | 1회 (즉시 확정, 변경 시 409) | 2회 (체크 → 확인 팝업 → 확정) |

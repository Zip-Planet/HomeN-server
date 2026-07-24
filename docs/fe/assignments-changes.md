# 분담안 변경 감지 연동 가이드 (`changes` / `change_type`)

> 대상: 프론트엔드
> 엔드포인트: `GET /api/v1/homes/mine/assignments/`
> 관련 코드: `apps/homes/selectors.py:429`, `apps/homes/serializers.py:935·999`, `apps/homes/views.py`

---

## 1. 개요

분담안 항목(`items[]`)은 **생성 시점 스냅샷**이다. 항목의 집안일명·카테고리·난이도·포인트는
분담안을 만든 시점의 값을 그대로 복사해 저장한다. 그래서 분담안 생성 이후 집안일이
추가/수정/삭제되면 스냅샷과 실제 원본이 어긋난다.

서버는 이 차이를 계산해 조회 응답에 함께 내려주고, FE는 이를 행 단위 배지
(`NEW` / `UPDATE` / 삭제)로 노출한다. `has_changes=true`면 확정 시 409가 발생하므로
사용자에게 **재생성**을 유도한다.

- 변경 감지는 **`status="proposed"`(제안됨) 상태에서만** 유효하다.
  confirmed(확정됨) / expired(만료됨) 상태에서는 항상 빈 값이 내려온다.

---

## 2. 엔드포인트

```
GET /api/v1/homes/mine/assignments/?week_start=YYYY-MM-DD
```

- 헤더: `Authorization: Bearer <access>`
- `week_start` 생략 시 **이번 주차**
- 별도 요청 없이 아래 두 필드가 **조회 응답 본문에 포함**되어 내려온다.

---

## 3. 응답 필드

### 3.1 최상단 `changes` (분담안 전체 변경 요약)

| 키 | 타입 | 의미 |
| --- | --- | --- |
| `has_changes` | boolean | 아래 셋 중 하나라도 있으면 `true` → 확정 차단, 재생성 유도 |
| `new_entries` | array | 분담안에 없는 신규 `(집안일, 요일)` 행 → `NEW` 배지 |
| `updated_item_ids` | array&lt;int&gt; | 스냅샷과 원본이 다른 항목 id → `UPDATE` |
| `removed_item_ids` | array&lt;int&gt; | 원본이 삭제/비활성된 항목 id → 삭제 표시 |

`new_entries[]` 원소 구조:

```json
{ "home_chore_id": 9, "chore_name": "설거지", "category": 3, "difficulty": 2, "point": 80, "weekday": 2 }
```

> `category` · `difficulty`는 enum **정수**로 내려온다. 한글 라벨은 포함되지 않으므로
> FE에서 라벨 매핑이 필요하다. (`weekday`도 0=월 ~ 6=일 정수)

### 3.2 항목별 `items[].change_type`

`changes`를 각 항목에 매핑해 둔 편의 값이다.

| 값 | 조건 |
| --- | --- |
| `"updated"` | 항목 id가 `updated_item_ids`에 포함 |
| `"removed"` | 항목 id가 `removed_item_ids`에 포함 |
| `null` | 변경 없음 |

> `new_entries`는 아직 분담안에 항목 자체가 없는 신규 행이라 `items[]`에 대응 항목이 없다.
> 따라서 `change_type`으로는 나오지 않으며, **`NEW` 배지는 `changes.new_entries`를
> 직접 렌더링**해야 한다.

---

## 4. 응답 예시 (proposed + 변경 발생)

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
      "assignee": { "uid": "8f3e…", "name": "김현수", "profile_image": 2 },
      "date": "2026-07-13", "is_completed": false,
      "change_type": "updated"
    },
    {
      "id": 32, "home_chore_id": 4,
      "weekday": 5, "weekday_label": "토",
      "chore_name": "화장실 청소", "category": 2, "category_label": "욕실",
      "difficulty": 4, "difficulty_label": "중간", "point": 160,
      "assignee": { "uid": "1a2b…", "name": "김수환", "profile_image": 5 },
      "date": "2026-07-18", "is_completed": false,
      "change_type": null
    }
  ],
  "member_points": [
    { "uid": "8f3e…", "name": "김현수", "profile_image": 2, "expected_point": 120 }
  ],
  "changes": {
    "has_changes": true,
    "new_entries": [
      { "home_chore_id": 9, "chore_name": "설거지", "category": 3, "difficulty": 2, "point": 80, "weekday": 2 }
    ],
    "updated_item_ids": [31],
    "removed_item_ids": []
  }
}
```

---

## 5. 화면 처리 규칙

- **행 배지**: 각 `items[i].change_type` 값으로 `UPDATE` / 삭제 배지를 표시
- **NEW 행**: `changes.new_entries` 배열을 항목 목록에 추가 행으로 렌더 (`NEW` 배지)
- **확정 버튼**: `changes.has_changes === true`면 확정 대신 "재생성"을 유도

---

## 6. 확정 / 재생성 흐름

### 확정
```
POST /api/v1/homes/mine/assignments/{id}/confirm/
```
| status | code | 의미 |
| --- | --- | --- |
| 409 | `chores_changed` | 생성 이후 집안일 변경 감지 (= `has_changes`의 주 원인) |
| 409 | `members_changed` | 생성 이후 구성원 변화 감지 |
| 409 | `not_enough_chores` | 활성 집안일 3개 미만 |
| 400 | `not_proposed` | proposed 상태가 아님 |
| 400 | `already_confirmed_week` | 같은 주차에 확정본 존재 |

### 재생성 (관리자 전용)
```
POST /api/v1/homes/mine/assignments/{id}/regenerate/
```
- 최신 집안일/구성원 기준으로 스냅샷을 다시 만든다. 재생성 후 다시 확정한다.

---

## 7. 주의사항

- **confirmed / expired 상태**: `changes`는 빈 값
  (`{ has_changes: false, new_entries: [], updated_item_ids: [], removed_item_ids: [] }`),
  모든 `items[].change_type`은 `null`. 변경 감지 UI는 proposed에서만 노출한다.
- **Swagger 예시 주의**: 자동 생성 문서의 응답 예시(`_ASSIGNMENT_EXAMPLE_JSON`)에는
  `changes` / `change_type`가 누락되어 있다. 예시가 축약본이라 그런 것이며 실제
  시리얼라이저는 항상 두 필드를 내려주므로, **실제 응답을 기준으로 파싱**한다.
- **스냅샷 필드**: `items[].chore_name`, `point` 등은 분담안 생성 시점 값이다.
  집안일의 최신 값이 필요하면 원본 집안일 API를 참조한다.

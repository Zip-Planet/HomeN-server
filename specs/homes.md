# Homes 스펙

## 개요
집 생성은 3단계로 구성됩니다: 1) 집 프로필 설정 → 2) 스타터팩(집안일) 선택 → 3) 리워드 설정.
중간에 이탈해도 `creation_step`으로 재진입 단계를 파악합니다.
한 유저는 하나의 집에만 속할 수 있으며, 초대코드(6자리)를 통해 구성원을 추가합니다.

---

## 모델

### HomeImage
| 필드 | 타입 | 설명 |
|------|------|------|
| id | BigAutoField | PK |
| image | ImageField | 프리셋 이미지 (`preset_homes/` 하위) |

### Home
| 필드 | 타입 | 설명 |
|------|------|------|
| id | BigAutoField | PK |
| name | CharField(10) | 집 이름 (한글·영문·숫자·공백, 최대 10자) |
| image | ForeignKey(HomeImage) | 선택된 프리셋 이미지 |
| invite_code | CharField(6, unique) | 자동 발급 6자리 초대코드 (대문자+숫자) |
| creation_step | IntegerField(choices) | 1=집 프로필, 2=집안일, 3=리워드 |
| status | CharField(choices) | draft=생성 중, active=활성 |
| created_at | DateTimeField | 생성 일시 |
| updated_at | DateTimeField | 최종 수정 일시 |

### HomeMember
| 필드 | 타입 | 설명 |
|------|------|------|
| id | BigAutoField | PK |
| home | ForeignKey(Home) | 소속 집 |
| user | ForeignKey(User) | 소속 유저 |
| role | IntegerField(choices) | 1=관리자, 2=구성원 |
| joined_at | DateTimeField | 참여 일시 |

> `(home, user)` 유니크 제약. 집 생성자는 자동으로 관리자(role=1)로 등록.

### StarterPack
| 필드 | 타입 | 설명 |
|------|------|------|
| id | BigAutoField | PK |
| name | CharField(50) | 스타터팩 이름 |
| description | TextField | 설명 |

### Chore (집안일 마스터)
| 필드 | 타입 | 설명 |
|------|------|------|
| id | BigAutoField | PK |
| starter_pack | ForeignKey(StarterPack, nullable) | null이면 커스텀 집안일 |
| name | CharField(50) | 집안일 이름 |
| image | ImageField | 이미지 (`chores/` 하위) |
| repeat_days | ArrayField(IntegerField) | 반복 요일 (0=월 ~ 6=일, Weekday enum). **최소 1개 필수** |
| difficulty | IntegerField(choices) | 1=하, 2=중하, 3=중, 4=중상, 5=상 |
| point | IntegerField | 난이도에 따라 **자동 부여** (직접 입력 불가, 아래 표 참조) |
| updated_at | DateTimeField | 최종 수정 일시 (분담안 변경 감지에 사용) |

> **난이도 표시 규칙**: difficulty≤2 → "쉬움", 3≤difficulty≤4 → "중간", difficulty=5 → "어려움"

> **난이도 → 포인트 자동 부여**: 하=40, 중하=80, 중=120, 중상=160, 상=200.
> 난이도 변경 시 포인트도 자동 재계산된다. 포인트 직접 입력은 허용하지 않는다.

### HomeChore (집에 배정된 집안일)
| 필드 | 타입 | 설명 |
|------|------|------|
| id | BigAutoField | PK |
| home | ForeignKey(Home) | 대상 집 |
| chore | ForeignKey(Chore) | 배정된 집안일 |
| is_active | BooleanField(default=True) | **soft-delete 플래그**. 삭제 시 False 로 전환 |
| created_at | DateTimeField | 배정 일시 |

> `(home, chore)` 유니크 제약.

### 집안일 수정/삭제 정책 (히스토리 보존)

- **수정** (그룹 내 모든 멤버 가능): 집안일명/카테고리/설명/반복요일/난이도만 수정 가능.
  포인트는 난이도 기반 자동 산출이므로 직접 수정 불가.
  수정은 **copy-on-write** — 원본 `Chore` 는 보존하고 사본을 만들어 `HomeChore.chore` 를
  교체한다 (스타터팩·커스텀 동일). 과거 완료 이력·분담안 히스토리는 수정 전 값으로 유지된다.
  확정된 분담안에는 반영되지 않으며, 확정 전(proposed) 분담안은 재생성 시 반영된다
  (→ `specs/assignments.md`).
- **삭제** (그룹 내 모든 멤버 가능): 물리 삭제하지 않고 `HomeChore.is_active=False` 로
  **비활성화**한다. 완료 이력(`ChoreCompletion`)·메모·분담안 히스토리는 보존된다.
  비활성화된 집안일은 목록에서 제외되고, 다음 분담안 (재)생성부터 제외된다.
  이미 확정된 분담안의 해당 주차 항목은 유지된다. 상세 화면 접근 시 삭제된
  집안일임을 안내한다.
  단, **분담안 생성 이력도 완료 이력도 없는** 집안일은 물리 삭제한다.

### Reward
리워드는 `apps.rewards` 로 분리되었다. → `specs/rewards.md`

---

## API 엔드포인트

### GET /api/v1/homes/images/
프리셋 집 이미지 목록을 반환합니다. (인증 필요)

**Response 200**
```json
[
  {"id": 1, "url": "http://example.com/media/preset_homes/1.png"},
  {"id": 2, "url": "http://example.com/media/preset_homes/2.png"}
]
```

---

### POST /api/v1/homes/
집을 생성합니다 (1단계). 생성자는 자동으로 관리자로 등록됩니다. (인증 필요)

**집 이름 규칙**: 한글·영문·숫자·공백만 허용, 최대 10자, 특수문자 제외.

**Request Body**
```json
{
  "name": "우리집",
  "image_id": 2
}
```

**Response 201**
```json
{
  "id": 1,
  "name": "우리집",
  "image": {"id": 2, "url": "http://example.com/media/preset_homes/2.png"},
  "invite_code": "A1B2C3",
  "creation_step": 1,
  "status": "draft",
  "created_at": "2026-04-02T00:00:00Z"
}
```

**Error 400** — 이미 집이 있는 경우
```json
{"error": {"code": "already_has_home", "message": "이미 속한 집이 있습니다."}}
```

---

### GET /api/v1/homes/mine/membership/
현재 유저의 집 소속 여부를 반환합니다. 항상 200을 반환합니다. (인증 필요)
로그인 후 홈 화면과 온보딩(집 생성/초대코드 참여) 화면 분기용으로 사용합니다.

**Response 200**
```json
{"has_home": true}
```
```json
{"has_home": false}
```

---

### GET /api/v1/homes/mine/
현재 유저의 집 정보를 반환합니다. (인증 필요)

**Response 200** — 위 POST 응답과 동일 구조

**Error 404** — 집이 없는 경우
```json
{"error": {"code": "not_found", "message": "속한 집이 없습니다."}}
```

---

### GET /api/v1/starter-packs/
스타터팩 목록을 반환합니다. (인증 필요)

**Response 200**
```json
[
  {"id": 1, "name": "청결한 집", "description": "기본 청소 집안일 모음"},
  {"id": 2, "name": "주방의 달인", "description": "요리·설거지 중심"}
]
```

---

### GET /api/v1/starter-packs/{id}/chores/
특정 스타터팩의 집안일 목록을 반환합니다. (인증 필요)

**Response 200**
```json
[
  {
    "id": 1,
    "name": "청소기 돌리기",
    "image_url": "http://example.com/media/chores/vacuum.png",
    "repeat_days": [0, 2, 4],
    "difficulty": 2,
    "difficulty_label": "쉬움"
  }
]
```

---

### POST /api/v1/homes/{id}/chores/
스타터팩의 집안일 전체를 집에 추가합니다 (2단계). 기존 집안일은 교체됩니다. 관리자 전용. (인증 필요)

**Request Body**
```json
{"starter_pack_id": 1}
```

**Response 201** — 추가된 집안일 목록 (위 GET starter-packs/{id}/chores/ 응답과 동일 구조)

**Error 403** — 관리자가 아닌 경우
```json
{"error": {"code": "permission_denied", "message": "관리자만 집안일을 설정할 수 있습니다."}}
```

---

### POST /api/v1/homes/{id}/rewards/
리워드를 일괄 등록하고 집 생성을 완료합니다 (3단계). 관리자 전용. (인증 필요)

**Request Body** — 배열로 여러 개 일괄 등록
```json
[
  {"name": "치킨", "goal_point": 100},
  {"name": "영화 관람", "goal_point": 200}
]
```

**Response 201**
```json
[
  {"id": 1, "name": "치킨", "goal_point": 100},
  {"id": 2, "name": "영화 관람", "goal_point": 200}
]
```

---

### GET /api/v1/homes/invite/{code}/
초대코드로 집 정보를 조회합니다 (참여 전 미리보기). 활성(active) 상태인 집만 조회됩니다. (인증 필요)

**Response 200**
```json
{
  "invite_code": "A1B2C3",
  "name": "우리집",
  "image": {"id": 2, "url": "http://example.com/media/preset_homes/2.png"},
  "member_count": 2,
  "created_at": "2026-04-02T00:00:00Z",
  "members": [
    {
      "name": "홍길동",
      "profile_image": "http://example.com/media/profile_images/abc.png",
      "role": 1,
      "role_label": "관리자"
    },
    {
      "name": "김철수",
      "profile_image": null,
      "role": 2,
      "role_label": "구성원"
    }
  ]
}
```

**Error 404** — 코드 불일치 또는 비활성 집
```json
{"error": {"code": "not_found", "message": "유효하지 않은 초대코드입니다."}}
```

---

### POST /api/v1/homes/join/
초대코드로 집에 참여합니다. (인증 필요)

**Request Body**
```json
{"invite_code": "A1B2C3"}
```

**Response 200** — 참여한 집 정보 (GET /api/v1/homes/mine/ 응답과 동일 구조)

**Error 400** — 이미 집이 있는 경우
```json
{"error": {"code": "already_has_home", "message": "이미 속한 집이 있습니다. 기존 집에서 나간 후 참여해 주세요."}}
```

**Error 404** — 유효하지 않은 초대코드
```json
{"error": {"code": "not_found", "message": "유효하지 않은 초대코드입니다."}}
```

---

## 집안일 난이도 체계
| DB 값 | 이름 | 화면 표시 |
|-------|------|----------|
| 1 | 하 | 쉬움 |
| 2 | 중하 | 쉬움 |
| 3 | 중 | 중간 |
| 4 | 중상 | 중간 |
| 5 | 상 | 어려움 |

## 요일 enum (Weekday)
| 값 | 요일 |
|----|------|
| 0 | 월 |
| 1 | 화 |
| 2 | 수 |
| 3 | 목 |
| 4 | 금 |
| 5 | 토 |
| 6 | 일 |


---

## 집안일 완료 처리

완료 여부는 별도 컬럼 없이 `ChoreCompletion(home_chore, date)` 로 기록한다.
진행률·기여도·MVP·리포트·리워드 포인트가 전부 이 테이블을 근거로 계산된다.

### POST /api/v1/homes/mine/chores/{home_chore_id}/completions/
집안일 완료 처리 (**담당자 전용**). body: `{"date": "YYYY-MM-DD"}` (선택, 기본 오늘).

**Response 201**
```json
{
  "id": 12,
  "home_chore_id": 3,
  "date": "2026-07-15",
  "point": 120,
  "completed_by": {"uid": "…", "name": "김현수", "profile_image": 2}
}
```

- `point` 는 분담안 항목의 스냅샷 포인트 — 화면 스낵바 `완료! +120pt` 용.
- 400 `assignment_not_confirmed`: 해당 주차에 확정 분담안이 없음.
- 400 `not_assigned_on_date`: 그 날짜에 배정되지 않은 집안일.
- 403 `not_assignee`: 담당자가 아님 · 404: 본인 집의 활성 집안일이 아님.
- 409 `already_completed`: 같은 (집안일, 날짜) 중복.

### DELETE /api/v1/homes/mine/chores/{home_chore_id}/completions/{date}/
완료 취소 (**완료를 기록한 본인 전용**) — 스낵바의 `실행 취소`. 204.

- 403 `not_assignee`: 완료자 본인이 아님 · 404: 완료 이력 없음.

---

## 집안일 삭제 복구

### POST /api/v1/homes/mine/chores/{home_chore_id}/restore/
비활성화(soft-delete)된 집안일을 되살린다 — 삭제 스낵바의 `실행 취소`.
같은 집 구성원이면 누구나 가능하며, 이미 활성이면 그대로 200 (멱등).
이력이 전혀 없어 **물리 삭제**된 집안일은 복구할 수 없다 (404).

---

## 스타터팩 부분 적용

`POST /api/v1/homes/` 와 `POST /api/v1/homes/mine/chores/` 는 `starter_pack_id` 와 함께
`starter_pack_chore_ids` 를 받을 수 있다 (미리보기 화면에서 체크된 항목).

- 생략/null → 팩 전체 적용.
- 빈 배열 → 아무것도 적용하지 않음 ("전체 미선택 후 화면 넘겨도 상관 없음").

---

## 집안일 상세의 이번 주 진행 상태

`GET /api/v1/homes/mine/chores/{id}/` 의 `weekly_progress` 각 원소에 **담당자**가 포함된다.

| 키 | 설명 |
|----|------|
| `weekday` / `label` | 0(월)~6(일) / 한글 라벨 |
| `status` | `completed` / `incomplete` / `not_scheduled` |
| `assignee` | 이번 주 분담안에서 그 요일의 담당자. 배정이 없으면 null |
| `completed_by` | 실제 완료자. 미완료면 null |

> 담당자와 완료자는 다를 수 있다 (도움 카드로 대신 수행). 분담안이 없는 주차는
> `assignee` 가 null 이고 상태는 `repeat_days` 로 판단한다.

---

## 홈 대시보드

### GET /api/v1/homes/mine/dashboard/
`T1_HomeDashboard` 를 한 번에 그리기 위한 집계 응답.

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
  "contribution": {"rate": 72, "week_start": "2026-01-26", "is_last_week": false},
  "next_week": {"week_start": "2026-02-02", "assignment_id": 8, "status": "proposed"},
  "items": [ "…분담안 항목 구조…" ]
}
```

- **진행률** = 완료 항목 수 / 전체 항목 수.
- **기여도** = 내가 완료한 포인트 / 집 전체 완료 포인트 (배정 담당자가 아니라 **실제 완료자** 기준).
- **MVP** = 완료 포인트 최고 구성원 (동점이면 완료 건수 우선).
- **리포트 카드 기여도(`contribution`)**: 이번 주 집 전체 완료 포인트가 0 이면 **지난주 기여도**로 대체한다
  (`is_last_week: true` → 화면 `지난주 기여도 N%`). 지난주도 0 이면 `null` → 화면 `없음`.
  다른 구성원은 완료했는데 내 완료가 0 이면 대체하지 않고 `0%` 다.
- `next_week.status` 가 null 이면 화면은 `생성 필요` + 레드닷으로 표시한다.
- 404: 속한 집 없음.

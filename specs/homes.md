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
| repeat_days | ArrayField(IntegerField) | 반복 요일 (0=월 ~ 6=일, Weekday enum) |
| difficulty | IntegerField(choices) | 1=하, 2=중하, 3=중, 4=중상, 5=상 |

> **난이도 표시 규칙**: difficulty≤2 → "쉬움", 3≤difficulty≤4 → "중간", difficulty=5 → "어려움"

### HomeChore (집에 배정된 집안일)
| 필드 | 타입 | 설명 |
|------|------|------|
| id | BigAutoField | PK |
| home | ForeignKey(Home) | 대상 집 |
| chore | ForeignKey(Chore) | 배정된 집안일 |
| created_at | DateTimeField | 배정 일시 |

> `(home, chore)` 유니크 제약.

### Reward
| 필드 | 타입 | 설명 |
|------|------|------|
| id | BigAutoField | PK |
| home | ForeignKey(Home) | 소속 집 |
| name | CharField(50) | 리워드 이름 |
| goal_point | PositiveIntegerField | 목표 포인트 |
| created_at | DateTimeField | 생성 일시 |
| updated_at | DateTimeField | 최종 수정 일시 |

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

### GET /api/v1/homes/mine/
현재 유저의 집 정보를 반환합니다. `creation_step`으로 재진입 단계를 파악합니다. (인증 필요)

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

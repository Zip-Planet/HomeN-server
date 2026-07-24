# 리워드(Rewards) 연동 가이드

> 대상: 프론트엔드
> Base URL: `/api/v1/homes/mine/rewards/`
> 관련 코드: `apps/rewards/urls.py`, `apps/rewards/views.py`, `apps/rewards/serializers.py`, `specs/rewards.md`
> 화면: `T4_RewardMain`(목록) / `W1_RewardDetail`(상세) / `W2_RewardCreateEdit`(등록·수정)

---

## 1. 개요

리워드는 구성원이 **집안일 완료로 모은 포인트**를 써서 교환하는 보상이다.
포인트 잔액은 별도 컬럼으로 저장하지 않고 **파생값**으로 계산한다.

```
잔액 = 집안일 완료로 획득한 포인트 합 − 수령한 리워드의 포인트 합
```

- **획득**: 완료한 집안일의 포인트 스냅샷 합.
- **사용**: 수령한 리워드의 `claimed_point` 합.
- 완료를 취소하면 잔액도 자동으로 줄어든다 (파생값이라 정합성 보정이 필요 없다).

리워드 수령(**claim**)은 **집당 1회**만 가능하다. 요청 유저의 잔액이 목표 포인트 이상일 때 수령할 수 있고,
수령 시점의 목표 포인트가 `claimed_point` 로 스냅샷되어 잔액에서 차감된다. 수령된 리워드는 잠기며
이후 수정·삭제할 수 없다.

> `status` 는 저장값이 아니라 **요청 유저의 잔액 기준 파생값**이다. 같은 리워드라도 보는 사람에 따라
> `claimable` / `in_progress` 가 달라질 수 있다.

---

## 2. 공통

### Base URL
```
/api/v1/homes/mine/rewards/
```
리워드는 집에 종속된 리소스다. 요청 유저가 속한 집(`mine`)을 자동으로 사용한다.

### 인증
모든 엔드포인트가 인증 필요.
```
Authorization: Bearer <access>
```

### 공통 에러

| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 인증 토큰 없음/유효하지 않음 |
| 404 | `not_found` | 속한 집이 없음 |

에러 응답 형식은 프로젝트 공통(`ErrorResponseSerializer`)을 따른다.

---

## 3. 엔드포인트

| # | METHOD | Path | 설명 |
| --- | --- | --- | --- |
| 3.1 | GET | `/api/v1/homes/mine/rewards/` | 리워드 목록 조회 (탭 화면) |
| 3.2 | POST | `/api/v1/homes/mine/rewards/` | 리워드 등록 |
| 3.3 | GET | `/api/v1/homes/mine/rewards/{reward_id}/` | 리워드 상세 조회 |
| 3.4 | PATCH | `/api/v1/homes/mine/rewards/{reward_id}/` | 리워드 수정 |
| 3.5 | DELETE | `/api/v1/homes/mine/rewards/{reward_id}/` | 리워드 삭제 |
| 3.6 | POST | `/api/v1/homes/mine/rewards/{reward_id}/claim/` | 리워드 받기 (수령) |

### 공통 응답 객체 — 리워드 항목(`RewardOutput`)

목록·등록·수정·수령·상세 응답이 모두 아래 구조를 공유한다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | integer | 리워드 PK |
| `name` | string | 리워드 이름 |
| `goal_point` | integer | 목표 포인트 |
| `status` | string | `claimable` / `in_progress` / `claimed` — 요청 유저 기준 파생 상태 |
| `remaining_point` | integer | 목표까지 남은 포인트 (요청 유저 기준). 달성했으면 `0` |
| `created_by` | object \| null | 등록자 `{uid, name, profile_image}`. 탈퇴 시 `null` |
| `claim` | object \| null | 수령 이력. 미수령이면 `null` |
| `created_at` | string(datetime) | 등록 일시 |

`created_by` 객체:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `uid` | string | 등록자 uid |
| `name` | string | 닉네임 |
| `profile_image` | integer | 프로필 이미지 enum |

`claim` 객체(수령 이력):

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `claimed_by` | object \| null | 수령자 `{uid, name, profile_image}`. 탈퇴 시 `null` |
| `claimed_point` | integer | 수령 시점 목표 포인트 스냅샷 (차감액) |
| `claimed_at` | string(datetime) | 수령 일시 |

---

### 3.1 GET `/api/v1/homes/mine/rewards/` — 리워드 목록 조회

리워드 탭(`T4_RewardMain`) 응답. 헤더용 **내 포인트 잔액**과 상태별 개수, 정렬된 리워드 목록을 함께 반환한다.

- 정렬: **받기 가능(`claimable`) > 진행 중(`in_progress`) > 받기 완료(`claimed`)**, 동순위는 등록일(=`id`) 오름차순.
- `status` 는 요청 유저의 잔액 기준 파생값이다.
- 포인트 잔액 = 집안일 완료로 획득한 포인트 합 − 수령한 리워드의 포인트 합.

#### 요청 파라미터
없음. (요청 유저의 집을 자동 사용)

#### 응답 (200)

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `my_point` | integer | 내 리워드 포인트 잔액 |
| `claimable_count` | integer | 받기 가능 개수 |
| `in_progress_count` | integer | 진행 중 개수 |
| `claimed_count` | integer | 받기 완료 개수 |
| `rewards` | array | 리워드 목록 (위 정렬 순). 각 원소는 [공통 리워드 항목](#공통-응답-객체--리워드-항목rewardoutput) |

```json
{
  "my_point": 2480,
  "claimable_count": 3,
  "in_progress_count": 3,
  "claimed_count": 1,
  "rewards": [
    {
      "id": 1,
      "name": "저녁 N빵 면제권",
      "goal_point": 3000,
      "status": "in_progress",
      "remaining_point": 520,
      "created_by": { "uid": "…", "name": "닉네임_01", "profile_image": 2 },
      "claim": null,
      "created_at": "2026-01-02T10:00:00Z"
    }
  ]
}
```

#### 에러

| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 인증 실패 |
| 404 | `not_found` | 속한 집이 없음 |

```bash
curl -X GET 'https://<host>/api/v1/homes/mine/rewards/' \
  -H 'Authorization: Bearer <access>'
```

---

### 3.2 POST `/api/v1/homes/mine/rewards/` — 리워드 등록

리워드를 등록한다. **같은 집 구성원이면 누구나** 등록할 수 있고 등록자(`created_by`)가 기록된다.
입력은 화면(`W2_RewardCreateEdit`)과 동일하게 **이름 + 목표 포인트** 뿐이다.

#### 요청 (body)

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `name` | string | ✓ | 리워드 이름 (최대 20자) |
| `goal_point` | integer | ✓ | 목표 포인트 (1 이상) |

```json
{ "name": "저녁 더치페이 1회 면제권", "goal_point": 1600 }
```

#### 응답 (201)
등록된 리워드 ([공통 리워드 항목](#공통-응답-객체--리워드-항목rewardoutput) 구조).

#### 에러

| status | code | 의미 |
| --- | --- | --- |
| 400 | `invalid` | 이름 길이 초과 / 목표 포인트 범위 오류 |
| 401 | `authentication_failed` | 인증 실패 |
| 404 | `not_found` | 속한 집이 없음 |

```bash
curl -X POST 'https://<host>/api/v1/homes/mine/rewards/' \
  -H 'Authorization: Bearer <access>' \
  -H 'Content-Type: application/json' \
  -d '{"name": "저녁 더치페이 1회 면제권", "goal_point": 1600}'
```

---

### 3.3 GET `/api/v1/homes/mine/rewards/{reward_id}/` — 리워드 상세 조회

리워드 상세(`W1_RewardDetail`) 응답. [공통 리워드 항목](#공통-응답-객체--리워드-항목rewardoutput) 구조에
**구성원 현황**(`member_progress`)이 추가된다 — 구성원별 보유 포인트와 목표 대비 달성률을 보유 포인트
내림차순으로 정렬해 1등부터 순위를 매긴다.

#### 요청 (path)

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `reward_id` | integer | ✓ | 리워드 PK |

#### 응답 (200)
공통 리워드 항목의 모든 필드 + `member_progress` 배열.

`member_progress[]` 원소:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `rank` | integer | 보유 포인트 기준 순위 (1등부터) |
| `uid` | string | 유저 uid |
| `name` | string | 닉네임 |
| `profile_image` | integer \| null | 프로필 이미지 enum |
| `point` | integer | 구성원 보유 포인트 잔액 |
| `achievement_rate` | integer | 목표 대비 달성률 % (최대 100) |

```json
{
  "id": 1,
  "name": "저녁 N빵 면제권",
  "goal_point": 3000,
  "status": "in_progress",
  "remaining_point": 520,
  "created_by": { "uid": "…", "name": "닉네임_01", "profile_image": 2 },
  "claim": null,
  "created_at": "2026-01-02T10:00:00Z",
  "member_progress": [
    { "rank": 1, "uid": "…", "name": "투다리김치우동", "profile_image": 1, "point": 3470, "achievement_rate": 100 },
    { "rank": 2, "uid": "…", "name": "요정팅커벨", "profile_image": 2, "point": 1470, "achievement_rate": 50 }
  ]
}
```

#### 에러

| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 인증 실패 |
| 404 | `not_found` | 본인 집의 리워드가 아님 (미존재) |

```bash
curl -X GET 'https://<host>/api/v1/homes/mine/rewards/1/' \
  -H 'Authorization: Bearer <access>'
```

---

### 3.4 PATCH `/api/v1/homes/mine/rewards/{reward_id}/` — 리워드 수정

리워드의 이름/목표 포인트를 **부분 수정**한다. 전달된 키만 반영된다.
**이미 수령된 리워드는 수정할 수 없다**(409) — 수령 시점 조건이 사후에 바뀌면 이력이 왜곡되기 때문이다.

#### 요청

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| path | `reward_id` | integer | ✓ | 리워드 PK |
| body | `name` | string | - | 리워드 이름 (최대 20자) |
| body | `goal_point` | integer | - | 목표 포인트 (1 이상) |

```json
{ "goal_point": 2000 }
```

#### 응답 (200)
수정된 리워드 ([공통 리워드 항목](#공통-응답-객체--리워드-항목rewardoutput) 구조).

#### 에러

| status | code | 의미 |
| --- | --- | --- |
| 400 | `invalid` | 입력 검증 실패 (이름 길이 / 목표 포인트 범위) |
| 401 | `authentication_failed` | 인증 실패 |
| 404 | `not_found` | 본인 집의 리워드가 아님 |
| 409 | `already_claimed` | 이미 수령된 리워드 |

```bash
curl -X PATCH 'https://<host>/api/v1/homes/mine/rewards/1/' \
  -H 'Authorization: Bearer <access>' \
  -H 'Content-Type: application/json' \
  -d '{"goal_point": 2000}'
```

---

### 3.5 DELETE `/api/v1/homes/mine/rewards/{reward_id}/` — 리워드 삭제

리워드를 삭제한다. **이미 수령된 리워드는 삭제할 수 없다**(409) — 수령 이력을 보존해야 하기 때문이다.

#### 요청 (path)

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `reward_id` | integer | ✓ | 리워드 PK |

#### 응답 (204)
본문 없음.

#### 에러

| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 인증 실패 |
| 404 | `not_found` | 본인 집의 리워드가 아님 |
| 409 | `already_claimed` | 이미 수령된 리워드 |

```bash
curl -X DELETE 'https://<host>/api/v1/homes/mine/rewards/1/' \
  -H 'Authorization: Bearer <access>'
```

---

### 3.6 POST `/api/v1/homes/mine/rewards/{reward_id}/claim/` — 리워드 받기 (수령)

리워드를 수령한다. 수령은 **집당 1회**이며, 요청 유저의 포인트 잔액이 목표 포인트 이상이어야 한다.
수령 시점의 목표 포인트가 `claimed_point` 로 스냅샷되어 잔액에서 차감된다.
수령 후 해당 리워드는 잠기며 화면은 "받기 완료된 리워드예요"로 비활성화된다.

> 수령 시 보드에 `리워드 달성` 봇 카드가 발행되고, 전 구성원에게 리워드 알림이 발송된다.

#### 요청

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| path | `reward_id` | integer | ✓ | 리워드 PK |

본문(body) 없음.

#### 응답 (200)
수령 처리된 리워드 ([공통 리워드 항목](#공통-응답-객체--리워드-항목rewardoutput) 구조).
`status=claimed`, `claim` 이 채워진다.

```json
{
  "id": 1,
  "name": "저녁 N빵 면제권",
  "goal_point": 3000,
  "status": "claimed",
  "remaining_point": 0,
  "created_by": { "uid": "…", "name": "닉네임_01", "profile_image": 2 },
  "claim": {
    "claimed_by": { "uid": "…", "name": "닉네임_01", "profile_image": 2 },
    "claimed_point": 3000,
    "claimed_at": "2026-07-24T09:00:00Z"
  },
  "created_at": "2026-01-02T10:00:00Z"
}
```

#### 에러

| status | code | 의미 |
| --- | --- | --- |
| 400 | `not_enough_points` | 포인트 잔액 부족 (예: "포인트가 부족합니다. (보유 480P / 목표 2000P)") |
| 401 | `authentication_failed` | 인증 실패 |
| 404 | `not_found` | 본인 집의 리워드가 아님 |
| 409 | `already_claimed` | 이미 수령된 리워드 |

```bash
curl -X POST 'https://<host>/api/v1/homes/mine/rewards/1/claim/' \
  -H 'Authorization: Bearer <access>'
```

---

## 4. enum / 상태값 정리

### 4.1 리워드 상태 `status`

`status` 는 저장값이 아니라 **요청 유저의 잔액 기준 파생값**이다.

| 값 | 조건 | 화면 처리 |
| --- | --- | --- |
| `claimed` | `claim` 존재 (이미 수령됨) | "받기 완료된 리워드예요" (비활성) |
| `claimable` | 미수령 + 요청 유저 잔액 ≥ 목표 포인트 | `리워드 받기` 버튼 |
| `in_progress` | 그 외 (미수령 + 잔액 부족) | `수정하기` 버튼 |

목록 정렬 우선순위: `claimable(0) > in_progress(1) > claimed(2)`, 동순위는 `id` 오름차순.

### 4.2 수령(claim) 가능 조건

| 조건 | 결과 |
| --- | --- |
| 미수령 + 잔액 ≥ 목표 포인트 | 수령 성공 (200) |
| 잔액 < 목표 포인트 | 400 `not_enough_points` |
| 이미 수령됨 | 409 `already_claimed` |
| 본인 집 리워드 아님 | 404 `not_found` |

수령은 **집당 1회**(`RewardClaim` 은 `Reward` 와 1:1). 수령자가 탈퇴하면 `claimed_by` 는 `null` 이 되지만
수령 이력(`claimed_point`, `claimed_at`)과 상태는 그대로 보존된다.

### 4.3 에러 코드 요약

| code | status | 발생 지점 |
| --- | --- | --- |
| `authentication_failed` | 401 | 전 엔드포인트 |
| `not_found` | 404 | 전 엔드포인트 (집 미존재 / 리워드 미존재) |
| `invalid` | 400 | 등록·수정 (입력 검증) |
| `not_enough_points` | 400 | 수령 (잔액 부족) |
| `already_claimed` | 409 | 수정·삭제·수령 (수령된 리워드) |

---

## 5. FE 연동 팁 / 주의사항

- **`status` 는 사용자별 파생값이다.** 서버가 요청 유저 잔액을 기준으로 계산하므로, 같은 리워드라도
  보는 사람에 따라 `claimable` / `in_progress` 가 다르다. 목록의 `claimable_count` 등 카운트도
  요청 유저 기준이다. 로컬에서 상태를 재계산하지 말고 서버 응답을 그대로 사용한다.
- **버튼 분기는 `status` 로**: `claimable` → 받기, `in_progress` → 수정, `claimed` → 비활성. 명시적 판정을 위해
  `status` 값을 우선 사용하고, `remaining_point` 는 진행 바/남은 포인트 표기에 쓴다.
- **`remaining_point`** 는 `max(goal_point − 내 잔액, 0)` 이다. `claimable` / `claimed` 상태에서는 `0` 이다.
- **수령·수정·삭제 후 목록 갱신**: 이들 응답/성공 후에는 잔액과 상태가 바뀌므로 목록(3.1)을 다시 조회해
  `my_point` 와 카운트를 동기화한다.
- **수령된 리워드 편집 차단**: `status === "claimed"` 이면 수정·삭제 UI를 미리 비활성화한다. 그래도 서버는
  409 `already_claimed` 로 재차 방어한다.
- **`created_by` / `claimed_by` 는 null 가능**: 등록자·수령자가 탈퇴하면 `null` 이 내려온다. 렌더 시 null 가드 필수.
- **`profile_image` 는 정수 enum**: 이미지 URL이 아니라 enum 값이므로 FE에서 매핑한다.
  `member_progress[].profile_image` 는 `null` 일 수 있다.
- **입력 검증(등록/수정)**: `name` 최대 20자(화면 카운터 `0/20`), `goal_point` 는 1 이상. 위반 시 400 `invalid`.
- **`member_progress`** 는 상세(3.3)에만 포함된다. 보유 포인트 내림차순으로 이미 정렬·순위 부여되어 있으므로
  FE에서 재정렬하지 않아도 된다. `achievement_rate` 는 최대 100으로 클램프된다.

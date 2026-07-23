# Rewards (리워드) 스펙

## 개요

리워드는 구성원이 **집안일 완료로 모은 포인트**를 써서 교환하는 보상이다.
화면: `T4_RewardMain`(목록) / `W1_RewardDetail`(상세) / `W2_RewardCreateEdit`(등록·수정).

포인트는 별도 컬럼으로 저장하지 않고 **파생값**으로 계산한다.

```
잔액 = 완료로 획득한 포인트 합 − 수령한 리워드의 포인트 합
```

- 획득: `ChoreCompletion` 과 같은 (집안일, 날짜)의 `AssignmentItem.point` 스냅샷 합.
- 사용: `RewardClaim.claimed_point` 합.
- 완료를 취소하면 잔액도 자동으로 줄어든다 (파생값이므로 정합성 보정이 필요 없다).

---

## 모델

### Reward
| 필드 | 타입 | 설명 |
|------|------|------|
| id | BigAutoField | PK |
| home | ForeignKey(Home) | 소속 집 |
| name | CharField(50) | 리워드 이름 (입력 검증은 20자 — 화면 카운터 `0/20`) |
| goal_point | PositiveIntegerField | 목표 포인트 |
| created_by | ForeignKey(User, SET_NULL) | 등록자 (탈퇴 시 null) |
| created_at / updated_at | DateTimeField | 생성·수정 일시 |

> 테이블명 `rewards`. 원래 `apps.homes` 에 있던 모델을 **state-only 마이그레이션**으로
> `apps.rewards` 로 옮겼다 (테이블·데이터 그대로).

### RewardClaim
| 필드 | 타입 | 설명 |
|------|------|------|
| id | BigAutoField | PK |
| reward | OneToOneField(Reward) | 대상 리워드 — **집당 1회 수령** |
| claimed_by | ForeignKey(User, SET_NULL) | 수령자 (탈퇴 시 null) |
| claimed_point | PositiveIntegerField | 수령 시점 목표 포인트 스냅샷 (차감액) |
| claimed_at | DateTimeField | 수령 일시 |

---

## 상태

`status` 는 저장값이 아니라 **요청 유저의 잔액 기준 파생값**이다.

| 상태 | 조건 | 화면 |
|------|------|------|
| `claimed` | `RewardClaim` 존재 | "받기 완료된 리워드예요" (비활성) |
| `claimable` | 미수령 + 잔액 ≥ 목표 포인트 | `리워드 받기` 버튼 |
| `in_progress` | 그 외 | `수정하기` 버튼 |

목록 정렬: **받기 가능 > 진행 중 > 받기 완료**, 동순위는 등록일 오름차순.

---

## 정책

- 등록·수정·삭제는 같은 집 구성원이면 누구나 가능하다. 등록자는 `created_by` 로 기록된다.
  (구버전 화면설계서의 "작성자만 수정 가능"은 최종 design 2 에서 사라졌다. `created_by` 는
  남겨 두었으므로 정책이 되살아나면 서비스 레이어에서만 막으면 된다.)
- **이미 수령된 리워드는 수정·삭제 불가** (409 `already_claimed`). 수령 이력과 조건이 어긋나면
  안 되기 때문이다.
- 수령은 잔액이 목표 포인트 이상일 때만 가능하다 (400 `not_enough_points`).
- 수령 시 보드에 `리워드 달성` 봇 카드가 발행되고, 전 구성원에게 리워드 알림이 간다.

---

## API 엔드포인트

모두 인증 필요. 리워드는 집에 종속되므로 `/api/v1/homes/mine/rewards/` 하위다.

### GET /api/v1/homes/mine/rewards/
리워드 탭 응답 — 헤더 요약 + 정렬된 목록.

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
      "created_by": {"uid": "…", "name": "닉네임_01", "profile_image": 2},
      "claim": null,
      "created_at": "2026-01-02T10:00:00Z"
    }
  ]
}
```

### POST /api/v1/homes/mine/rewards/
`{"name": "저녁 더치페이 1회 면제권", "goal_point": 1600}` → 201.

### GET /api/v1/homes/mine/rewards/{id}/
목록 항목 구조 + `member_progress` (구성원 현황 랭킹).

```json
{
  "member_progress": [
    {"rank": 1, "uid": "…", "name": "투다리김치우동", "profile_image": 1, "point": 3470, "achievement_rate": 100},
    {"rank": 2, "uid": "…", "name": "요정팅커벨", "profile_image": 2, "point": 1470, "achievement_rate": 50}
  ]
}
```

### PATCH /api/v1/homes/mine/rewards/{id}/
`name` / `goal_point` 부분 수정. 수령된 리워드는 409.

### DELETE /api/v1/homes/mine/rewards/{id}/
204. 수령된 리워드는 409.

### POST /api/v1/homes/mine/rewards/{id}/claim/
수령. 200 (수령 처리된 리워드) / 400 `not_enough_points` / 409 `already_claimed`.

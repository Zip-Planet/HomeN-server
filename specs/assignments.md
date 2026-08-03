# Assignments (분담안) 스펙

## 개요

집안일 관리는 두 데이터로 분리된다.

1. **집안일 원본** (`Chore` + `HomeChore`) — 반복 생성되는 집안일의 기본 정보.
   예: 분리수거 / 난이도 중 / 120포인트 / 매주 월·수·금. → `specs/homes.md` 참조.
2. **주차별 실행 집안일** (`AssignmentItem`) — 원본을 기준으로 특정 주차에 실제로 생성된 항목.
   예: 2026년 6월 3주차 월요일 분리수거 / 120포인트 / 담당자 김현수 / 미완료.

**분담안**(`WeeklyAssignment`)은 한 집의 한 주차에 대한 실행 집안일 묶음이며,
담당자 자동 배정 결과를 담는다.

### 용어
- **주차**: 월요일(0)~일요일(6). `week_start` = 해당 주 월요일 날짜로 식별.
- **활성 집안일**: `HomeChore.is_active=True` 인 집안일 (soft-delete 되지 않은 것).
- **기여도**: 최근 3주(해당 주차 직전 3개 주차) 동안 유저가 완료한 집안일 포인트 합
  (`ChoreCompletion.completed_by` 기준, 완료 시점의 `chore.point` 합산).

---

## 상태 및 전이

| 상태 | 설명 | 허용 액션 |
|------|------|----------|
| `proposed` (제안됨) | 관리자·구성원에게 제안된 분담안 | 조회 / 재생성 / 확정 |
| `confirmed` (확정됨) | 관리자에 의해 확정(고정)된 분담안 | 조회만 |
| `expired` (만료됨) | 적용 주차가 지난 분담안 (히스토리) | 조회만 |

```
(없음) ──생성──▶ proposed ──확정──▶ confirmed ──주차 종료──▶ expired
                    │
                    └─재생성─▶ 기존 proposed 폐기(삭제) + 새 proposed 생성
```

- 확정된 분담안은 **수정/삭제 불가**. 이후 변경은 조율 요청(추후 스펙)으로만 가능.
- 재생성 시 기존 `proposed` 는 물리 삭제(폐기)한다. `confirmed`/`expired` 는 불변 히스토리로 영구 보존.
- 한 집·한 주차에 `proposed` 최대 1건, `confirmed` 최대 1건.

---

## 모델

### WeeklyAssignment (분담안)
| 필드 | 타입 | 설명 |
|------|------|------|
| id | BigAutoField | PK |
| home | ForeignKey(Home) | 대상 집 |
| week_start | DateField | 적용 주차의 월요일 날짜 |
| status | CharField(choices) | proposed / confirmed / expired |
| generated_at | DateTimeField | 분담안 생성(재생성) 시점 — 이후 변경 감지 기준 |
| member_uids_snapshot | ArrayField(UUID) | 생성 시점 구성원 uid 목록 (구성원 변화 감지용) |
| chore_fingerprint | CharField | 생성 시점 활성 집안일 지문 — 활성 HomeChore 들의 (id, name, category, repeat_days, difficulty) 를 정렬·직렬화해 해시한 값 (집안일 변경 감지용) |
| confirmed_at | DateTimeField(null) | 확정 시각 |
| confirmed_by | ForeignKey(User, SET_NULL, null) | 확정한 관리자 (자동 확정이면 null) |
| created_at / updated_at | DateTimeField | 생성·수정 일시 |

> 제약: `(home, week_start)` 당 `proposed` 1건, `confirmed` 1건 (partial unique).
> 과거 주차 정보 보존: 항목은 아래 `AssignmentItem` 스냅샷으로 저장되므로 원본
> 수정/삭제가 확정·만료 분담안에 소급되지 않는다.

### AssignmentItem (주차별 실행 집안일)
| 필드 | 타입 | 설명 |
|------|------|------|
| id | BigAutoField | PK |
| assignment | ForeignKey(WeeklyAssignment) | 소속 분담안 |
| home_chore | ForeignKey(HomeChore, SET_NULL, null) | 원본 집안일 링크 (원본 삭제·비활성화돼도 항목 유지) |
| weekday | IntegerField(0~6) | 실행 요일 (Weekday enum) |
| assignee | ForeignKey(User, SET_NULL, null) | 자동 배정된 담당자 (탈퇴 시 null) |
| chore_name | CharField(20) | **스냅샷**: 생성 시점 집안일명 |
| category | IntegerField | **스냅샷**: 생성 시점 카테고리 |
| difficulty | IntegerField | **스냅샷**: 생성 시점 난이도 |
| point | IntegerField | **스냅샷**: 생성 시점 포인트 |

> 완료 여부는 별도 저장하지 않고 기존 `ChoreCompletion`(home_chore, date) 과
> 조인해 계산한다 — `date = week_start + weekday`. 완료 처리 API 는 기존 것을 재사용.

---

## 분담안 생성/재생성 정책

**권한: 생성·재생성·확정 모두 관리자 전용.** 조회는 모든 구성원 가능.

### 생성 기준
1. **활성 집안일 3개 이상**이어야 생성 가능 (미만이면 생성 불가 에러).
2. 활성 집안일 × `repeat_days` 를 펼쳐 (집안일, 요일) 단위 항목을 만든다.
3. 각 항목의 포인트는 생성 시점 `chore.point` 스냅샷.
4. **멤버별 예상 포인트 총합이 최대한 균등**하도록 배정한다.

### 배정 알고리즘
1. 항목을 포인트 내림차순으로 정렬한다.
2. 각 항목을 **현재 누적 배정 포인트가 가장 낮은 멤버**에게 배정한다 (greedy / LPT).
3. 누적 포인트 동점 시 **최근 3주 기여도가 낮은 멤버 우선**.
4. 그래도 동점이면 무작위 — 재생성 시 동일한 분담안이 반복되지 않도록 tie-break 에
   무작위성을 부여한다 (권장 수준, 완전 상이함을 보장하지는 않음).

### 재생성 조건
- 관리자만 가능.
- 기존 분담안이 `proposed` 상태일 때만 가능 (`confirmed` 는 재생성 불가).
- 기존 `proposed` 를 폐기(삭제)하고 최신 원본 기준으로 새 `proposed` 를 생성한다.
  → 생성 시점 이후의 집안일 추가/수정/삭제(비활성화)가 이때 반영된다.

### 집안일 변경의 분담안 반영 (생성 시점 기준)
| 상황 | 반영 정책 |
|------|-----------|
| 분담안 생성 전 집안일 생성 | 분담안 생성 시 포함 |
| `proposed` 분담안 존재 중 집안일 생성/수정/삭제 | 자동 반영 안 됨 — **재생성 시 반영** (확정 시도 시 변경 감지로 차단됨) |
| `confirmed` 분담안 존재 중 집안일 생성/수정/삭제 | 해당 주차 반영 불가 — **다음 주차 분담안부터 반영** |
| 이미 지난 요일 | 소급 반영하지 않음 |

---

## 분담안 확정 정책

### 확정 조건
| 조건 | 필수 여부 | 위반 시 |
|------|-----------|---------|
| `proposed` 상태 분담안 존재 | 필수 | 404/400 |
| 같은 주차에 `confirmed` 분담안 없음 | 필수 | 400 |
| 집 구성원 1명 이상 (관리자 혼자도 가능) | 필수 | 400 |
| 생성 시점 이후 집안일 변경 없음 (`chore_fingerprint` 재계산 일치) | 중요 | 확정 불가(409) — 변경 안내 후 재생성 유도 |
| 활성 집안일 3개 이상 | 중요 | 확정 불가(409) — 재생성 유도 |
| 생성 시점 이후 구성원 변화 없음 (`member_uids_snapshot` 일치) | 중요 | 확정 불가(409) — 재생성 유도 |

### 확정 2단계 (화면 플로우)
`분담안 확정` 버튼을 눌러도 곧바로 확정하지 않는다. 확인 팝업을 먼저 띄워야 하므로
확정 엔드포인트가 요청 본문의 `acknowledged` 로 2단계로 동작한다.

```
[분담안 확정] ──▶ POST confirm {}            (1차 — 확정하지 않고 체크만)
                    │
                    ├─ needs_regenerate=true  ──▶ "추가된 집안일이 있어요" 팝업
                    │                              └─[분담안 다시 생성하기]──▶ POST regenerate
                    │                                    └─▶ NEW/UPDATE 배지가 실린 분담안
                    └─ needs_regenerate=false ──▶ "이대로 확정할까요?" 팝업
                                                   └─[확정]──▶ POST confirm {"acknowledged": true}
```

- 1차 호출은 **부작용이 없다** — 상태는 `proposed` 그대로다.
- `needs_regenerate = has_changes || blocked_reason != null`. 화면은 이 필드 하나만 보면 된다.
- 1차와 2차 사이에 원본이 바뀔 수 있으므로 2차 호출도 확정 조건을 다시 검증한다(위반 시 409).

### 확정 후 생성/보장되는 값
- 원본 집안일 ID(`home_chore`) / 확정 분담안 ID
- 담당자 ID / 실행 날짜(주차 `week_start` + `weekday`)
- 생성 시점의 난이도와 포인트 (스냅샷 — 이후 원본 수정에 불변)
- 보드 카드 알림 생성, 앱푸시 알림 → **TODO: 알림 인프라 미정. 구현 보류** (호출 지점만 서비스에 주석으로 표시)

---

## 스케줄 (management command + cron)

| 커맨드 | 스케줄 | 동작 |
|--------|--------|------|
| `generate_assignments` | 매주 일요일 21:05 | 모든 활성 집에 대해 **다음 주차** 분담안 자동 생성. 해당 주차에 이미 `proposed`/`confirmed` 가 있으면(관리자 수동 생성 포함) 그 집은 **스킵**. 활성 집안일 3개 미만인 집도 스킵(로그) |
| `finalize_assignments` | 매주 월요일 00:00 | ① 시작된 주차의 `proposed` 중 **확정 조건을 모두 만족**하는 것을 자동 확정(`confirmed_by=null`). 불만족이면 `proposed` 로 유지 — 관리자가 재생성 또는 수동 확정해야 함. ② 종료된 주차의 `confirmed` → `expired` 전환 |

- cron 등록 예시는 README 배포 절에 문서화한다. (예: `5 21 * * 0`, `0 0 * * 1`, TZ=Asia/Seoul)
- 커맨드는 멱등: 같은 시각 중복 실행돼도 중복 생성/전이가 발생하지 않는다.

---

## API 엔드포인트

모두 인증 필요. `{week_start}` 는 `YYYY-MM-DD`(월요일) 형식.

### GET /api/v1/homes/mine/assignments/?week_start=&assignee=
자기 집 분담안 조회 (모든 구성원). `week_start` 생략 시 **이번 주차**
(분담안 탭의 기본 진입 탭이 `이번 주`).

`assignee` 는 항목 목록을 담당자로 좁히는 필터 — `me` 또는 구성원 uid (멤버 필터 칩).
`member_points`(구성원 배정 포인트 카드)는 항상 전체 기준으로 반환된다.

**Response 200**
```json
{
  "id": 1,
  "week_start": "2026-07-06",
  "status": "proposed",
  "generated_at": "2026-07-05T21:05:00+09:00",
  "confirmed_at": null,
  "items": [
    {
      "id": 10,
      "home_chore_id": 3,
      "weekday": 0,
      "chore_name": "분리수거",
      "category": 1,
      "difficulty": 3,
      "point": 120,
      "assignee": {"uid": "…", "name": "김현수", "profile_image": 2},
      "date": "2026-07-06",
      "is_completed": false,
      "change_type": null
    }
  ],
  "member_points": [
    {"uid": "…", "name": "김현수", "profile_image": 2, "expected_point": 360}
  ]
}
```

`items[].change_type` — **재생성 시점**에 직전 분담안과 비교해 굽는 값. 화면의 행 배지다.

| 값 | 조건 | 화면 |
| --- | --- | --- |
| `new` | 재생성으로 새로 추가된 (집안일, 요일) | **NEW** 배지 |
| `updated` | 이름·카테고리·난이도·포인트 중 하나가 직전과 다름 | **UPDATE** 배지 |
| `null` | 직전과 동일. 최초 생성분은 항상 이 값 | 배지 없음 |

- **DB 에 저장된 값**이라 조회 때 계산하지 않는다. 확정·만료된 분담안도 생성 당시 값을 그대로 보존한다.
- 담당자 변경은 배지로 치지 않는다 — 재생성은 동점 시 무작위 tie-break 이라 담당자가 거의 매번 바뀐다.
- 원본이 삭제된 집안일은 새 분담안에 항목 자체가 없으므로 별도 표시가 없다.
- 변경 없이 연속 재생성하면 직전 재생성본과 같아 배지가 사라진다 — 배지의 의미가
  "이번 재생성으로 무엇이 바뀌었나" 이기 때문이다.

**Error 404** — 해당 주차 분담안 없음.

### GET /api/v1/homes/mine/assignments/history/?weeks_ago=
분담안 히스토리 조회 (모든 구성원). **최대 4주 전까지**, 기본 선택은 지난 주(`weeks_ago=1`).
주차 셀렉터 목록과 선택된 주차의 분담안을 한 번에 반환한다.

```json
{
  "weeks": [
    {"week_start": "2026-01-26", "weeks_ago": 1, "assignment_id": 7, "status": "expired"},
    {"week_start": "2026-01-19", "weeks_ago": 2, "assignment_id": null, "status": null}
  ],
  "selected": { "…GET 응답과 동일 구조…" }
}
```

- 400: `weeks_ago` 가 1~4 범위 밖 · 404: 속한 집 없음.
- 기록이 없는 주차는 `assignment_id`/`selected` 가 null (화면: "해당 주차의 분담안 기록이 없어요").

### POST /api/v1/homes/mine/assignments/nudge/
분담안 생성 재촉 (**구성원 → 관리자**). body: `{"week_start": "…"}` (선택, 기본 이번 주차).
관리자에게 `이번 주 분담안을 기다리고 있어요` 알림이 적재된다. → `specs/notifications.md`

- 201: `{"notified_count": 1}` · 404: 속한 집 없음.

### POST /api/v1/homes/mine/assignments/
분담안 수동 생성 (**관리자 전용**). body: `{"week_start": "…"}` (선택, 기본 다음 주차. 과거 주차 불가).
수동 생성된 주차는 일요일 자동 생성에서 스킵된다.

- 201: 생성된 분담안 (위 GET 응답 구조)
- 400: 해당 주차에 이미 proposed/confirmed 존재, 활성 집안일 3개 미만, 과거 주차
- 403: 관리자 아님

### POST /api/v1/homes/mine/assignments/{id}/regenerate/
분담안 재생성 (**관리자 전용**). `proposed` 상태에서만 가능.
기존 분담안을 폐기하고 최신 원본 기준으로 새로 생성해 반환한다.

- 201: 새 분담안
- 400: proposed 상태 아님 / 활성 집안일 3개 미만
- 403: 관리자 아님 · 404: 없음

### POST /api/v1/homes/mine/assignments/{id}/confirm/
분담안 확정 (**관리자 전용**). 위 확정 조건 6종을 검증한다.
요청 본문 `acknowledged` 로 2단계 동작 — 생략/`false` 면 확정 전 체크, `true` 면 실제 확정.

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

- `confirmed`: 실제로 확정됐는지. 1차 호출은 항상 false.
- `needs_regenerate`: 화면 분기 기준. true 면 재생성 팝업, false 면 확정 확인 팝업.
- `added_count` / `updated_count` / `removed_count`: 팝업 문구용 건수.
- `blocked_reason`: `chores_changed` / `members_changed` / `not_enough_chores` / null.
- `assignment`: 확정된 분담안(위 조회 응답과 동일 구조). 1차 호출은 null.

- 200: 확정 전 체크 결과 또는 확정 완료
- 409: (2차 호출) 집안일 변경/구성원 변화/활성 집안일 부족 감지 — `error.code` 로 사유 구분
  (`chores_changed` / `members_changed` / `not_enough_chores`), 재생성 유도
- 400: proposed 아님 / 같은 주차 확정본 존재 / 구성원 없음 (1차 호출에서도 400) ·
  403: 관리자 아님 · 404: 없음

---

## 보드 카드 / 알림 연동

분담안 생성·확정 시 보드에 봇 카드를 발행하고 전 구성원에게 알림을 적재한다.
자세한 정책은 `specs/boards.md`, `specs/notifications.md` 참조.

| 시점 | 봇 카드 | 알림 |
|------|---------|------|
| 분담안 생성 | `assignment_created` | 분담안이 생성됐어요 |
| 분담안 확정 | `assignment_confirmed` | 분담안이 확정됐어요 |
| 확정 시도 중 변경 감지 | — | 409 + 응답의 `changes` 로 화면이 안내 |

> **앱푸시 발송은 인프라 미정으로 보류.** 인앱 알림 레코드 적재까지만 구현되어 있고
> 발송 지점은 `apps/notifications/services.py` 에 TODO 로 표시돼 있다.

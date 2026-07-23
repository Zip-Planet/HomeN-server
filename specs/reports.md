# Reports (주간 리포트) 스펙

## 개요

`R1_WeeklyReport` 화면용 주간 집계. **매주 일요일 21:00** 에 관리 커맨드가 그 주차
분담안의 수행 결과를 스냅샷으로 굳혀 저장한다 (빈 상태 문구: "리포트는 매주 일요일
저녁 9시에 자동으로 생성돼요").

스냅샷인 이유: 리포트는 "그 주에 무슨 일이 있었나"를 남기는 기록이므로, 이후 집안일이
수정·삭제돼도 지난 리포트 수치가 흔들리면 안 된다.

---

## 모델 — WeeklyReport

| 필드 | 타입 | 설명 |
|------|------|------|
| home | ForeignKey(Home) | 대상 집 |
| week_start | DateField | 대상 주차의 월요일 |
| total_count / completed_count | PositiveIntegerField | 전체·완료 항목 수 |
| progress_rate | PositiveIntegerField | 진행률 % (반올림) |
| mvp_user | ForeignKey(User, SET_NULL) | 완료 포인트 1위 (탈퇴 시 null) |
| mvp_name | CharField(8) | MVP 닉네임 **스냅샷** (탈퇴해도 화면에 남김) |
| mvp_point / mvp_completed_count | PositiveIntegerField | MVP 포인트·건수 |
| member_stats | JSONField | 구성원별 `{uid, name, profile_image, assigned_count, completed_count, point}` |
| most_done / most_missed | JSONField(null) | 하이라이트 `{name, count}` |
| generated_at | DateTimeField | 생성 시각 |

> `(home, week_start)` 유니크.

---

## 집계 규칙

- **진행률** = 완료 항목 수 / 전체 항목 수.
- **포인트**는 배정 담당자가 아니라 **실제 완료자**(`ChoreCompletion.completed_by`) 기준으로
  합산한다 — 도움 카드로 담당자가 바뀔 수 있기 때문이다.
- **MVP** = 완료 포인트 1위 (동점이면 완료 건수 우선).
- **구성원 통계**는 배정(`assigned_count`)과 완료(`completed_count`)를 함께 담는다
  (화면이 `완료 · 7/7건` 으로 둘 다 보여준다). 배정이 없는 구성원도 0건으로 노출한다.
- **하이라이트**는 집안일명 기준 완료/미완료 최다 항목.
- 대상 분담안은 `confirmed` 또는 `expired` — **제안(proposed) 상태는 리포트 대상이 아니다.**

---

## 스케줄

| 커맨드 | 스케줄 | 동작 |
|--------|--------|------|
| `generate_weekly_reports` | 매주 일요일 21:00 (`0 21 * * 0`, TZ=Asia/Seoul) | 모든 활성 집의 이번 주차 리포트 생성. 분담안이 없으면 스킵 |

멱등 — 중복 실행 시 최신 집계로 덮어쓸 뿐 중복 생성되지 않는다.
생성 시 보드에 `주간 리포트` 봇 카드가 발행되고 전 구성원에게 리포트 알림이 간다.

---

## API 엔드포인트

### GET /api/v1/homes/mine/reports/weekly/?week_start=
인증 필요. 모든 구성원 조회 가능. `week_start` 생략 시 이번 주차.

```json
{
  "id": 4,
  "week_start": "2026-01-26",
  "total_count": 25,
  "completed_count": 16,
  "progress_rate": 64,
  "mvp": {"uid": "…", "name": "투다리김치우동", "profile_image": 1, "point": 570, "completed_count": 7},
  "member_stats": [
    {"uid": "…", "name": "투다리김치우동", "profile_image": 1, "assigned_count": 7, "completed_count": 7, "point": 570}
  ],
  "most_done": {"name": "설거지", "count": 6},
  "most_missed": {"name": "화장실 청소", "count": 2},
  "generated_at": "2026-02-01T21:00:00+09:00"
}
```

**Error 404** — 속한 집이 없거나 해당 주차 리포트 미생성 (화면은 빈 상태 노출).

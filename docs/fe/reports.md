# 주간 리포트 연동 가이드 (`reports`)

> 대상: 프론트엔드
> 화면: `R1_WeeklyReport`
> 관련 코드: `apps/reports/urls.py`, `apps/reports/views.py`, `apps/reports/serializers.py`, `specs/reports.md`

---

## 1. 개요

주간 리포트는 "그 주에 무슨 일이 있었나"를 남기는 **스냅샷 기록**이다. **매주 일요일 21:00**
(`Asia/Seoul`) 에 `generate_weekly_reports` 커맨드가 그 주차 분담안의 수행 결과를 굳혀 저장한다.
스냅샷이므로 리포트 생성 이후 집안일이 수정·삭제돼도 지난 리포트 수치는 변하지 않는다.

리포트가 담는 것:

- **주간 진행률** (`progress_rate`) 과 완료/전체 항목 수
- **우리집 MVP** (완료 포인트 1위)
- **구성원별 달성 현황** (`member_stats[]` — 배정·완료·포인트)
- **하이라이트** — 가장 많이 한 집안일(`most_done`) / 미완료가 많은 집안일(`most_missed`)

빈 상태 처리: 아직 리포트가 생성되지 않았거나 그 주차에 분담안이 없으면 **404** 가 내려온다.
화면은 "집안일을 완료하면 리포트가 도착해요" (또는 "리포트는 매주 일요일 저녁 9시에
자동으로 생성돼요") 빈 상태를 노출한다.

### 집계 규칙 (참고)

- **진행률** = 완료 항목 수 / 전체 항목 수 (반올림 %).
- **포인트**는 배정 담당자가 아니라 **실제 완료자** 기준으로 합산한다 (도움 카드로 담당자가 바뀔 수 있음).
- **MVP** = 완료 포인트 1위 (동점이면 완료 건수 우선). 완료 이력이 없으면 `null`.
- **구성원 통계**는 배정이 없는 구성원도 0건으로 노출한다.
- 대상 분담안은 `confirmed` 또는 `expired` 상태만 (제안 상태 `proposed` 는 리포트 대상이 아님).

---

## 2. 공통

| 항목 | 값 |
| --- | --- |
| Base URL | `/api/v1/homes/mine/reports/` |
| 인증 | `Authorization: Bearer <access>` (필수) |
| 권한 | 집의 **모든 구성원** 조회 가능 |

---

## 3. 엔드포인트

### 3.1 주간 리포트 조회

```
GET /api/v1/homes/mine/reports/weekly/?week_start=YYYY-MM-DD
```

내가 속한 집의 특정 주차 주간 리포트를 조회한다.

#### 요청 파라미터

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| query | `week_start` | date (`YYYY-MM-DD`) | 아니오 | 조회할 주차의 **월요일** 날짜. 생략 시 **이번 주차** |

> `week_start` 는 반드시 **월요일** 날짜여야 한다. 월요일이 아니면 400 (`week_start 는 월요일 날짜여야 합니다.`) 이 내려온다.

#### 응답 필드 (200)

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | integer | 리포트 PK |
| `week_start` | date | 대상 주차의 월요일 날짜 |
| `total_count` | integer | 그 주 전체 항목 수 |
| `completed_count` | integer | 완료 항목 수 |
| `progress_rate` | integer | 진행률 % (반올림) |
| `mvp` | object \| null | 우리집 MVP. 완료 이력이 없으면 `null` |
| `member_stats` | array | 구성원별 달성 현황 (포인트 내림차순) |
| `most_done` | object \| null | 가장 많이 한 집안일 `{name, count}` |
| `most_missed` | object \| null | 미완료가 많은 집안일 `{name, count}` |
| `generated_at` | datetime | 리포트 생성 시각 |

##### `mvp` 오브젝트

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `uid` | string \| null | MVP 유저 uid (탈퇴 시 `null`) |
| `name` | string | MVP 닉네임 (생성 시점 **스냅샷** — 탈퇴해도 화면에 남김) |
| `profile_image` | integer \| null | 프로필 이미지 enum (탈퇴 시 `null`) |
| `point` | integer | MVP 가 완료로 획득한 포인트 합 |
| `completed_count` | integer | MVP 완료 건수 |

##### `member_stats[]` 원소

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `uid` | string | 유저 uid |
| `name` | string | 닉네임 (생성 시점 스냅샷) |
| `profile_image` | integer \| null | 프로필 이미지 enum |
| `assigned_count` | integer | 배정된 항목 수 |
| `completed_count` | integer | 완료한 항목 수 |
| `point` | integer | 완료로 획득한 포인트 합 |

> 화면이 `완료 · 7/7건` 형태로 배정/완료를 함께 보여주므로 `assigned_count`, `completed_count` 를 모두 사용한다.

##### `most_done` / `most_missed` 오브젝트

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `name` | string | 집안일명 |
| `count` | integer | 횟수 (완료 / 미완료 최다) |

#### 응답 예시 (200)

```json
{
  "id": 4,
  "week_start": "2026-01-26",
  "total_count": 25,
  "completed_count": 16,
  "progress_rate": 64,
  "mvp": {
    "uid": "8f3e…",
    "name": "투다리김치우동",
    "profile_image": 1,
    "point": 570,
    "completed_count": 7
  },
  "member_stats": [
    {
      "uid": "8f3e…",
      "name": "투다리김치우동",
      "profile_image": 1,
      "assigned_count": 7,
      "completed_count": 7,
      "point": 570
    }
  ],
  "most_done": { "name": "설거지", "count": 6 },
  "most_missed": { "name": "화장실 청소", "count": 2 },
  "generated_at": "2026-02-01T21:00:00+09:00"
}
```

#### 에러 코드

| status | code | 의미 |
| --- | --- | --- |
| 400 | `validation_error` | `week_start` 형식 오류 또는 월요일이 아닌 날짜 |
| 401 | `authentication_failed` | 인증 실패 (토큰 미제공/만료) |
| 404 | `not_found` | 속한 집이 없거나 해당 주차 리포트가 없음 → **빈 상태 노출** |

#### curl 예시

```bash
# 이번 주차
curl -H "Authorization: Bearer <access>" \
  "https://<host>/api/v1/homes/mine/reports/weekly/"

# 특정 주차 (월요일 지정)
curl -H "Authorization: Bearer <access>" \
  "https://<host>/api/v1/homes/mine/reports/weekly/?week_start=2026-01-26"
```

---

## 4. FE 연동 팁 / 주의사항

- **404 는 정상 흐름이다.** 리포트 미생성/분담안 없음을 의미하므로 에러 토스트가 아니라
  빈 상태 화면("집안일을 완료하면 리포트가 도착해요")으로 처리한다.
- **`week_start` 는 월요일만 허용.** 주차 이동 UI 에서 날짜를 계산할 때 항상 해당 주의
  월요일로 정규화해 보낸다. 월요일이 아니면 400 이다.
- **`mvp` / `most_done` / `most_missed` 는 `null` 일 수 있다.** 완료 이력이 없는 주차는
  `mvp = null`, 하이라이트도 `null` 이므로 각 카드에 null 가드를 둔다.
- **`profile_image` 는 enum 정수.** MVP·구성원 통계 모두 이미지 URL 이 아니라 정수 enum 이므로
  FE 에서 이미지 매핑이 필요하다. 탈퇴 유저(MVP)의 `profile_image`·`uid` 는 `null` 일 수 있다.
- **스냅샷 값이다.** `name`, `point`, `member_stats` 등은 리포트 생성 시점 값이다. 이후 집안일/닉네임이
  바뀌어도 지난 리포트 수치는 변하지 않는다. 최신 값이 필요하면 원본 API 를 참조한다.
- **정렬 보장.** `member_stats[]` 는 **포인트 내림차순**으로 정렬되어 내려온다 (별도 정렬 불필요).
- **생성 시점.** 리포트는 매주 일요일 21:00(KST) 에 자동 생성된다. 그 이전에 이번 주차를 조회하면 404 다.

# Boards (집안 보드 / FairBoard) 스펙

## 개요

`T2_FairBoard` 는 두 종류의 카드가 **시간순으로 섞인 피드**다. 화면은 `week_start` 가
바뀌는 지점에 주차 구분선을 그린다.

1. **봇 카드** — 시스템이 발행. 페어봇 시스템 카드 4종.
2. **조율 카드** — 구성원이 발행. 도움 요청 / 교환 요청.

보드는 안내창이 아니라 **배정을 실제로 움직이는 도구**다 — 조율 카드를 수락하면
`AssignmentItem.assignee` 가 바뀐다.

---

## 모델

### BotCard
| 필드 | 타입 | 설명 |
|------|------|------|
| home | ForeignKey(Home) | 대상 집 |
| kind | CharField(choices) | `assignment_created` / `assignment_confirmed` / `weekly_report` / `reward_achieved` |
| week_start | DateField | 카드가 가리키는 주차 (구분선 기준) |
| payload | JSONField | 문구용 **스냅샷** (총 집안일 수, MVP, 완료율 등) |
| created_at | DateTimeField | 발행 시각 |

> `(home, kind, week_start)` 유니크 — 같은 주차·종류는 1건 (멱등 발행).

### HelpRequest (도움 요청)
| 필드 | 타입 | 설명 |
|------|------|------|
| home / item | FK | 대상 집 / 대상 `AssignmentItem` |
| requester | ForeignKey(User) | 요청자 (= 요청 시점 담당자) |
| message | CharField(30) | 메시지 (선택, 화면 카운터 `0/30`) |
| status | CharField | `pending` / `accepted` / `expired` |
| accepted_by | ForeignKey(User, SET_NULL) | 수락자 |
| resolved_at | DateTimeField(null) | 수락·만료 시각 |

> `item` 당 `pending` 1건 (partial unique).

### SwapRequest (교환 요청)
| 필드 | 타입 | 설명 |
|------|------|------|
| home | FK | 대상 집 |
| requester_item / target_item | FK(AssignmentItem) | 교환할 두 항목 |
| requester | ForeignKey(User) | 요청자 (= `requester_item` 담당자) |
| message | CharField(30) | 메시지 (선택) |
| status | CharField | `pending` / `accepted` / `rejected` / `expired` |
| responded_by | ForeignKey(User, SET_NULL) | 응답자 |
| resolved_at | DateTimeField(null) | 응답·만료 시각 |

> `requester_item` 당 `pending` 1건 (partial unique).

---

## 정책

### 조율 카드 생성 조건
- 대상은 **확정(confirmed) 분담안의 항목**만. 제안 상태는 400 `assignment_not_confirmed`.
- **이미 완료된 항목**은 조율 불가 (400 `already_completed`).
- 도움: 본인 담당 항목만 (403).
- 교환: `requester_item` 은 본인 담당, `target_item` 은 타인 담당이어야 한다 (403).
  같은 항목 지정은 400 `same_item`.
- 같은 항목에 대기 중 카드가 있으면 409 `already_requested`
  (화면의 "이미 도움 요청한 집안일이에요").

### 수락 시 배정 변경
| 카드 | 수락 결과 |
|------|-----------|
| 도움 요청 | 대상 항목의 담당자 → **수락자** |
| 교환 요청 | 두 항목의 담당자를 **맞바꿈** |

- 도움 요청은 요청자 **본인이 수락할 수 없다** (403).
- 교환은 **요청을 받은 담당자만** 수락·거절할 수 있다 (403).
- 이미 처리된 카드는 409 `already_resolved`.
- 취소(삭제)는 본인이 올린 **대기 중** 카드만 가능하다.

### 만료
응답이 없으면 **대상 집안일 날짜의 다음 날 23:59** 에 자동 만료된다.
교환은 두 항목 중 **더 이른 쪽**을 기준으로 한다 (먼저 지나가는 집안일 기준).

| 커맨드 | 스케줄 | 동작 |
|--------|--------|------|
| `expire_board_requests` | 매일 자정 (`0 0 * * *`, TZ=Asia/Seoul) | 기한이 지난 `pending` 카드를 `expired` 로 전환 |

### 봇 카드 발행 지점
| 시점 | 카드 |
|------|------|
| 분담안 생성 | `assignment_created` — 주차 + 총 집안일 수 |
| 분담안 확정 | `assignment_confirmed` — 주차 + 총 집안일 수 |
| 주간 리포트 생성 (일 21:00) | `weekly_report` — 진행률 + MVP |
| 리워드 수령 | `reward_achieved` — 수령자 + 리워드명 + 포인트 |

---

## API 엔드포인트

모두 인증 필요. `/api/v1/homes/mine/board/` 하위.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/` | 피드 조회 (봇+조율 병합, 최신순) |
| GET | `/items/?week_start=&assignee=` | 조율 대상 항목 목록 (인라인 아코디언용) |
| POST | `/help/` | 도움 요청 생성 `{item_id, message}` |
| DELETE | `/help/{id}/` | 도움 요청 취소 (본인, 대기 중) |
| POST | `/help/{id}/accept/` | 도움 수락 → 담당자 변경 |
| POST | `/swap/` | 교환 요청 생성 `{requester_item_id, target_item_id, message}` |
| DELETE | `/swap/{id}/` | 교환 요청 취소 (본인, 대기 중) |
| POST | `/swap/{id}/accept/` | 교환 수락 → 담당자 맞바꿈 |
| POST | `/swap/{id}/reject/` | 교환 거절 |

`GET /items/` 는 확정 분담안의 **미완료 항목**만 반환하고, 대기 중 조율 카드가 걸린
항목은 `is_requested=true` 로 표시한다. `assignee` 는 `me` 또는 구성원 uid.

피드 카드는 `type` 으로 구분한다 (`bot` / `help` / `swap`).

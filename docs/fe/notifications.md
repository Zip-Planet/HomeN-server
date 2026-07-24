# 알림(Notifications) 연동 가이드

> 대상: 프론트엔드
> Base URL: `/api/v1/notifications/` (알림함 · 설정 · 확인) + `/api/v1/homes/mine/assignments/nudge/` (분담안 재촉)
> 관련 화면: `N1_NotificationInbox`(알림함), `T5_My`(푸시 설정)
> 관련 코드: `apps/notifications/urls.py`, `apps/notifications/views.py`, `apps/notifications/serializers.py`, `apps/notifications/models.py`

---

## 1. 개요

알림 도메인은 크게 세 가지를 담당한다.

- **인앱 알림함**(`N1_NotificationInbox`): 발생한 알림을 카테고리별로 조회하고 개별 확인(읽음) 처리한다.
- **푸시 설정**(`T5_My`): 마스터 토글 + 카테고리별 토글로 푸시 수신 여부를 제어한다.
- **분담안 재촉(nudge)**: 분담안이 아직 없을 때 구성원이 관리자에게 생성을 요청한다. (URL은 분담안 흐름에 붙지만 동작은 알림 적재다.)

핵심 개념:

- **알림함 기록과 푸시 발송은 별개다.** 인앱 알림함 레코드는 설정과 **무관하게 항상** 적재된다. 푸시 설정 토글은 오직 푸시 **발송** 여부만 제어한다.
- **마스터 토글 우선**: `push_enabled`가 꺼지면 카테고리 값과 무관하게 푸시를 발송하지 않는다.
- **정렬**: 미확인 우선 > 최신순.
- **보관 7일**: 발생 후 7일이 지난 알림은 서버가 삭제한다(`purge_notifications` 커맨드). 응답의 `retention_days`로 화면 하단 안내 문구(예: "7일 전 알림까지 확인할 수 있어요")를 구성한다.
- **딥링크**: `deep_link`는 탭 시 이동할 목적지 문자열이다. 대상 주차가 지났거나 이미 처리된 카드처럼 랜딩할 수 없으면 앱이 만료 토스트를 대신 노출한다.

> **푸시 발송은 인프라 미정으로 현재 보류.** 지금은 인앱 알림 레코드 적재까지만 수행한다. FE는 알림함/설정 UI를 정상 구현하되, 실제 푸시 도착 여부에 의존하지 말 것.

---

## 2. 공통

### Base URL

```
/api/v1/notifications/                       # 알림함 · 설정 · 확인
/api/v1/homes/mine/assignments/nudge/        # 분담안 재촉
```

### 인증

- 모든 엔드포인트 **Bearer access 토큰 필수**.
- 헤더: `Authorization: Bearer <access>`
- 토큰 누락/무효 시 `401 authentication_failed`.

### 엔드포인트 요약

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/api/v1/notifications/?category=` | 알림함 조회 (미확인 개수 + 목록) |
| POST | `/api/v1/notifications/{notification_id}/read/` | 알림 확인(읽음) 처리 |
| GET | `/api/v1/notifications/settings/` | 푸시 설정 조회 (없으면 기본값 생성) |
| PATCH | `/api/v1/notifications/settings/` | 푸시 설정 부분 수정 |
| POST | `/api/v1/homes/mine/assignments/nudge/` | 분담안 생성 재촉 (구성원 → 관리자) |

---

## 3. 엔드포인트별 상세

### 3.1 알림함 조회

```
GET /api/v1/notifications/?category={category}
```

인앱 알림함 응답. 정렬은 **미확인 우선 > 최신순**이며, 발생 후 7일이 지난 알림은 삭제된다.

#### 요청 파라미터

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| query | `category` | string | - | 카테고리 5종 중 하나로 필터. 생략 시 전체. 값은 [4. enum](#4-enum-정리) 참조 |

#### 응답 필드 (200)

| 위치 | 필드 | 타입 | 설명 |
| --- | --- | --- | --- |
| body | `unread_count` | integer | 미확인 알림 개수 (헤더 벨 배지) |
| body | `retention_days` | integer | 보관 기간(일). 현재 `7`. 하단 안내 문구용 |
| body | `notifications` | array | 알림 목록 (미확인 우선 > 최신순) |
| body | `notifications[].id` | integer | 알림 PK (확인 처리 시 사용) |
| body | `notifications[].category` | string | 카테고리 값 (`home_member` 등) |
| body | `notifications[].category_label` | string | 카테고리 한국어 표시 (예: `분담안`) |
| body | `notifications[].title` | string | 알림 제목 |
| body | `notifications[].body` | string | 보조 문구 (빈 문자열일 수 있음) |
| body | `notifications[].deep_link` | string | 탭 시 이동할 목적지 문자열 (빈 문자열일 수 있음) |
| body | `notifications[].is_read` | boolean | 확인 여부. `false`면 화면에서 강조 표시 |
| body | `notifications[].created_at` | datetime | 발생 시각 (ISO8601) |

#### 응답 예시

```json
{
  "unread_count": 3,
  "retention_days": 7,
  "notifications": [
    {
      "id": 12,
      "category": "assignment",
      "category_label": "분담안",
      "title": "다음 주 분담안이 생성됐어요",
      "body": "총 25개 집안일 · 2026-02-02 주차",
      "deep_link": "assignment:2026-02-02",
      "is_read": false,
      "created_at": "2026-02-01T21:05:00+09:00"
    }
  ]
}
```

#### 에러

| status | code | 의미 |
| --- | --- | --- |
| 400 | (검증 오류) | `category` 값이 허용 목록 밖 |
| 401 | `authentication_failed` | 인증 실패 |

#### curl

```bash
curl -H "Authorization: Bearer <access>" \
  "https://<host>/api/v1/notifications/?category=assignment"
```

---

### 3.2 알림 확인(읽음) 처리

```
POST /api/v1/notifications/{notification_id}/read/
```

알림을 확인(읽음) 처리한다. **본인 알림만** 가능하며, 이미 확인한 알림은 그대로 `200`을 반환한다(**멱등**). 처리된 알림 한 건을 반환한다.

#### 요청 파라미터

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| path | `notification_id` | integer | O | 확인할 알림 PK |
| body | - | - | - | 요청 본문 없음 |

#### 응답 필드 (200)

[3.1](#31-알림함-조회)의 `notifications[]` 원소와 동일한 단건 구조. 처리 후 `is_read`는 `true`.

| 위치 | 필드 | 타입 | 설명 |
| --- | --- | --- | --- |
| body | `id` | integer | 알림 PK |
| body | `category` | string | 카테고리 값 |
| body | `category_label` | string | 카테고리 한국어 표시 |
| body | `title` | string | 알림 제목 |
| body | `body` | string | 보조 문구 |
| body | `deep_link` | string | 이동 목적지 문자열 |
| body | `is_read` | boolean | 확인 여부 (처리 후 `true`) |
| body | `created_at` | datetime | 발생 시각 |

#### 응답 예시

```json
{
  "id": 12,
  "category": "assignment",
  "category_label": "분담안",
  "title": "다음 주 분담안이 생성됐어요",
  "body": "총 25개 집안일 · 2026-02-02 주차",
  "deep_link": "assignment:2026-02-02",
  "is_read": true,
  "created_at": "2026-02-01T21:05:00+09:00"
}
```

#### 에러

| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 인증 실패 |
| 404 | `not_found` | 본인 알림이 아니거나 존재하지 않음 |

#### curl

```bash
curl -X POST -H "Authorization: Bearer <access>" \
  "https://<host>/api/v1/notifications/12/read/"
```

---

### 3.3 푸시 설정 조회

```
GET /api/v1/notifications/settings/
```

마이 화면(`T5_My`)의 푸시 알림 토글 상태를 반환한다. 설정이 없으면 **전체 on 기본값으로 생성**해 반환한다.

`push_enabled`가 마스터 토글이며, 꺼지면 카테고리 값과 무관하게 푸시를 발송하지 않는다. 인앱 알림함 기록은 설정과 무관하게 항상 남는다.

#### 요청 파라미터

없음.

#### 응답 필드 (200)

| 위치 | 필드 | 타입 | 설명 |
| --- | --- | --- | --- |
| body | `push_enabled` | boolean | 푸시 전체 on/off (마스터 토글). 꺼지면 카테고리 무관하게 발송 안 함 |
| body | `home_member` | boolean | 집·구성원 알림 수신 여부 |
| body | `assignment` | boolean | 분담안 알림 수신 여부 |
| body | `board` | boolean | 보드 조율 알림 수신 여부 |
| body | `reward` | boolean | 리워드 알림 수신 여부 |
| body | `report` | boolean | 리포트 알림 수신 여부 |

#### 응답 예시

```json
{
  "push_enabled": true,
  "home_member": true,
  "assignment": true,
  "board": true,
  "reward": true,
  "report": true
}
```

#### 에러

| status | code | 의미 |
| --- | --- | --- |
| 401 | `authentication_failed` | 인증 실패 |

#### curl

```bash
curl -H "Authorization: Bearer <access>" \
  "https://<host>/api/v1/notifications/settings/"
```

---

### 3.4 푸시 설정 수정

```
PATCH /api/v1/notifications/settings/
```

푸시 알림 토글을 **부분 수정**한다. 전달된 키만 반영되며, 생략된 키는 기존 값을 유지한다. 수정 후 전체 설정을 반환한다(응답 구조는 [3.3](#33-푸시-설정-조회)과 동일).

#### 요청 파라미터

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| body | `push_enabled` | boolean | - | 푸시 전체 on/off |
| body | `home_member` | boolean | - | 집·구성원 알림 on/off |
| body | `assignment` | boolean | - | 분담안 알림 on/off |
| body | `board` | boolean | - | 보드 조율 알림 on/off |
| body | `reward` | boolean | - | 리워드 알림 on/off |
| body | `report` | boolean | - | 리포트 알림 on/off |

> 모든 필드가 선택값이다. 실제로 바꾸려는 토글만 담아 보내면 된다.

#### 요청 예시

```json
{ "board": false }
```

```json
{ "push_enabled": false }
```

#### 응답 예시 (200)

```json
{
  "push_enabled": true,
  "home_member": true,
  "assignment": true,
  "board": false,
  "reward": true,
  "report": true
}
```

#### 에러

| status | code | 의미 |
| --- | --- | --- |
| 400 | (검증 오류) | 필드 값 타입 불일치 등 입력 검증 실패 |
| 401 | `authentication_failed` | 인증 실패 |

#### curl

```bash
curl -X PATCH -H "Authorization: Bearer <access>" \
  -H "Content-Type: application/json" \
  -d '{"board": false}' \
  "https://<host>/api/v1/notifications/settings/"
```

---

### 3.5 분담안 생성 재촉 (nudge)

```
POST /api/v1/homes/mine/assignments/nudge/
```

분담안이 아직 없을 때 **구성원이 관리자에게** 생성을 요청한다. 관리자에게 `이번 주 분담안을 기다리고 있어요` 알림(카테고리 `assignment`)이 적재된다. 관리자에게만 전달된다.

> URL은 분담안 흐름(`/api/v1/homes/mine/assignments/`)에 붙지만, 동작은 알림 도메인의 알림 적재다.

#### 요청 파라미터

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| body | `week_start` | date (`YYYY-MM-DD`) | - | 대상 주차의 **월요일** 날짜. 생략 시 이번 주차 |

> `week_start`는 반드시 **월요일**이어야 한다. 월요일이 아니면 `400`(검증 오류: "week_start 는 월요일 날짜여야 합니다.").

#### 요청 예시

```json
{}
```

```json
{ "week_start": "2026-07-20" }
```

#### 응답 필드 (201)

| 위치 | 필드 | 타입 | 설명 |
| --- | --- | --- | --- |
| body | `notified_count` | integer | 알림을 받은 관리자 수 |

#### 응답 예시

```json
{ "notified_count": 1 }
```

#### 에러

| status | code | 의미 |
| --- | --- | --- |
| 400 | (검증 오류) | `week_start` 형식 오류 또는 월요일이 아님 |
| 401 | `authentication_failed` | 인증 실패 |
| 404 | `not_found` | 속한 집이 없음 |

#### curl

```bash
curl -X POST -H "Authorization: Bearer <access>" \
  -H "Content-Type: application/json" \
  -d '{}' \
  "https://<host>/api/v1/homes/mine/assignments/nudge/"
```

---

## 4. enum 정리

### 알림 카테고리 (`category` / `category_label`)

알림함 필터(`category` 쿼리)와 푸시 설정 토글이 **같은 분류**를 쓴다. `전체`는 필터 값일 뿐 저장되는 카테고리가 아니므로, 전체 조회 시에는 `category`를 **생략**한다.

| 값 (`category`) | 화면 라벨 (`category_label`) | 푸시 설정 필드 |
| --- | --- | --- |
| `home_member` | 집·구성원 | `home_member` |
| `assignment` | 분담안 | `assignment` |
| `board` | 보드 조율 | `board` |
| `reward` | 리워드 | `reward` |
| `report` | 리포트 | `report` |

### 카테고리별 알림 발생 지점 (참고)

| 시점 | 카테고리 | 제목 예시 |
| --- | --- | --- |
| 분담안 생성 | `assignment` | 분담안이 생성됐어요 |
| 분담안 확정 | `assignment` | 분담안이 확정됐어요 |
| 구성원이 관리자에게 재촉(nudge) | `assignment` | 이번 주 분담안을 기다리고 있어요 |
| 도움 요청 등록 | `board` | 도움이 필요해요 (닉네임) |
| 도움 요청 수락 | `board` | 도움 요청이 수락됐어요 |
| 교환 요청 도착 | `board` | 교환 요청이 도착했어요 |
| 교환 수락 / 거절 | `board` | 교환 요청이 수락됐어요 / 아쉽지만 다음에 교환해요 |
| 리워드 수령 | `reward` | 리워드가 수령됐어요 (닉네임) |
| 주간 리포트 생성 | `report` | 이번 주 리포트가 도착했어요 |

---

## 5. FE 연동 팁 / 주의사항

- **벨 배지**: 헤더 미확인 배지는 알림함 응답의 `unread_count`를 그대로 쓴다. 목록을 다시 불러오지 않아도 되도록, 확인 처리 성공 시 로컬에서 배지를 1 감소시키고 서버 값과 주기적으로 동기화하는 것을 권장.
- **미확인 강조**: `is_read === false`인 행만 강조 표시한다. 정렬은 서버가 미확인 우선 > 최신순으로 이미 내려주므로 FE에서 재정렬하지 않아도 된다.
- **확인 처리는 멱등**: 이미 읽은 알림을 다시 `read/` 호출해도 `200`이 온다. 중복 탭/재시도에 안전하다.
- **딥링크 만료 처리**: `deep_link`로 이동했을 때 대상(주차/카드)이 만료·처리 완료 상태면 앱이 만료 토스트를 대신 노출한다. 딥링크 랜딩 실패를 에러가 아닌 정상 흐름으로 다룰 것.
- **보관 안내 문구**: 하드코딩 대신 응답의 `retention_days`(현재 `7`)를 사용해 "N일 전 알림까지 확인할 수 있어요" 문구를 구성한다.
- **알림함 vs 푸시 설정 분리**: 푸시 설정을 모두 꺼도 인앱 알림함에는 계속 레코드가 쌓인다. "알림을 껐는데 알림함에 남아 있다"는 것은 정상 동작임을 UX에서 오해 없게 다룰 것.
- **마스터 토글 UI**: `push_enabled`가 꺼진 상태에서는 카테고리 토글이 무의미하다(발송 안 됨). 마스터 off 시 하위 토글을 비활성/흐리게 처리하는 것을 권장.
- **부분 수정(PATCH)**: 설정 수정은 바꾸려는 키만 보내면 된다. 전체 payload를 보낼 필요 없음.
- **nudge의 `week_start`는 월요일 고정**: 캘린더에서 임의 날짜를 넘기면 `400`이 난다. 반드시 해당 주차의 월요일로 정규화해 전송한다. 이번 주 재촉이면 `week_start`를 생략하는 것이 가장 안전하다.
- **푸시 발송 보류 상태**: 실제 푸시 도착에 의존하는 플로우(예: 푸시 수신 후 특정 화면 진입)는 현재 동작하지 않을 수 있다. 알림함 조회 기반으로 설계할 것.

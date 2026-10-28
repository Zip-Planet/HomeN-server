# Notifications (알림) 스펙

## 개요

인앱 알림함(`N1_NotificationInbox`)과 푸시 설정(`T5_My`)을 담당한다.
알림함과 푸시는 **문구·랜딩이 동일**하므로 같은 레코드를 근거로 한다.

> **푸시 인프라는 FCM(Firebase Cloud Messaging)** 이다. 기기 등록·해제 API와 유저 단위 발송
> 서비스(`send_push_to_user`)·테스트 발송까지 구현돼 있고, 알림 이벤트(`notify`)와 발송의 **연결은
> 아직 하지 않았다** (`apps/notifications/services.py` 의 TODO).

---

## 모델

### Notification
| 필드 | 타입 | 설명 |
|------|------|------|
| home | ForeignKey(Home) | 발생한 집 |
| recipient | ForeignKey(User) | 수신자 |
| category | CharField(choices) | 카테고리 5종 |
| title | CharField(100) | 제목 |
| body | CharField(200) | 보조 문구 |
| deep_link | CharField(200) | 탭 시 이동 목적지 문자열 |
| read_at | DateTimeField(null) | 확인 시각. null 이면 미확인 |
| created_at | DateTimeField | 발생 시각 |

### NotificationSetting
| 필드 | 타입 | 설명 |
|------|------|------|
| user | OneToOneField(User) | 대상 유저 |
| push_enabled | BooleanField | **마스터 토글** |
| home_member / assignment / board / reward / report | BooleanField | 카테고리별 토글 |

마스터가 꺼지면 카테고리 값과 무관하게 푸시를 발송하지 않는다.
**인앱 알림함 기록은 설정과 무관하게 항상 남는다** — 알림함은 기록이고 토글은 발송 제어다.

### Device
| 필드 | 타입 | 설명 |
|------|------|------|
| user | ForeignKey(User) | 현재 이 기기로 로그인한 유저 |
| registration_id | CharField(255, unique) | FCM registration token 또는 FID. **전역 유일** |
| kind | CharField(choices) | `token`(기본) / `fid` — 발송 시 `Message(token=)` / `Message(fid=)` 분기 |
| platform | CharField(choices) | `ios` / `android` |
| app_version | CharField(32) | 앱 버전 (선택) |
| is_active | BooleanField | 발송 대상 여부. 로그아웃·FCM UNREGISTERED 응답 시 False |
| created_at | DateTimeField | 최초 등록 시각 |
| last_seen_at | DateTimeField | 마지막 등록(업로드) 시각 — 등록 호출마다 갱신 |

- 같은 `registration_id` 를 다른 유저가 등록하면 행을 새 유저로 옮긴다 (기기 공유 시 이전 계정 푸시 누출 방지).
- FCM 은 registration token → FID(Firebase Installation ID) 로 전환 중이라 둘 다 받는다. 앱이 어느 모드를 켰는지 `kind` 로 알려준다.

---

## 카테고리

알림함 필터와 푸시 설정이 같은 분류를 쓴다 (`전체` 는 필터 값일 뿐 저장 카테고리가 아니다).

| 값 | 화면 라벨 |
|----|-----------|
| `home_member` | 집·구성원 |
| `assignment` | 분담안 |
| `board` | 보드 조율 |
| `reward` | 리워드 |
| `report` | 리포트 |

---

## 정책

- **정렬**: 미확인 우선 > 최신순.
- **보관**: 발생 후 **7일**이 지나면 삭제 (화면 하단 "7일 전 알림까지 확인할 수 있어요").
- **랜딩**: `deep_link` 로 이동. 대상 주차가 지났거나 이미 처리된 카드처럼 랜딩할 수 없으면
  앱이 만료 토스트를 대신 노출한다.
- **확인 처리**는 본인 알림만 가능하며 멱등이다.

| 커맨드 | 스케줄 | 동작 |
|--------|--------|------|
| `purge_notifications` | 매일 (`0 4 * * *`, TZ=Asia/Seoul) | 7일 지난 알림 삭제 |
| `send_test_push --user <id> [--title] [--body] [--dry-run]` | 수동 | 유저의 활성 기기 전부에 테스트 푸시 (백엔드 검증용) |

### 푸시 발송 (`send_push_to_user`)
- 유저의 `is_active` 기기를 `kind` 별로 묶어 `firebase-admin` 의 `send_each_for_multicast` 로 보낸다 (한 번에 500개).
- FCM 이 `UNREGISTERED`(404) 또는 `INVALID_ARGUMENT`(400) 로 답한 기기는 `is_active=False` 처리한다.
- `dry_run=True` 면 FCM 검증만 하고 실제 전달하지 않는다.
- `FIREBASE_CREDENTIALS_JSON` 이 비어 있으면 `PushNotConfiguredError` (API 는 503 `push_unavailable`). 서버 기동·테스트에는 영향 없음.

---

## 발생 지점

| 시점 | 카테고리 | 제목 |
|------|----------|------|
| 분담안 생성 | `assignment` | 분담안이 생성됐어요 |
| 분담안 확정 | `assignment` | 분담안이 확정됐어요 |
| 구성원이 관리자에게 재촉 | `assignment` | 이번 주 분담안을 기다리고 있어요 |
| 도움 요청 등록 | `board` | 도움이 필요해요 (닉네임) |
| 도움 요청 수락 | `board` | 도움 요청이 수락됐어요 |
| 교환 요청 도착 | `board` | 교환 요청이 도착했어요 (상대에게만) |
| 교환 수락 / 거절 | `board` | 교환 요청이 수락됐어요 / 아쉽지만 다음에 교환해요 (요청자에게만) |
| 리워드 수령 | `reward` | 리워드가 수령됐어요 (닉네임) |
| 주간 리포트 생성 | `report` | 이번 주 리포트가 도착했어요 |

### 분담안 생성 재촉 (nudge)
최종 design 2 에서 추가된 기능. 분담안이 없을 때 **구성원이 관리자에게** 생성을 요청한다.
관리자에게만 알림이 전달된다.

---

## API 엔드포인트

모두 인증 필요.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/v1/notifications/?category=` | 알림함 (미확인 개수 + 목록) |
| POST | `/api/v1/notifications/{id}/read/` | 확인 처리 |
| GET | `/api/v1/notifications/settings/` | 푸시 설정 조회 (없으면 기본값 생성) |
| PATCH | `/api/v1/notifications/settings/` | 푸시 설정 부분 수정 |
| POST | `/api/v1/homes/mine/assignments/nudge/` | 분담안 생성 재촉 (구성원 → 관리자) |
| PUT | `/api/v1/users/me/devices/` | 푸시 기기 등록 (201 생성 / 200 갱신, 앱 시작마다 호출) |
| POST | `/api/v1/users/me/devices/unregister/` | 푸시 기기 해제 (로그아웃 시, 204 멱등) |
| POST | `/api/v1/notifications/test/` | 본인 기기로 테스트 푸시 (분당 5회, `PUSH_TEST_ENDPOINT_ENABLED` 꺼지면 404) |

**GET /api/v1/notifications/ 응답**
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

**PUT /api/v1/users/me/devices/ 요청**
```json
{"registration_id": "dXh3…:APA91b…", "platform": "ios", "kind": "token", "app_version": "1.2.0"}
```

**응답 (201 생성 / 200 갱신)**
```json
{"registration_id": "dXh3…:APA91b…", "kind": "token", "platform": "ios", "app_version": "1.2.0", "is_active": true, "last_seen_at": "2026-10-28T14:00:00+09:00"}
```

**POST /api/v1/notifications/test/ 요청·응답**
```json
{"title": "HomeN 테스트 알림", "body": "푸시 설정이 정상적으로 동작하고 있어요.", "dry_run": false}
```
```json
{"sent": 1, "failed": 0, "deactivated": 0}
```

---

## 필수 환경 변수
| 변수 | 설명 |
|------|------|
| `FIREBASE_CREDENTIALS_JSON` | Firebase 서비스 계정 JSON (한 줄). 비어 있으면 푸시 발송 비활성 |
| `PUSH_TEST_ENDPOINT_ENABLED` | 테스트 푸시 엔드포인트 노출 여부 (기본 `DEBUG` 와 동일) |

iOS 로 보내려면 Firebase 콘솔 > 프로젝트 설정 > Cloud Messaging 에 APNs 인증 키(.p8)가 등록돼 있어야 한다 (없으면 `ThirdPartyAuthError`).

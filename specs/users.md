# Users 스펙

## 개요
카카오 / 애플 SSO 기반 로그인 API. 이메일·비밀번호 인증은 지원하지 않습니다.
소셜 제공자의 고유 ID(`provider_id`)로 유저를 식별하며, 인증 성공 시 자체 JWT(Access + Refresh)를 발급합니다.

---

## 모델

### ProfileImage
| 필드 | 타입 | 설명 |
|------|------|------|
| id | BigAutoField | PK |
| image | ImageField | 이미지 파일 (`preset_profiles/` 하위 저장, 추후 S3) |

### User
| 필드 | 타입 | 설명 |
|------|------|------|
| id | BigAutoField | PK |
| uid | UUIDField(unique) | 자동 생성 고유 식별자 |
| name | CharField(8) | 닉네임 (한글·영문·숫자, 최대 8자, 서비스 내 별도 입력) |
| profile_image | ForeignKey(ProfileImage, nullable) | 선택된 프로필 이미지 (미설정 시 null) |
| is_active | BooleanField | 계정 활성 여부 (기본: True) |
| is_staff | BooleanField | 어드민 접근 여부 (기본: False) |
| created_at | DateTimeField | 가입 일시 |
| updated_at | DateTimeField | 최종 수정 일시 |

> `is_profile_set`: `name != ""` AND `profile_image is not null` 인 경우 True (모델 프로퍼티).

### SocialAccount
| 필드 | 타입 | 설명 |
|------|------|------|
| id | BigAutoField | PK |
| user | ForeignKey(User) | 연결된 유저 |
| provider | CharField(20) | 소셜 제공자 ('kakao' 또는 'apple') |
| provider_id | CharField(255) | 제공자가 발급한 고유 유저 ID |
| created_at | DateTimeField | 연결 일시 |
| updated_at | DateTimeField | 최종 수정 일시 |

> `(provider, provider_id)` 조합은 유니크 제약 조건이 적용됩니다.

---

## API 엔드포인트

### POST /api/v1/auth/kakao/
카카오 인가 코드로 로그인 또는 회원가입을 처리합니다.
`SocialAccount`에 `(kakao, provider_id)`가 없으면 신규 유저를 생성합니다.

**Request Body**
```json
{
  "code": "카카오_인가_코드"
}
```

**Response 200**
```json
{
  "access": "<access_token>",
  "refresh": "<refresh_token>",
  "is_profile_set": false
}
```

> `is_profile_set`이 `false`이면 클라이언트는 프로필 설정 플로우로 이동해야 합니다.

**Error 401** — 카카오 인증 실패
```json
{"error": {"code": "authentication_failed", "message": "카카오 토큰 교환 실패: ..."}}
```

---

### POST /api/v1/auth/apple/
Apple 인가 코드로 로그인 또는 회원가입을 처리합니다.
`SocialAccount`에 `(apple, provider_id)`가 없으면 신규 유저를 생성합니다.

> **Android 환경**: iOS Native(Bundle ID)와 달리 Android/웹에서는 Apple **Service ID**를 `APPLE_CLIENT_ID`로 사용하고 `APPLE_REDIRECT_URI` 설정이 필요합니다.

**Request Body**
```json
{
  "code": "애플_인가_코드"
}
```

**Response 200**
```json
{
  "access": "<access_token>",
  "refresh": "<refresh_token>",
  "is_profile_set": false
}
```

**Error 401** — 애플 인증 실패
```json
{"error": {"code": "authentication_failed", "message": "Apple 토큰 교환 실패: ..."}}
```

---

### GET /api/v1/users/me/
현재 로그인한 유저의 프로필을 조회합니다. (인증 필요)

**Response 200**
```json
{
  "uid": "<uuid>",
  "name": "홍길동",
  "profile_image": {
    "id": 3,
    "url": "http://example.com/media/preset_profiles/3.png"
  },
  "is_profile_set": true
}
```

---

### PATCH /api/v1/users/me/
현재 로그인한 유저의 닉네임과 프로필 이미지를 설정합니다. (인증 필요)

**Request Body**
```json
{
  "name": "홍길동",
  "profile_image": 3
}
```

> `profile_image`는 `GET /api/v1/users/profile-images/`에서 반환된 이미지 ID입니다.

**닉네임 규칙**: 한글·영문·숫자만 허용, 최대 8자, 전체 유저 내 유일해야 함.

**Response 200** — 업데이트된 프로필
```json
{
  "uid": "<uuid>",
  "name": "홍길동",
  "profile_image": {
    "id": 3,
    "url": "http://example.com/media/preset_profiles/3.png"
  },
  "is_profile_set": true
}
```

**Error 400** — 닉네임 중복
```json
{"error": {"code": "duplicate_nickname", "message": "이미 사용 중인 닉네임입니다."}}
```

---

### GET /api/v1/users/nicknames/{nickname}/
닉네임 사용 가능 여부를 확인합니다. (인증 필요)

**Response 200**
```json
{"is_available": true}
```

---

### GET /api/v1/users/profile-images/
선택 가능한 프리셋 프로필 이미지 목록을 반환합니다. (인증 불필요)

**Response 200**
```json
[
  {"id": 1, "url": "http://example.com/media/preset_profiles/1.png"},
  {"id": 2, "url": "http://example.com/media/preset_profiles/2.png"}
]
```

> 이미지 파일은 현재 Django 로컬 스토리지(`media/preset_profiles/`)에 저장하며, 추후 S3로 마이그레이션 예정입니다.
> 프리셋 이미지는 관리자 또는 배포 스크립트를 통해 사전에 등록해야 합니다.

---

### POST /api/v1/auth/token/refresh/
Access 토큰을 갱신합니다.

**Request Body**
```json
{"refresh": "<refresh_token>"}
```

**Response 200**
```json
{"access": "<new_access_token>"}
```

---

## 인증 설정
- Access 토큰 만료: 1시간
- Refresh 토큰 만료: 7일
- Header: `Authorization: Bearer <access_token>`

## 필수 환경 변수
| 변수 | 설명 |
|------|------|
| `KAKAO_REST_API_KEY` | 카카오 REST API 키 |
| `KAKAO_CLIENT_SECRET` | 카카오 Client Secret (보안 강화 시 사용) |
| `KAKAO_REDIRECT_URI` | 카카오 Redirect URI |
| `APPLE_TEAM_ID` | Apple Developer Team ID |
| `APPLE_CLIENT_ID` | iOS: Bundle ID / Android·웹: Service ID |
| `APPLE_KEY_ID` | Apple Sign In Key ID |
| `APPLE_PRIVATE_KEY` | Apple ES256 개인키 (줄바꿈은 `\n`으로 입력) |
| `APPLE_REDIRECT_URI` | Apple Redirect URI (Android·웹 플로우에서 필수) |

---

## 유저 식별 원칙
- 카카오와 애플은 **별개 계정**으로 관리됩니다 (자동 연동 없음).
- 재로그인 시 `SocialAccount.provider_id`로 동일 유저 여부를 판별합니다.
- 이메일은 저장하지 않습니다. 닉네임(`name`)과 프로필 이미지는 서비스 내 별도 입력으로 수집합니다.

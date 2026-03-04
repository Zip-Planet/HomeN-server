# Users 스펙

## 개요
카카오 / 애플 SSO 기반 로그인 API. 이메일·비밀번호 인증은 지원하지 않습니다.
소셜 제공자의 고유 ID(`provider_id`)로 유저를 식별하며, 인증 성공 시 자체 JWT(Access + Refresh)를 발급합니다.

---

## 모델

### User
| 필드 | 타입 | 설명 |
|------|------|------|
| id | BigAutoField | PK |
| uid | UUIDField(unique) | 자동 생성 고유 식별자 |
| name | CharField(50) | 닉네임 (서비스 내 별도 입력) |
| is_active | BooleanField | 계정 활성 여부 (기본: True) |
| is_staff | BooleanField | 어드민 접근 여부 (기본: False) |
| created_at | DateTimeField | 가입 일시 |
| updated_at | DateTimeField | 최종 수정 일시 |

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
  "refresh": "<refresh_token>"
}
```

**Error 401** — 카카오 인증 실패
```json
{"error": {"code": "authentication_failed", "message": "카카오 토큰 교환 실패: ..."}}
```

---

### POST /api/v1/auth/apple/
Apple 인가 코드로 로그인 또는 회원가입을 처리합니다.
`SocialAccount`에 `(apple, provider_id)`가 없으면 신규 유저를 생성합니다.

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
  "refresh": "<refresh_token>"
}
```

**Error 401** — 애플 인증 실패
```json
{"error": {"code": "authentication_failed", "message": "Apple 토큰 교환 실패: ..."}}
```

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

---

## 유저 식별 원칙
- 카카오와 애플은 **별개 계정**으로 관리됩니다 (자동 연동 없음).
- 재로그인 시 `SocialAccount.provider_id`로 동일 유저 여부를 판별합니다.
- 이메일은 저장하지 않습니다. 닉네임(`name`)은 서비스 내 별도 입력으로 수집합니다.

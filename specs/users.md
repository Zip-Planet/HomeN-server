# Users 스펙

## 개요
이메일 기반 회원가입/로그인 API. JWT 토큰(Access + Refresh) 발급.

## 모델

### User
| 필드 | 타입 | 설명 |
|------|------|------|
| id | BigAutoField | PK |
| email | EmailField(unique) | 로그인 ID |
| name | CharField(50) | 표시 이름 |
| password | CharField | 해시된 비밀번호 |
| is_active | BooleanField | 계정 활성 여부 (기본: True) |
| is_staff | BooleanField | 어드민 접근 여부 (기본: False) |
| created_at | DateTimeField | 가입 일시 |

## API 엔드포인트

### POST /api/v1/auth/signup/
회원가입.

**Request Body**
```json
{
  "email": "user@example.com",
  "password": "securepassword",
  "name": "홍길동"
}
```

**Response 201**
```json
{
  "id": 1,
  "email": "user@example.com",
  "name": "홍길동",
  "created_at": "2026-03-03T00:00:00Z"
}
```

**Error 400** — 유효성 검사 실패 또는 이메일 중복
```json
{"error": {"code": "email", "message": "이미 사용 중인 이메일입니다."}}
```

---

### POST /api/v1/auth/login/
로그인 후 JWT 토큰 반환.

**Request Body**
```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response 200**
```json
{
  "access": "<access_token>",
  "refresh": "<refresh_token>"
}
```

**Error 401** — 잘못된 인증 정보
```json
{"error": {"code": "authentication_failed", "message": "이메일 또는 비밀번호가 올바르지 않습니다."}}
```

---

### POST /api/v1/auth/token/refresh/
Access 토큰 갱신.

**Request Body**
```json
{"refresh": "<refresh_token>"}
```

**Response 200**
```json
{"access": "<new_access_token>"}
```

## 인증 설정
- Access 토큰 만료: 1시간
- Refresh 토큰 만료: 7일
- Header: `Authorization: Bearer <access_token>`

# CLAUDE.md — Homen Project Guidelines

> Django REST Framework API 서버 | Python 3.12+ | uv | Docker 컨테이너 배포

**트레이드오프:** 속도보다 신중함에 편향. 사소한 작업(오타, 한 줄 변경)에는 판단력을 사용하라.

---

## 행동 원칙

### 1. Think Before Coding
가정하지 마라. 불확실하면 질문. 여러 해석이 있으면 전부 제시. 더 단순한 접근이 있으면 말하라.

### 2. Simplicity First
요청받은 것만 구현. 추측성 추상화/유연성/에러 처리 금지. 200줄을 50줄로 줄일 수 있으면 다시 작성.

### 3. Surgical Changes
요청받은 것만 변경. 인접 코드 "개선" 금지. 기존 스타일 따라라. 내 변경으로 인한 고아 코드만 제거.

### 4. Goal-Driven Execution
성공 기준을 정의하고 검증될 때까지 반복. 다단계 작업은 `[단계] → 검증: [확인사항]` 형식으로 계획.

---

## Architecture

### 레이어 규칙

| 레이어 | 역할 | 금지 |
|--------|------|------|
| **views.py** | HTTP I/O, 시리얼라이제이션 | 비즈니스 로직, 직접 ORM 쿼리 |
| **serializers.py** | 입력 검증, 출력 포매팅 | 비즈니스 로직, DB 조작 |
| **services.py** | 비즈니스 로직, 쓰기 오케스트레이션 | HTTP 코드, 시리얼라이제이션 |
| **selectors.py** | 읽기 전용 쿼리 | 데이터 변경, HTTP 코드 |
| **models.py** | 데이터 구조, 제약조건 | 외부 API, HTTP 코드 |

View는 얇게 → Service에 위임. 쿼리 로직은 Selector에 분리.

### 앱 생성 규칙
- 모든 앱은 `apps/` 하위에 생성. AppConfig의 `name = "apps.<app_name>"`.
- 앱 내부에 `services.py`, `selectors.py`, `tests/` 반드시 포함.
- 공유 유틸리티는 `common/`에 배치.

### Settings
- `config/settings.py` 단일 파일. 환경별 분리하지 않음.
- 모든 환경 차이는 `.env` 파일 또는 환경변수로 주입 (`django-environ` 사용).
- 시크릿/설정값 코드 하드코딩 금지.

## Conventions

### Python / Django
- 타입 힌트 필수. Google style docstring.
- `snake_case` (변수/함수), `PascalCase` (클래스), `UPPER_CASE` (상수).
- f-string 사용. `select_related`/`prefetch_related`로 N+1 방지.

### DRF
- URL: 복수형 명사, `/api/v1/` prefix.
- 시리얼라이저 입력/출력 분리 가능 (`CreateSerializer`, `ListSerializer`).
- 커스텀 예외 핸들러로 일관된 에러 포맷.

### 테스트
- pytest 기반. 테스트 코드는 프레임워크 비종속으로 작성.
  - `test_services.py`: 순수 비즈니스 로직 테스트 (DRF 의존 금지). 프레임워크 교체 시 재사용 가능.
  - `test_views.py`: API 통합 테스트 (여기만 DRF 종속 허용).
- `pytest-django`는 DB 세팅 용도로만 사용. factory_boy로 데이터 생성.
- **테스트 DB는 반드시 PostgreSQL.** SQLite 금지.
- 서비스 레이어 테스트 최우선.

### Git
- Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`).

## 패키지 매니저
- `uv add/remove/sync`로 의존성 관리. `uv run`으로 명령 실행.

## MCP

- 에이전트에게는 **코드 생성만** 위임. Git/PR은 개발자가 직접.
- MCP 서버는 필요할 때만 활성화 (미사용 서버는 컨텍스트 소비).
- DB MCP는 읽기 전용 연결 기본. API 키는 환경변수로 관리.
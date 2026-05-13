# HomeN Backend Docs

본 디렉터리는 코드만으로는 드러나지 않는 약속(컨벤션·아키텍처·운영 절차) 의 단일 출처(Single Source of Truth) 다.
도메인 스펙(요구사항·기능 명세) 은 [`/specs`](../specs) 에, Claude Code 작업 지침은 [`/CLAUDE.md`](../CLAUDE.md) · [`/.ai/instructions.md`](../.ai/instructions.md) 에 있다.

## 문서 목록

| 문서 | 무엇이 들어있나 |
|---|---|
| [git-conventions.md](git-conventions.md) | 커밋 메시지 · PR 제목 · PR 본문 · 브랜치 네이밍 — Conventional Commits + Gitmoji. 작업 플로우 (issue ↔ branch ↔ commit ↔ PR). |
| [api-conventions.md](api-conventions.md) | URI · HTTP method · 상태 코드 · 인증 · 컨트롤러 작성 패턴. 외부 API 계약의 모든 규칙. |
| [swagger-conventions.md](swagger-conventions.md) | `@extend_schema` / `help_text` / `OpenApiExample` 사용 규칙. PR 전 swagger 검증 명령. |
| [architecture.md](architecture.md) | Django + DRF 앱 구조, selectors / services 패턴, 도메인 예외 → HTTP 매핑, 인증 / 요청 라이프사이클. |
| [migrations.md](migrations.md) | `makemigrations` / `migrate` 사용법, 단일 논리 변경 원칙, constraint 명명, 롤백 전략. |

## 1분 가이드

- **새 API 를 추가한다** → [architecture.md §"새 코드는 어디에?"](architecture.md#새-코드는-어디에-빠른-결정-가이드) + [swagger-conventions.md §1](swagger-conventions.md#1-컨트롤러-view--extend_schema-필수-항목)
- **PR 을 연다** → [git-conventions.md §9~§10](git-conventions.md#9-pr-제목) + 본 repo 의 [`PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md) 자동 채움
- **모델을 바꾼다** → [migrations.md](migrations.md) 의 체크리스트
- **swagger 가 깨졌다** → [swagger-conventions.md §6 (검증 명령)](swagger-conventions.md#6-검증-pr-전-확인)

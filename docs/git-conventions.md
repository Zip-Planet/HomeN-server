# Git & PR Conventions

본 문서는 커밋 메시지·PR 제목·PR 본문·브랜치 네이밍의 단일 출처(Single Source of Truth)다.
[Conventional Commits 1.0](https://www.conventionalcommits.org/) 을 기반으로 [Gitmoji](https://gitmoji.dev/) 이모지를 결합한 형식을 사용한다.

> **왜 이 규칙이 필요한가**
> 1. **History 가독성** — `git log` 만 봐도 변경 종류를 한눈에 파악
> 2. **Changelog 자동화** — Conventional Commits 호환 도구(`semantic-release`, `commitlint`, `conventional-changelog` 등) 와 자연스럽게 연동
> 3. **Semver 자동 산출** — `feat`/`fix`/`BREAKING CHANGE` 로 버전 bump 자동 결정
> 4. **PR 리뷰 효율** — 제목만 봐도 변경의 종류·범위·영향도가 명확

---

## 1. 커밋 메시지 형식

```
<gitmoji> <type>(<scope>): <subject>

<body>

<footer>
```

| 부분 | 필수 | 예 |
|---|---|---|
| Header (1줄) | ✅ | `✨ feat(homes): add invite-code lookup endpoint` |
| Body | 선택 | "왜" 변경했는지, 72자 wrap |
| Footer | 선택 | `Closes #42`, `BREAKING CHANGE: ...` |

Header 와 Body, Body 와 Footer 사이는 **빈 줄 1개**로 구분한다.

### 예시

```
✨ feat(homes): add invite-code lookup endpoint

기존에는 초대코드 검증을 join 단계에서만 했지만, FE 미리보기 화면을 위해
참여 전 조회 전용 엔드포인트를 추가. selectors 에서 invite_code 로 Home 을 직접
조회한다.

Closes #12
```

---

## 2. Type 표 (Conventional Commits 11종)

| Type | 의미 | Semver 영향 |
|---|---|---|
| `feat` | 새 기능 추가 | **MINOR** |
| `fix` | 버그 수정 | **PATCH** |
| `docs` | 문서만 변경 | — |
| `style` | 포매팅·세미콜론 등 의미 변화 없는 수정 | — |
| `refactor` | 동작 변화 없는 코드 구조 개선 | — |
| `test` | 테스트 추가/수정 | — |
| `perf` | 성능 개선 | PATCH |
| `chore` | 빌드·도구·설정 등 그 외 잡일 | — |
| `ci` | CI 설정·스크립트 변경 | — |
| `build` | 빌드 시스템·외부 의존성 변경 (`pyproject.toml`, `uv.lock`, `Dockerfile` 등) | — |
| `revert` | 이전 커밋 되돌리기 | — |

> **BREAKING CHANGE** 가 있으면 type 과 무관하게 **MAJOR** bump (§7 참고).

---

## 3. Gitmoji 표

### Type ↔ Gitmoji 권장 매핑

| Type | Gitmoji | 코드 | 의미 |
|---|---|---|---|
| `feat` | ✨ | `:sparkles:` | 새 기능 |
| `fix` | 🐛 | `:bug:` | 일반 버그 수정 |
| `docs` | 📝 | `:memo:` | 문서 |
| `style` | 🎨 | `:art:` | 코드 구조/포매팅 |
| `refactor` | ♻️ | `:recycle:` | 리팩토링 |
| `test` | ✅ | `:white_check_mark:` | 테스트 |
| `perf` | ⚡️ | `:zap:` | 성능 |
| `chore` | 🔧 | `:wrench:` | 설정 |
| `ci` | 💚 | `:green_heart:` | CI 수정 |
| `build` | 📦️ | `:package:` | 빌드/패키지 |
| `revert` | ⏪️ | `:rewind:` | 되돌리기 |

### 보조 Gitmoji (특수 상황)

| Gitmoji | 코드 | 사용 시점 |
|---|---|---|
| 🔥 | `:fire:` | 코드/파일 삭제 |
| 🚧 | `:construction:` | WIP (작업 중 임시 커밋) |
| 🚑️ | `:ambulance:` | Critical hotfix |
| 🩹 | `:adhesive_bandage:` | 사소한 비치명적 수정 |
| 🥅 | `:goal_net:` | 에러 처리 추가/개선 |
| ⬆️ | `:arrow_up:` | 의존성 업그레이드 |
| ⬇️ | `:arrow_down:` | 의존성 다운그레이드 |
| 🔒️ | `:lock:` | 보안 이슈 수정 |
| 🔖 | `:bookmark:` | 릴리스/버전 태그 |
| 🚀 | `:rocket:` | 배포 관련 |
| 🗃️ | `:card_file_box:` | DB 스키마/마이그레이션 |
| 🌐 | `:globe_with_meridians:` | i18n/l10n |
| ♿️ | `:wheelchair:` | 접근성 개선 |

> 전체 목록: https://gitmoji.dev/

---

## 4. Scope 가이드

Scope 는 **변경의 1차 영향 범위**다. 본 repo 의 권장 scope:

| Scope | 범위 |
|---|---|
| `<app>` | Django 앱 단위 (`users`, `homes` — `apps/<app>/`) |
| `core` | `config/` 전반 (settings, urls, asgi/wsgi), `common/` |
| `db` | 모델·마이그레이션 (`apps/**/models.py`, `apps/**/migrations/`) |
| `infra` | 배포·인프라 (`Dockerfile`, `docker-compose*.yml`, `Makefile`) |
| `deps` | 의존성 변경 (`pyproject.toml`, `uv.lock`) |
| `ci` | `.github/workflows/` |
| `docs` | `docs/`, `README.md`, `.github/*_TEMPLATE*` |

- 모르면 **생략 가능** (Conventional Commits 표준): `✨ feat: add login`
- 여러 scope 에 걸치면 가장 큰 단위 하나로 표기

---

## 5. Header 작성 규칙

1. **50자 이내** (Tim Pope 50/72 규칙). git CLI 도 50자에서 컬러 경고
2. **마침표 없음** — `add login.` ❌ → `add login` ✅
3. **명령형/현재형** — `added` ❌, `adds` ❌, `add` ✅
4. **소문자 시작** — `Add login` ❌ → `add login` ✅ (영문 기준)
5. **한글 사용 시**: 동사 종결 회피 (`로그인 추가` / `add login` ⭕ — `로그인을 추가했습니다.` ❌)
6. 한글/영문 혼용 허용 — 본 repo 의 `.github/PULL_REQUEST_TEMPLATE.md` 가 이미 양국어를 사용 중이니 일관성 유지

---

## 6. Body 작성 규칙

- **"왜" 가 우선, "무엇" 은 코드가 이미 보여줌**
- 한 줄 72자 wrap
- Header 와 빈 줄로 분리
- 여러 단락은 빈 줄로 구분

```
♻️ refactor(homes): split services into selectors and services

조회와 변경 책임이 한 모듈에 섞여 있어 테스트와 swagger 분기 케이스 작성이
까다로웠다. selectors 는 SELECT 만, services 는 INSERT/UPDATE/DELETE 만 책임
지도록 분리.

Refs #38
```

---

## 7. Breaking Change 표시

호환성을 깨는 변경은 **둘 다** 적용 권장(어느 도구가 어느 쪽을 인식하든 안전):

1. **Header 에 `!`**: `<type>(<scope>)!:`
2. **Footer 에 `BREAKING CHANGE:`** + 설명

```
✨ feat(api)!: switch response envelope to {data, meta}

BREAKING CHANGE: 모든 성공 응답이 {"data": ...} 형태로 래핑된다.
v1 클라이언트가 raw payload 를 가정한다면 호출부 수정 필요.
```

---

## 8. 좋은 예 / 나쁜 예

| ❌ Bad | ✅ Good | 이유 |
|---|---|---|
| `update code` | `♻️ refactor(homes): extract invite-code lookup into selectors` | type/scope/구체성 누락 |
| `🐛 fix bug.` | `🐛 fix(homes): handle invalid invite code as 404` | 마침표·구체성 |
| `Added new auth` | `✨ feat(users): add kakao social login` | 과거형·이모지·type 누락 |
| `feat: 집을 추가했습니다.` | `✨ feat(homes): add home create endpoint` | 동사 종결·이모지 누락 |
| `💄 update settings` | `🔧 chore(core): enable swagger persistAuthorization` | 잘못된 이모지(💄 는 UI용), scope 누락 |
| `✨ feat: a really long subject line that goes way past fifty chars and keeps going` | `✨ feat(homes): add starter-pack chore preview` (+ body 로 부연) | 50자 초과 — body 로 분리 |

---

## 9. PR 제목

**커밋 메시지 Header 와 동일한 형식**을 사용한다.

```
✨ feat(homes): add starter-pack chore preview
```

이유:
- Squash merge 가 default 일 때 PR 제목이 그대로 단일 커밋이 되므로 history 일관성
- 리뷰어가 PR 목록만 훑어도 변경 종류를 즉시 파악
- 이슈/PR 번호는 GitHub 이 자동으로 `(#123)` 을 추가하므로 직접 적지 않음

## 10. PR 본문

[`.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md) 가 자동으로 채워준다. 작성 팁:

- **한 PR = 한 가지 목적**: 작은 PR 이 리뷰가 빠르고 회귀가 적다. 여러 type 이 섞이면 분리.
- **Self-review 먼저**: PR 을 열기 전에 자기 PR 을 한 번 읽고 명백한 문제는 미리 정리.
- **스크린샷/GIF**: UI · 동작 변화는 첨부 (PR 템플릿의 `Attachment` 섹션).
- **Test plan**: 통합·단위 테스트 결과를 PR 템플릿의 해당 섹션에 명시.
- **Reviewer / Label**: 도메인 owner 를 reviewer 로, type 에 맞는 label 을 부착 (`✨ feature`, `🐞 bug` 등 기존 label 활용).

---

## 11. 이슈 연결 키워드

GitHub 은 PR 본문/커밋 footer 의 키워드를 인식해 issue 를 자동 처리한다. ([GitHub Docs](https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue))

| 키워드 | 동작 |
|---|---|
| `Closes #N` / `Close #N` | PR merge 시 #N **자동 close** |
| `Fixes #N` / `Fix #N` | 동일 — 자동 close (버그성 issue 에 관용적으로 사용) |
| `Resolves #N` / `Resolve #N` | 동일 — 자동 close |
| `Refs #N` / `Related to #N` | 단순 참조. close 되지 않음 |

같은 PR 에서 여러 issue 를 closing 하려면 키워드를 각각 적는다 — `Closes #1, #2` 는 인식되지 않는다.

```
Closes #12
Closes #15
Refs #20
```

---

## 12. 브랜치 네이밍

```
<type>/<issue-no>-<short-desc>
```

| Type | 예 |
|---|---|
| feat | `feat/12-homes-invite-preview` |
| fix | `fix/45-kakao-login-has-home` |
| docs | `docs/8-git-conventions` |
| refactor | `refactor/27-homes-services-split` |
| chore | `chore/33-deps-bump-django` |
| hotfix | `hotfix/91-token-refresh-rotation` |

- 소문자 + 하이픈
- **`<issue-no>` 는 권장** — 작업을 시작하기 전에 이슈를 먼저 발행한다 (이슈 → 브랜치 → 커밋 → PR 순서).
- GitHub 이슈 페이지의 **"Create a branch"** 버튼을 사용하면 issue ↔ branch 가 자동으로 link 된다.
  이때 base branch 를 **`dev`** 로 지정한다.
- 길어지면 의미 단어 위주로 축약.
- **예외**: 일회성 typo 수정 등 이슈로 추적할 가치가 없는 경우에만 issue 번호 생략 가능 — 이때는 `<type>/<scope>-<short-desc>` 형식 사용.

### 베이스 브랜치 정책

- **작업 브랜치는 항상 최신 `origin/dev` 에서 분기한다.** PR target 도 `dev`. `main` 은 릴리스/배포 트리거 전용이므로 일반 작업이 직접 들어가지 않는다 (`.github/workflows/deploy.yml` 이 `main` push 시 자동 배포).
- 작업 시작 전 권장:

```bash
git fetch origin
git switch -c <type>/<issue-no>-<short-desc> origin/dev
```

- 이미 만든 브랜치가 오래되어 `origin/dev` 에서 멀어졌다면 **rebase 로 최신화** (squash merge 가 기본이므로 merge commit 으로 따라잡지 않는다):

```bash
git fetch origin
git rebase origin/dev
```

---

## 13. 참고 자료

- **Gitmoji** — https://gitmoji.dev/
- **Conventional Commits 1.0.0** — https://www.conventionalcommits.org/
- **Tim Pope, "A Note About Git Commit Messages"** — https://tbaggery.com/2008/04/19/a-note-about-git-commit-messages.html
- **Semantic Versioning 2.0.0** — https://semver.org/
- **GitHub Docs — Linking a pull request to an issue** — https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue
- 본 repo 의 [`.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md)

---

## 14. 작업 플로우 (Issue ↔ Commit ↔ PR)

이슈 발행부터 merge · 공유까지 한 사이클이다. 별도의 자동화 도구 없이 **GitHub 기본 동작**(키워드 인식, 이슈 Timeline, Development sidebar) 만으로 양방향 가시화된다.

```
① 이슈 발행
   └─ .github/ISSUE_TEMPLATE/ 5 종 중 적절한 것 선택
   └─ 라벨 자동 부착 (🐞 bug / ✨ feature / 🔄 refactoring / 🚀 enhancement)
   └─ assignee 지정

② 브랜치 생성  (base = 최신 origin/dev)
   └─ git fetch origin
   └─ git switch -c <type>/<issue-no>-<short-desc> origin/dev
   └─ 또는 이슈 페이지의 "Create a branch" → base 를 dev 로 지정

③ 작업 / 커밋
   └─ 형식: <gitmoji> <type>(<scope>): <subject>   (§1~§8)
   └─ 진행 중 커밋 footer: Refs #N   (link 만, close 안 함)
   └─ origin/dev 에서 멀어졌으면 git rebase origin/dev 로 최신화

④ PR 생성  (target: dev)
   └─ PR 제목도 커밋 Header 와 동일 형식 (§9)
   └─ PR 본문 "연관된 이슈" 섹션의 `Closes #` 뒤에 이슈 번호 채움
       (PR merge 시 이슈 자동 close 트리거)
   └─ main 은 릴리스/배포 전용 — 일반 작업은 dev 로만 합친다

⑤ Merge → 이슈 자동 close → 공유
   └─ 이슈 Timeline 에 commit/PR 이 자동 노출 → 다른 팀원이 진행/연관 작업 확인
   └─ PR 페이지의 Linked issues 에 이슈가 노출
```

### 왜 이 흐름인가

- **이슈 = 단일 논의 지점**: "이 작업은 왜·언제·누가 했나" 의 맥락이 이슈 한 곳에 누적된다.
  브랜치명·PR·커밋 footer 가 모두 이슈를 가리키므로 GitHub UI 에서 자동 집계된다.
- **브랜치명에 issue 번호**: `git branch -a`, PR 목록, CI 로그 어디서 봐도 어떤 이슈의 작업인지 즉시 식별 가능.
- **`Closes #N` 을 PR 템플릿에 미리 박아둠**: 사람이 잊어도 기본값이 안전한 쪽 — merge 하면 이슈가 닫힌다.

# Migrations

Django 마이그레이션 작성·검토·롤백 규칙. PR 템플릿의 **DB 마이그레이션 체크리스트** 가 본 문서를 가리킨다.

## 1. 파일 생성

```bash
python manage.py makemigrations <app>
# 또는 docker compose 환경
docker compose run --rm app python manage.py makemigrations <app>
```

- 항상 `<app>` 을 지정해 의도된 앱에만 마이그레이션이 생성되도록 한다.
- 자동 생성된 이름이 모호하면 `--name <short_desc>` 으로 명시 (예: `--name add_home_member_unique`).
- 결과 파일을 **반드시 PR 에 포함**한다 — 운영자가 별도로 만들지 않는다.

## 2. 단일 논리 변경 원칙

한 마이그레이션 = 한 논리 변경. 다음 두 가지가 섞이면 별도 파일로 분리:

- **스키마 변경** (`AlterField`, `AddIndex`, `AddConstraint`) — `python manage.py makemigrations` 결과를 그대로 사용.
- **데이터 마이그레이션** (`RunPython`, `RunSQL`) — `python manage.py makemigrations --empty <app>` 으로 빈 파일을 만들고 직접 작성.

데이터 마이그레이션을 같은 파일에 섞으면:
- 롤백 시 데이터만 되돌리기 어렵다.
- 운영 DB 의 거대 테이블에서 `RunPython` 이 stuck 되면 스키마 부분도 함께 멈춘다.

## 3. NOT NULL / 컬럼 추가 패턴

거대한 운영 테이블에 NOT NULL 컬럼을 추가할 때:

1. **마이그 1**: NULL 허용 + 데이터 백필 (`RunPython`).
2. **마이그 2**: NOT NULL 로 변경.

`makemigrations` 가 자동으로 만들어주지 않으므로, default 가 비-trivial 한 경우 수동 분리한다.

## 4. constraints / indexes 명명

`Meta.constraints` / `Meta.indexes` 에는 **명시적 `name=`** 을 부여한다. 자동 생성 이름은 Django 버전에 따라 바뀌어 PR 간 diff 가 어지러워진다.

```python
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=["name"],
            condition=models.Q(name__gt=""),
            name="unique_user_name_when_set",
        ),
    ]
    indexes = [
        models.Index(fields=["created_at"], name="users_created_at_idx"),
    ]
```

## 5. 롤백 가능성

- `RunPython` 은 **`reverse_code` 를 반드시 작성**한다. 실현 불가능하면 `migrations.RunPython.noop` 를 명시적으로 적어 의도된 단방향임을 표시.
- 로컬에서 사이클 테스트:

```bash
python manage.py migrate <app> <previous_revision>   # 롤백
python manage.py migrate <app>                       # 다시 적용
```

## 6. AUTH_USER_MODEL 변경

`config/settings.py` 의 `AUTH_USER_MODEL = "users.User"` 는 **변경 불가** 약속이다. 변경하려면 별도 RFC + 데이터 마이그레이션 전략이 필요하다 (`django-rename-app` 등 외부 도구).

## 7. CI 와 운영 적용

- CI 에서는 `pytest` 가 자동으로 마이그레이션을 적용한다 (`pytest-django` 기본 동작).
- 운영 배포는 `.github/workflows/deploy.yml` 의 마지막 스텝에서 `docker compose exec ... python manage.py migrate` 가 수행한다.
- 배포 직후 잘못된 마이그레이션을 발견하면 **새 마이그레이션으로 forward fix**가 기본이다. 운영 DB 에서 `migrate <app> <prev>` 를 통한 즉시 롤백은 데이터 손실 위험이 있어 신중히.

## 8. PR 체크리스트 (`PULL_REQUEST_TEMPLATE.md` 항목)

- [ ] `makemigrations` 결과가 단일 논리 변경
- [ ] 파일명이 자동 규칙 (`NNNN_<short>.py`) 을 따르며 시퀀스 안 끊김
- [ ] 데이터 마이그레이션은 스키마와 별도 파일
- [ ] constraint / index 에 명시적 `name=`
- [ ] 로컬에서 forward / reverse 사이클 통과 (또는 `RunPython.noop` 명시)
- [ ] CI workflow `tests` 통과

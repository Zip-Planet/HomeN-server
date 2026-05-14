"""dev 환경 어드민 시드 자격증명.

`seed_admins` 관리 커맨드와 Swagger DESCRIPTION 이 동일한 상수를 공유한다.
Django 의존을 두지 않아 settings 로드 단계에서도 안전하게 import 가능하다.
"""

SEED_ADMINS: tuple[dict[str, str], ...] = (
    {
        "uid": "00000000-0000-0000-0000-000000000001",
        "name": "admin1",
        "password": "AdminPass1!",
    },
    {
        "uid": "00000000-0000-0000-0000-000000000002",
        "name": "admin2",
        "password": "AdminPass2!",
    },
)

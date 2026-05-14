from django.core.management.base import BaseCommand

from apps.users.admin_seeds import SEED_ADMINS
from apps.users.models import User


class Command(BaseCommand):
    """dev 환경에서 사용할 어드민 계정 2개를 멱등 시드한다.

    `SEED_ADMINS` 의 각 항목에 대해:
      - 동일 `uid` 의 유저가 없으면 `create_superuser` 로 신규 생성.
      - 이미 존재하면 비밀번호와 어드민 플래그(`is_staff`, `is_superuser`, `is_active`) 만 동기화.

    배포 워크플로우의 `migrate` 다음 단계에서 호출되어 매 배포 시 멱등하게 실행된다.
    """

    help = "Seed admin users used for dev login and Swagger documentation."

    def handle(self, *args, **options) -> None:
        for spec in SEED_ADMINS:
            uid = spec["uid"]
            name = spec["name"]
            password = spec["password"]

            user = User.objects.filter(uid=uid).first()
            if user is None:
                User.objects.create_superuser(uid=uid, password=password, name=name)
                self.stdout.write(f"created {name}")
                continue

            user.set_password(password)
            user.name = name
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.save()
            self.stdout.write(f"updated {name}")

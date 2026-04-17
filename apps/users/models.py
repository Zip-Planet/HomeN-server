import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserProfileImage(models.IntegerChoices):
    """유저 프로필 이미지 enum.

    프론트엔드에서 값을 받아 해당하는 이미지를 렌더링합니다.
    """

    TYPE_1 = 1, "캐릭터 1"
    TYPE_2 = 2, "캐릭터 2"
    TYPE_3 = 3, "캐릭터 3"
    TYPE_4 = 4, "캐릭터 4"
    TYPE_5 = 5, "캐릭터 5"
    TYPE_6 = 6, "캐릭터 6"
    TYPE_7 = 7, "캐릭터 7"
    TYPE_8 = 8, "캐릭터 8"


class UserManager(BaseUserManager):
    """SSO 기반 커스텀 유저 매니저."""

    def create_user(self, name: str = "", **extra_fields) -> "User":
        """비밀번호 없이 유저를 생성합니다 (SSO 전용).

        Args:
            name: 표시 이름.
            **extra_fields: 추가 모델 필드.

        Returns:
            생성된 User 인스턴스.
        """
        user = self.model(name=name, **extra_fields)
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, uid: str, password: str, name: str = "admin", **extra_fields) -> "User":
        """비밀번호를 포함한 슈퍼유저를 생성합니다.

        Args:
            uid: 고유 식별자 (UUID 문자열).
            password: 원문 비밀번호.
            name: 표시 이름.
            **extra_fields: 추가 모델 필드.

        Returns:
            생성된 슈퍼유저 User 인스턴스.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        user = self.model(uid=uid, name=name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user


class User(AbstractBaseUser, PermissionsMixin):
    """SSO 기반 인증 유저 모델.

    비밀번호 로그인은 지원하지 않습니다. 카카오 또는 애플 SSO를 통해 생성됩니다.
    UUID로 식별하며 이메일은 저장하지 않습니다.

    Attributes:
        uid: 자동 생성되는 고유 UUID 식별자.
        name: 서비스에서 직접 입력받는 닉네임 (최대 8자, 한글·영문·숫자).
        profile_image: 선택된 프로필 이미지 enum 값 (미설정 시 null).
        is_active: 계정 활성 여부.
        is_staff: 어드민 접근 가능 여부.
        created_at: 가입 일시.
        updated_at: 최종 수정 일시.
    """

    uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=8, blank=True, default="")
    profile_image = models.IntegerField(choices=UserProfileImage.choices, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "uid"
    REQUIRED_FIELDS = ["name"]

    objects = UserManager()

    class Meta:
        db_table = "users"
        constraints = [
            models.UniqueConstraint(
                fields=["name"],
                condition=models.Q(name__gt=""),
                name="unique_user_name_when_set",
            )
        ]

    def __str__(self) -> str:
        return f"user:{self.pk}"

    @property
    def is_profile_set(self) -> bool:
        """닉네임과 프로필 이미지가 모두 설정된 경우 True를 반환합니다."""
        return bool(self.name) and self.profile_image is not None

    @property
    def has_home(self) -> bool:
        """집 관리자 또는 구성원에 속해있는 경우 True를 반환합니다."""
        return self.home_memberships.exists()


class SocialAccount(models.Model):
    """유저와 소셜 로그인 제공자를 연결하는 모델.

    Attributes:
        user: 연결된 유저.
        provider: 소셜 제공자 ('kakao' 또는 'apple').
        provider_id: 제공자가 발급한 고유 유저 ID.
        created_at: 소셜 계정 연결 일시.
        updated_at: 최종 수정 일시.
    """

    KAKAO = "kakao"
    APPLE = "apple"
    PROVIDER_CHOICES = [(KAKAO, "Kakao"), (APPLE, "Apple")]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="social_accounts")
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    provider_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "social_accounts"
        unique_together = [("provider", "provider_id")]

    def __str__(self) -> str:
        return f"{self.provider}:{self.provider_id}"

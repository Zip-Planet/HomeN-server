from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "django.contrib.postgres",
    # Local
    "apps.users",
    "apps.homes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL"),
}

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "EXCEPTION_HANDLER": "common.exceptions.custom_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "HomeN API",
    "DESCRIPTION": (
        "HomeN 서비스 REST API 명세.\n\n"
        "## 인증\n"
        "- 모든 보호된 엔드포인트는 `Authorization: Bearer <access_token>` 헤더를 요구한다.\n"
        "- access 토큰은 카카오/애플 소셜 로그인으로 발급한다 (`/api/v1/auth/kakao/`, `/api/v1/auth/apple/`).\n"
        "- access 만료 시 `/api/v1/auth/token/refresh/` 로 갱신, 로그아웃 시 `/api/v1/auth/logout/` 으로 폐기.\n\n"
        "## 도메인 컨텍스트\n"
        "- **Auth / Users**: 소셜 로그인, 본인 프로필 관리, 회원 탈퇴.\n"
        "- **Homes**: 집 생성·조회·삭제, 초대/참여/나가기, 관리자 양도, 집안일 추가·메모 수정.\n"
        "- **StarterPacks**: 사전 정의된 집안일 프리셋 목록 및 미리보기.\n\n"
        "## 규칙\n"
        "- 한 유저는 단 하나의 집에만 속한다.\n"
        "- 집당 관리자는 1명. 관리자만 집 삭제·집안일 등록·양도 가능.\n"
        "- 관리자는 직접 탈퇴/나가기가 불가하며, 양도 또는 집 삭제 후 가능.\n"
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SECURITY": [{"BearerAuth": []}],
    # HomeImageType / UserProfileImage 는 값(1~8)이 동일해 drf-spectacular 가 같은 choice set 으로
    # 병합하면서 enum 이름 충돌을 경고한다. 결정적 이름을 부여해 경고를 제거한다.
    "ENUM_NAME_OVERRIDES": {
        "ImageTypeEnum": "apps.homes.models.HomeImageType",
    },
    "TAGS": [
        {"name": "Auth", "description": "소셜 로그인 (Kakao/Apple), 로그아웃, 액세스 토큰 갱신."},
        {"name": "Users", "description": "본인 프로필 조회·수정·탈퇴, 프로필 이미지 프리셋."},
        {"name": "Homes", "description": "집 CRUD, 초대 / 참여 / 나가기, 관리자 양도, 집안일 관리."},
        {"name": "StarterPacks", "description": "사전 정의된 집안일 프리셋 목록과 미리보기."},
    ],
    "SWAGGER_UI_SETTINGS": {
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
        "docExpansion": "none",
        # Schemas 패널을 펼쳐 example 값이 한 번에 보이도록 한다.
        "defaultModelsExpandDepth": 2,
        "defaultModelExpandDepth": 3,
        # 요청 본문 편집기에 example value 를 자동 채워 사용성을 높인다.
        "tryItOutEnabled": True,
    },
    "CONTACT": {"name": "HomeN Backend", "email": "gitak.lee@theplatforms.io"},
    # field-level example 일괄 주입 (common.swagger.FIELD_EXAMPLES 참고).
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "common.swagger.add_field_examples",
    ],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# Kakao OAuth2
KAKAO_REST_API_KEY = env("KAKAO_REST_API_KEY", default="kakao-rest-api-key-placeholder")
KAKAO_ADMIN_KEY = env("KAKAO_ADMIN_KEY", default="")
KAKAO_CLIENT_SECRET = env("KAKAO_CLIENT_SECRET", default="")
KAKAO_REDIRECT_URI = env("KAKAO_REDIRECT_URI", default="http://localhost:8000/api/v1/auth/kakao/")

# Apple Sign In
APPLE_TEAM_ID = env("APPLE_TEAM_ID", default="APPLE_TEAM_ID_PLACEHOLDER")
APPLE_CLIENT_ID = env("APPLE_CLIENT_ID", default="com.example.app.placeholder")
APPLE_KEY_ID = env("APPLE_KEY_ID", default="APPLE_KEY_ID_PLACEHOLDER")
APPLE_PRIVATE_KEY = env(
    "APPLE_PRIVATE_KEY",
    default="-----BEGIN EC PRIVATE KEY-----\nPLACEHOLDER\n-----END EC PRIVATE KEY-----",
).replace("\\n", "\n")
APPLE_REDIRECT_URI = env("APPLE_REDIRECT_URI", default="https://localhost/api/v1/auth/apple/")

import django
from django.conf import settings


def pytest_configure() -> None:
    settings.DJANGO_SETTINGS_MODULE = "config.settings"
    django.setup()
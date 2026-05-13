"""에러 응답 스키마.

`common.exceptions.custom_exception_handler` 는 모든 DRF 예외를 다음 형식으로
일관되게 wrap 한다:

    {"error": {"code": "<도메인 key 또는 default_code>", "message": "<사용자 메시지>"}}

본 모듈의 시리얼라이저는 그 응답 모양을 OpenAPI 스키마에 반영해 Swagger UI 가
각 status code 별로 구조 + 예시를 노출할 수 있게 한다.

규칙:
- 4xx 응답에는 항상 `responses={STATUS: OpenApiResponse(response=ErrorResponseSerializer, ...)}`
  를 사용한다 (description 만 지정하는 것은 지양 — schema 가 비어 보임).
- 구체적인 메시지는 `examples=[OpenApiExample(value={"error": {...}}, response_only=True, status_codes=["..."])]`
  로 부착한다.
"""

from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "도메인 에러 (400)",
            value={"error": {"code": "already_has_home", "message": "이미 속한 집이 있습니다."}},
            response_only=True,
        ),
        OpenApiExample(
            "인증 실패 (401)",
            value={"error": {"code": "authentication_failed", "message": "Authentication credentials were not provided."}},
            response_only=True,
        ),
        OpenApiExample(
            "권한 없음 (403)",
            value={"error": {"code": "permission_denied", "message": "관리자만 집을 삭제할 수 있습니다."}},
            response_only=True,
        ),
        OpenApiExample(
            "리소스 없음 (404)",
            value={"error": {"code": "not_found", "message": "속한 집이 없습니다."}},
            response_only=True,
        ),
    ]
)
class ErrorBodySerializer(serializers.Serializer):
    """`error` 객체의 내부 구조.

    `code` 는 다음 중 하나:
    - DRF 표준 default_code (`authentication_failed`, `permission_denied`, `not_found`).
    - 도메인별 key (예: `already_has_home`, `home_has_members`, `ambiguous_chore_input`).
      `ValidationError({key: msg})` 패턴으로 발생시 자동 매핑된다 (custom_exception_handler 참고).
    """

    code = serializers.CharField(
        help_text="에러 코드 — DRF default_code 또는 도메인 key (예: 'already_has_home').",
    )
    message = serializers.CharField(
        help_text="사용자에게 표시할 에러 메시지 (한국어).",
    )


class ErrorResponseSerializer(serializers.Serializer):
    """모든 4xx/5xx 응답의 표준 wrapper.

    `common.exceptions.custom_exception_handler` 가 DRF 의 표준 예외를 본 모양으로
    변환한다. Swagger UI 의 각 에러 status code 응답 스키마로 사용된다.
    """

    error = ErrorBodySerializer(help_text="에러 본문 (code + message).")


def error_example(*, code: str, message: str, name: str | None = None) -> OpenApiExample:
    """`{"error": {"code": code, "message": message}}` 형식의 OpenApiExample 헬퍼.

    각 엔드포인트의 `@extend_schema(examples=[...])` 에서 status code 별 응답
    예시를 부착할 때 사용한다.

    Args:
        code: 에러 코드 (도메인 key 또는 DRF default_code).
        message: 사용자 메시지.
        name: OpenApiExample 의 표시 이름 (생략 시 code 그대로 사용).
    """
    return OpenApiExample(
        name or code,
        value={"error": {"code": code, "message": message}},
        response_only=True,
    )

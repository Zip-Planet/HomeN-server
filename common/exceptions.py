from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler


def custom_exception_handler(exc: Exception, context: dict) -> None:
    """일관된 에러 응답 포맷을 반환합니다.

    DRF 기본 핸들러를 감싸 아래 형식으로 응답을 통일합니다:
        {"error": {"code": "...", "message": "..."}}

    Args:
        exc: 발생한 예외.
        context: 뷰와 요청 정보를 담은 DRF 컨텍스트 딕셔너리.

    Returns:
        포맷된 에러 응답. 처리할 수 없는 예외면 None.
    """
    response = exception_handler(exc, context)

    if response is None:
        return None

    code = getattr(exc, "default_code", "error")
    if isinstance(exc, APIException) and isinstance(exc.detail, dict):
        first_key = next(iter(exc.detail))
        detail = exc.detail[first_key]
        message = detail[0] if isinstance(detail, list) else str(detail)
        code = first_key
    elif isinstance(exc, APIException) and isinstance(exc.detail, list):
        message = str(exc.detail[0])
    else:
        message = str(exc.detail) if isinstance(exc, APIException) else str(exc)

    response.data = {"error": {"code": code, "message": message}}
    return response

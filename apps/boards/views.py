"""집안 보드 컨트롤러 — 피드 조회, 도움/교환 카드 CRUD."""

from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.boards import selectors, services
from apps.boards.serializers import (
    BoardFeedOutputSerializer,
    BoardItemQuerySerializer,
    BoardSelectableItemSerializer,
    CoordinationRequestResultSerializer,
    HelpRequestCreateSerializer,
    SwapRequestCreateSerializer,
)
from apps.homes.models import HomeMember
from apps.homes.selectors import get_user_home
from apps.homes.services import week_start_of
from common.error_responses import ErrorResponseSerializer, error_example
from common.exceptions import Conflict

_AUTH_FAILED_EXAMPLE = error_example(
    code="authentication_failed",
    message="Authentication credentials were not provided.",
    name="인증 실패",
)

# Swagger 응답 예시용 구성원 객체.
_EXAMPLE_MEMBER_A = {"uid": "8f3e2b1a-1234-4abc-9def-1234567890ab", "name": "김현수", "profile_image": 2}
_EXAMPLE_MEMBER_B = {"uid": "1a2b3c4d-5678-4abc-9def-abcdef123456", "name": "김수환", "profile_image": 5}


def _handle(exc: services.BoardError):
    """보드 도메인 예외를 DRF 표준 예외로 매핑합니다."""
    if isinstance(exc, services.BoardNotFoundError):
        return NotFound(str(exc))
    if isinstance(exc, services.BoardPermissionError):
        return PermissionDenied({exc.code: str(exc)})
    if isinstance(exc, services.BoardConflictError):
        return Conflict({exc.code: str(exc)})
    return ValidationError({exc.code: str(exc)})


# 항목 요약 구조 — 피드 카드의 item / requester_item / target_item 과 조율 대상 목록이 공유한다.
_ITEM_SUMMARY_TABLE = (
    "| 필드 | 타입 | 설명 |\n"
    "| --- | --- | --- |\n"
    "| `id` | integer | 분담안 항목 PK |\n"
    "| `chore_name` | string | 집안일명 (생성 시점 스냅샷) |\n"
    "| `weekday` | integer | 실행 요일 (0=월 ~ 6=일) |\n"
    "| `weekday_label` | string | 요일 한글 라벨 |\n"
    "| `difficulty` | integer | 난이도 enum (스냅샷) |\n"
    "| `point` | integer | 포인트 (스냅샷) |\n"
    "| `date` | date | 실행 날짜 (`week_start + weekday`) |\n"
    "| `assignee` | object\\|null | 현재 담당자 `{uid, name, profile_image}` |\n"
)

# 조율 대상 목록 = 항목 요약 + 선택 가능 여부.
_SELECTABLE_ITEM_TABLE = (
    _ITEM_SUMMARY_TABLE
    + "| `is_requested` | boolean | 이미 대기 중인 조율 카드가 걸린 항목이면 true (선택 불가 표시) |\n\n"
)

# 조율 카드(도움/교환) 생성·수락·거절 공통 응답 표.
_COORDINATION_RESULT_TABLE = (
    "| 위치 | 필드 | 타입 | 설명 |\n"
    "| --- | --- | --- | --- |\n"
    "| body | `id` | integer | 조율 카드 PK |\n"
    "| body | `status` | string | `pending` / `accepted` / `rejected` / `expired` |\n\n"
)


class BoardFeedView(APIView):
    """보드 피드 조회."""

    @extend_schema(
        tags=["Boards"],
        summary="집안 보드 피드 조회",
        description=(
            "## 🔥 설명\n"
            "봇 카드와 조율 카드를 **시간순으로 병합**한 단일 피드를 반환한다(최신순). "
            "화면은 `week_start` 가 바뀌는 지점에 주차 구분선을 그린다.\n\n"
            "- `type=bot` — 페어봇 시스템 카드 4종: 분담안 제안 / 분담안 확정 / 주간 리포트 / 리워드 달성. "
            "문구용 수치는 발행 시점 스냅샷(`payload`)이다.\n"
            "- `type=help` — 도움 요청. `status` 는 pending(내가 도와줄게) / accepted(담당자 변경) / expired.\n"
            "- `type=swap` — 교환 요청. `status` 는 pending / accepted(담당자 맞바꿈) / rejected / expired.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "요청 파라미터 없음.\n\n"
            "## 📤 응답 (200)\n"
            "`cards[]` 배열. 원소는 `type` 으로 구분되며 공통/타입별 필드는 아래와 같다.\n\n"
            "| 위치 | 필드 | 타입 | 대상 type | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| body | `cards[].type` | string | 공통 | `bot` / `help` / `swap` |\n"
            "| body | `cards[].id` | integer | 공통 | 카드 PK (종류별 독립) |\n"
            "| body | `cards[].week_start` | date | 공통 | 카드가 속한 주차의 월요일 (구분선 기준) |\n"
            "| body | `cards[].created_at` | datetime | 공통 | 발행 시각 (정렬 기준) |\n"
            "| body | `cards[].kind` | string | bot | 봇 카드 종류 enum (4종) |\n"
            "| body | `cards[].kind_label` | string | bot | 봇 카드 종류 한국어 라벨 |\n"
            "| body | `cards[].payload` | object | bot | 문구용 스냅샷 (종류별 상이) |\n"
            "| body | `cards[].status` | string | help / swap | `pending` / `accepted` / `rejected` / `expired` |\n"
            "| body | `cards[].message` | string | help / swap | 작성 메시지 (최대 30자, 빈 문자열 가능) |\n"
            "| body | `cards[].requester` | object\\|null | help / swap | 요청자 `{uid, name, profile_image}` |\n"
            "| body | `cards[].accepted_by` | object\\|null | help | 도움 수락자 |\n"
            "| body | `cards[].responded_by` | object\\|null | swap | 교환 응답자(수락/거절) |\n"
            "| body | `cards[].item` | object | help | 도움 요청 대상 항목 요약 |\n"
            "| body | `cards[].requester_item` | object | swap | 교환 — 요청자 항목 요약 |\n"
            "| body | `cards[].target_item` | object | swap | 교환 — 상대 항목 요약 |\n\n"
            "**항목 요약 구조** (`item` / `requester_item` / `target_item` 공통):\n\n"
            + _ITEM_SUMMARY_TABLE
            + "\n## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 404 | `not_found` | 속한 집이 없음 |\n"
        ),
        responses={
            200: BoardFeedOutputSerializer,
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="속한 집이 없음."),
        },
        examples=[
            OpenApiExample(
                "보드 피드",
                value={
                    "cards": [
                        {
                            "type": "swap",
                            "id": 12,
                            "week_start": "2026-07-20",
                            "created_at": "2026-07-22T09:14:00+09:00",
                            "status": "pending",
                            "message": "토요일에 일정이 생겨서 바꿔줄 수 있어?",
                            "requester": _EXAMPLE_MEMBER_A,
                            "responded_by": None,
                            "requester_item": {
                                "id": 31,
                                "chore_name": "분리수거",
                                "weekday": 5,
                                "weekday_label": "토",
                                "difficulty": 3,
                                "point": 120,
                                "date": "2026-07-25",
                                "assignee": _EXAMPLE_MEMBER_A,
                            },
                            "target_item": {
                                "id": 44,
                                "chore_name": "화장실 청소",
                                "weekday": 2,
                                "weekday_label": "수",
                                "difficulty": 4,
                                "point": 160,
                                "date": "2026-07-22",
                                "assignee": _EXAMPLE_MEMBER_B,
                            },
                        },
                        {
                            "type": "bot",
                            "id": 5,
                            "week_start": "2026-07-20",
                            "created_at": "2026-07-20T21:05:00+09:00",
                            "kind": "weekly_report",
                            "kind_label": "주간 리포트",
                            "payload": {"completion_rate": 0.82, "mvp": "김현수"},
                        },
                    ]
                },
                response_only=True,
                status_codes=["200"],
            ),
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="속한 집이 없습니다.", name="집 미존재"),
        ],
    )
    def get(self, request: Request) -> Response:
        home = get_user_home(request.user)
        if home is None:
            raise NotFound("속한 집이 없습니다.")

        return Response({"cards": selectors.get_board_feed(home=home)})


class BoardItemListView(APIView):
    """조율 카드 생성용 항목 목록 (인라인 아코디언)."""

    @extend_schema(
        tags=["Boards"],
        summary="조율 대상 집안일 목록",
        description=(
            "## 🔥 설명\n"
            "도움/교환 카드 생성 화면의 아코디언에 채울 항목 목록. **확정 분담안의 미완료 항목**만 "
            "반환하며, 이미 대기 중인 조율 카드가 걸린 항목은 `is_requested=true` 로 표시된다 "
            "(화면의 \"이미 도움 요청한 집안일이에요\").\n\n"
            "도움 요청 화면은 `assignee=me` 로, 교환 대상 선택은 담당자 필터 칩에 맞춰 uid 로 호출한다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| query | `week_start` | date |  | 대상 주차의 월요일. 생략 시 이번 주차 |\n"
            "| query | `assignee` | string |  | `me` 또는 구성원 uid. 생략 시 전체 |\n\n"
            "> `week_start` 는 반드시 월요일 날짜여야 한다. 월요일이 아니면 400.\n\n"
            "## 📤 응답 (200)\n"
            "항목 배열 (래퍼 없음). 확정 분담안이 없으면 빈 배열이다. 각 원소는 아래 구조 + `is_requested`.\n\n"
            + _SELECTABLE_ITEM_TABLE
            + "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 400 | `invalid` | `week_start` 가 월요일이 아님 |\n"
            "| 404 | `not_found` | 속한 집이 없음 / 구성원 uid 미존재 |\n"
        ),
        parameters=[
            OpenApiParameter(name="week_start", type=str, required=False, description="대상 주차 월요일."),
            OpenApiParameter(name="assignee", type=str, required=False, description="`me` 또는 구성원 uid."),
        ],
        responses={
            200: BoardSelectableItemSerializer(many=True),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="쿼리 형식 오류."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="속한 집이 없음."),
        },
        examples=[
            OpenApiExample(
                "조율 대상 목록",
                value=[
                    {
                        "id": 31,
                        "chore_name": "분리수거",
                        "weekday": 5,
                        "weekday_label": "토",
                        "difficulty": 3,
                        "point": 120,
                        "date": "2026-07-25",
                        "assignee": _EXAMPLE_MEMBER_A,
                        "is_requested": False,
                    },
                    {
                        "id": 33,
                        "chore_name": "설거지",
                        "weekday": 5,
                        "weekday_label": "토",
                        "difficulty": 2,
                        "point": 80,
                        "date": "2026-07-25",
                        "assignee": _EXAMPLE_MEMBER_A,
                        "is_requested": True,
                    },
                ],
                response_only=True,
                status_codes=["200"],
            ),
            _AUTH_FAILED_EXAMPLE,
        ],
    )
    def get(self, request: Request) -> Response:
        query = BoardItemQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)

        home = get_user_home(request.user)
        if home is None:
            raise NotFound("속한 집이 없습니다.")

        assignee_param = query.validated_data.get("assignee")
        assignee = None
        if assignee_param == "me":
            assignee = request.user
        elif assignee_param:
            membership = HomeMember.objects.select_related("user").filter(
                home=home, user__uid=assignee_param
            ).first()
            if membership is None:
                raise NotFound("구성원을 찾을 수 없습니다.")
            assignee = membership.user

        week_start = query.validated_data.get("week_start") or week_start_of(timezone.localdate())
        return Response(
            selectors.get_coordinatable_items(home=home, week_start=week_start, assignee=assignee)
        )


class HelpRequestListView(APIView):
    """도움 요청 카드 생성."""

    @extend_schema(
        tags=["Boards"],
        summary="도움 요청 카드 생성",
        description=(
            "## 🔥 설명\n"
            "본인이 담당한 **확정 분담안의 미완료 항목**에 대해 도움 요청 카드를 올린다. "
            "아무도 수락하지 않으면 대상 집안일 **다음 날 23:59** 에 자동 만료된다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| body | `item_id` | integer | ✓ | 대상 분담안 항목 PK (본인 담당) |\n"
            "| body | `message` | string | - | 메시지 (최대 30자) |\n\n"
            "## 📤 응답 (201)\n"
            + _COORDINATION_RESULT_TABLE
            + "생성 직후 `status` 는 항상 `pending` 이다. 카드 전문은 피드 조회로 받는다.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 400 | `assignment_not_confirmed` | 확정 분담안이 아님 |\n"
            "| 400 | `already_completed` | 이미 완료된 집안일 |\n"
            "| 403 | `permission_denied` | 본인 담당 항목이 아님 |\n"
            "| 404 | `not_found` | 항목 미존재 |\n"
            "| 409 | `already_requested` | 이미 도움 요청한 집안일 |\n"
        ),
        request=HelpRequestCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=CoordinationRequestResultSerializer, description="도움 요청 생성 완료."
            ),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="상태 오류."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="본인 담당이 아님."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="항목 미존재."),
            409: OpenApiResponse(response=ErrorResponseSerializer, description="중복 요청."),
        },
        examples=[
            OpenApiExample(
                "도움 요청",
                value={"item_id": 31, "message": "토요일 출장이라 대신해줄 사람?"},
                request_only=True,
            ),
            OpenApiExample(
                "생성 완료",
                value={"id": 8, "status": "pending"},
                response_only=True,
                status_codes=["201"],
            ),
            _AUTH_FAILED_EXAMPLE,
            error_example(
                code="already_requested", message="이미 도움 요청한 집안일이에요.", name="중복 요청"
            ),
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = HelpRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            help_request = services.create_help_request(
                user=request.user,
                item_id=serializer.validated_data["item_id"],
                message=serializer.validated_data.get("message", ""),
            )
        except services.BoardError as e:
            raise _handle(e) from e

        return Response({"id": help_request.id, "status": help_request.status}, status=status.HTTP_201_CREATED)


class HelpRequestDetailView(APIView):
    """도움 요청 취소 (본인 카드)."""

    @extend_schema(
        tags=["Boards"],
        summary="도움 요청 취소",
        description=(
            "## 🔥 설명\n"
            "본인이 올린 **대기 중** 도움 요청 카드를 취소(삭제)한다. 이미 수락·만료된 카드는 409.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `help_request_id` | integer | ✓ | 취소할 도움 요청 카드 PK (본인·pending) |\n\n"
            "요청 본문 없음.\n\n"
            "## 📤 응답 (204)\n"
            "본문 없음. 카드는 삭제되므로 피드에서 사라진다.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 403 | `permission_denied` | 본인이 올린 카드가 아님 |\n"
            "| 404 | `not_found` | 카드 미존재 |\n"
            "| 409 | `already_resolved` | 이미 처리된 카드 |\n"
        ),
        responses={
            204: OpenApiResponse(description="취소 완료 (본문 없음)."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="본인 카드가 아님."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="카드 미존재."),
            409: OpenApiResponse(response=ErrorResponseSerializer, description="이미 처리됨."),
        },
        examples=[_AUTH_FAILED_EXAMPLE],
    )
    def delete(self, request: Request, help_request_id: int) -> Response:
        try:
            services.cancel_help_request(user=request.user, help_request_id=help_request_id)
        except services.BoardError as e:
            raise _handle(e) from e
        return Response(status=status.HTTP_204_NO_CONTENT)


class HelpRequestAcceptView(APIView):
    """도움 요청 수락 — 담당자가 수락자로 바뀝니다."""

    @extend_schema(
        tags=["Boards"],
        summary="도움 요청 수락 (내가 도와줄게)",
        description=(
            "## 🔥 설명\n"
            "도움 요청을 수락한다. 대상 분담안 항목의 **담당자가 수락자로 변경**되고, 요청자에게 "
            "`도움 요청이 수락됐어요` 알림이 전달된다. 본인이 올린 요청은 수락할 수 없다.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `help_request_id` | integer | ✓ | 수락할 도움 요청 카드 PK (pending) |\n\n"
            "요청 본문 없음.\n\n"
            "## 📤 응답 (200)\n"
            + _COORDINATION_RESULT_TABLE
            + "수락 후 `status` 는 `accepted` 다.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 403 | `permission_denied` | 본인이 올린 요청 |\n"
            "| 404 | `not_found` | 카드 미존재 |\n"
            "| 409 | `already_resolved` | 이미 처리된 카드 |\n"
        ),
        request=None,
        responses={
            200: OpenApiResponse(
                response=CoordinationRequestResultSerializer, description="수락 완료."
            ),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="본인 요청."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="카드 미존재."),
            409: OpenApiResponse(response=ErrorResponseSerializer, description="이미 처리됨."),
        },
        examples=[
            OpenApiExample(
                "수락 완료",
                value={"id": 8, "status": "accepted"},
                response_only=True,
                status_codes=["200"],
            ),
            _AUTH_FAILED_EXAMPLE,
            error_example(
                code="already_resolved", message="이미 처리된 도움 요청이에요.", name="이미 처리됨"
            ),
        ],
    )
    def post(self, request: Request, help_request_id: int) -> Response:
        try:
            help_request = services.accept_help_request(
                user=request.user, help_request_id=help_request_id
            )
        except services.BoardError as e:
            raise _handle(e) from e

        return Response({"id": help_request.id, "status": help_request.status})


class SwapRequestListView(APIView):
    """교환 요청 카드 생성."""

    @extend_schema(
        tags=["Boards"],
        summary="교환 요청 카드 생성",
        description=(
            "## 🔥 설명\n"
            "내 항목과 상대 항목의 담당자를 맞바꾸자고 제안한다. 두 항목 모두 **확정 분담안의 "
            "미완료 항목**이어야 하며, 상대 항목의 담당자에게만 응답 권한이 있다.\n\n"
            "응답이 없으면 두 항목 중 **더 이른 쪽** 집안일 다음 날 23:59 에 만료된다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| body | `requester_item_id` | integer | ✓ | 내가 넘길 항목 PK (본인 담당) |\n"
            "| body | `target_item_id` | integer | ✓ | 내가 대신할 상대 항목 PK |\n"
            "| body | `message` | string | - | 메시지 (최대 30자) |\n\n"
            "## 📤 응답 (201)\n"
            + _COORDINATION_RESULT_TABLE
            + "생성 직후 `status` 는 항상 `pending` 이다. 카드 전문은 피드 조회로 받는다.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 400 | `same_item` / `assignment_not_confirmed` / `already_completed` / `no_assignee` | 상태 오류 |\n"
            "| 403 | `permission_denied` | 내 항목이 아니거나 상대 항목이 본인 것 |\n"
            "| 409 | `already_requested` | 이미 교환 요청한 집안일 |\n"
        ),
        request=SwapRequestCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=CoordinationRequestResultSerializer, description="교환 요청 생성 완료."
            ),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="상태 오류."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="권한 없음."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="항목 미존재."),
            409: OpenApiResponse(response=ErrorResponseSerializer, description="중복 요청."),
        },
        examples=[
            OpenApiExample(
                "교환 요청",
                value={
                    "requester_item_id": 31,
                    "target_item_id": 44,
                    "message": "토요일에 일정이 생겨서 바꿔줄 수 있어?",
                },
                request_only=True,
            ),
            OpenApiExample(
                "생성 완료",
                value={"id": 12, "status": "pending"},
                response_only=True,
                status_codes=["201"],
            ),
            _AUTH_FAILED_EXAMPLE,
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = SwapRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            swap = services.create_swap_request(
                user=request.user,
                requester_item_id=serializer.validated_data["requester_item_id"],
                target_item_id=serializer.validated_data["target_item_id"],
                message=serializer.validated_data.get("message", ""),
            )
        except services.BoardError as e:
            raise _handle(e) from e

        return Response({"id": swap.id, "status": swap.status}, status=status.HTTP_201_CREATED)


class SwapRequestDetailView(APIView):
    """교환 요청 취소 (본인 카드)."""

    @extend_schema(
        tags=["Boards"],
        summary="교환 요청 취소",
        description=(
            "## 🔥 설명\n"
            "본인이 올린 **대기 중** 교환 요청 카드를 취소(삭제)한다. 이미 응답·만료된 카드는 409.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `swap_id` | integer | ✓ | 취소할 교환 요청 카드 PK (본인·pending) |\n\n"
            "요청 본문 없음.\n\n"
            "## 📤 응답 (204)\n"
            "본문 없음. 카드는 삭제되므로 피드에서 사라진다.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 403 | `permission_denied` | 본인이 올린 카드가 아님 |\n"
            "| 404 | `not_found` | 카드 미존재 |\n"
            "| 409 | `already_resolved` | 이미 처리된 카드 |\n"
        ),
        responses={
            204: OpenApiResponse(description="취소 완료 (본문 없음)."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="본인 카드가 아님."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="카드 미존재."),
            409: OpenApiResponse(response=ErrorResponseSerializer, description="이미 처리됨."),
        },
        examples=[_AUTH_FAILED_EXAMPLE],
    )
    def delete(self, request: Request, swap_id: int) -> Response:
        try:
            services.cancel_swap_request(user=request.user, swap_id=swap_id)
        except services.BoardError as e:
            raise _handle(e) from e
        return Response(status=status.HTTP_204_NO_CONTENT)


class SwapRequestAcceptView(APIView):
    """교환 수락 — 두 항목의 담당자를 맞바꿉니다."""

    @extend_schema(
        tags=["Boards"],
        summary="교환 요청 수락 (교환할게)",
        description=(
            "## 🔥 설명\n"
            "교환을 수락한다. 두 분담안 항목의 **담당자가 서로 맞바뀌고**, 요청자에게 "
            "`교환 요청이 수락됐어요` 알림이 전달된다. **교환 요청을 받은 담당자만** 응답할 수 있다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `swap_id` | integer | ✓ | 수락할 교환 요청 카드 PK (pending) |\n\n"
            "요청 본문 없음.\n\n"
            "## 📤 응답 (200)\n"
            + _COORDINATION_RESULT_TABLE
            + "수락 후 `status` 는 `accepted` 다.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 403 | `permission_denied` | 요청을 받은 담당자가 아님 |\n"
            "| 404 | `not_found` | 카드 미존재 |\n"
            "| 409 | `already_resolved` | 이미 처리된 카드 |\n"
        ),
        request=None,
        responses={
            200: OpenApiResponse(
                response=CoordinationRequestResultSerializer, description="수락 완료."
            ),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="응답 권한 없음."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="카드 미존재."),
            409: OpenApiResponse(response=ErrorResponseSerializer, description="이미 처리됨."),
        },
        examples=[
            OpenApiExample(
                "수락 완료",
                value={"id": 12, "status": "accepted"},
                response_only=True,
                status_codes=["200"],
            ),
            _AUTH_FAILED_EXAMPLE,
        ],
    )
    def post(self, request: Request, swap_id: int) -> Response:
        try:
            swap = services.accept_swap_request(user=request.user, swap_id=swap_id)
        except services.BoardError as e:
            raise _handle(e) from e
        return Response({"id": swap.id, "status": swap.status})


class SwapRequestRejectView(APIView):
    """교환 거절."""

    @extend_schema(
        tags=["Boards"],
        summary="교환 요청 거절 (아쉽지만 다음에)",
        description=(
            "## 🔥 설명\n"
            "교환을 거절한다. 카드는 \"아쉽지만 다음에 교환해요\" 상태로 남고 담당자는 바뀌지 않는다. "
            "**교환 요청을 받은 담당자만** 응답할 수 있다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `swap_id` | integer | ✓ | 거절할 교환 요청 카드 PK (pending) |\n\n"
            "요청 본문 없음.\n\n"
            "## 📤 응답 (200)\n"
            + _COORDINATION_RESULT_TABLE
            + "거절 후 `status` 는 `rejected` 다. 카드는 삭제되지 않고 피드에 남는다.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 403 | `permission_denied` | 요청을 받은 담당자가 아님 |\n"
            "| 404 | `not_found` | 카드 미존재 |\n"
            "| 409 | `already_resolved` | 이미 처리된 카드 |\n"
        ),
        request=None,
        responses={
            200: OpenApiResponse(
                response=CoordinationRequestResultSerializer, description="거절 완료."
            ),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="응답 권한 없음."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="카드 미존재."),
            409: OpenApiResponse(response=ErrorResponseSerializer, description="이미 처리됨."),
        },
        examples=[
            OpenApiExample(
                "거절 완료",
                value={"id": 12, "status": "rejected"},
                response_only=True,
                status_codes=["200"],
            ),
            _AUTH_FAILED_EXAMPLE,
        ],
    )
    def post(self, request: Request, swap_id: int) -> Response:
        try:
            swap = services.reject_swap_request(user=request.user, swap_id=swap_id)
        except services.BoardError as e:
            raise _handle(e) from e
        return Response({"id": swap.id, "status": swap.status})

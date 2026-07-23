"""알림 컨트롤러 — 알림함 조회/확인, 푸시 설정, 분담안 생성 재촉."""

from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.homes.services import week_start_of
from apps.notifications import selectors, services
from apps.notifications.serializers import (
    AssignmentNudgeSerializer,
    NotificationListOutputSerializer,
    NotificationOutputSerializer,
    NotificationQuerySerializer,
    NotificationSettingSerializer,
)
from common.error_responses import ErrorResponseSerializer, error_example

_AUTH_FAILED_EXAMPLE = error_example(
    code="authentication_failed",
    message="Authentication credentials were not provided.",
    name="인증 실패",
)


class NotificationListView(APIView):
    """알림함 목록 조회."""

    @extend_schema(
        tags=["Notifications"],
        summary="알림함 조회",
        description=(
            "## 🔥 설명\n"
            "인앱 알림함(N1_NotificationInbox) 응답. 정렬은 **미확인 우선 > 최신순** 이며, "
            "발생 후 **7일이 지난 알림은 삭제**된다(`purge_notifications` 커맨드).\n\n"
            "`deep_link` 는 탭 시 이동할 목적지 문자열이다. 대상 주차가 지났거나 이미 처리된 "
            "카드처럼 랜딩할 수 없으면 앱이 만료 토스트를 대신 노출한다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| query | `category` | string |  | 카테고리 5종 중 하나. 생략 시 전체 |\n\n"
            "## 📤 응답 (200)\n"
            "| 위치 | 필드 | 타입 | 설명 |\n"
            "| --- | --- | --- | --- |\n"
            "| body | `unread_count` | integer | 미확인 개수 (헤더 벨 배지) |\n"
            "| body | `retention_days` | integer | 보관 기간(일) — 하단 안내 문구용 |\n"
            "| body | `notifications[].is_read` | boolean | false 면 강조 표시 |\n"
        ),
        parameters=[
            OpenApiParameter(
                name="category",
                type=str,
                required=False,
                description="카테고리 필터 (home_member / assignment / board / reward / report).",
            ),
        ],
        responses={
            200: NotificationListOutputSerializer,
            400: OpenApiResponse(response=ErrorResponseSerializer, description="카테고리 값 오류."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
        },
        examples=[_AUTH_FAILED_EXAMPLE],
    )
    def get(self, request: Request) -> Response:
        query = NotificationQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)

        notifications = selectors.get_notifications(
            user=request.user, category=query.validated_data.get("category")
        )
        return Response({
            "unread_count": selectors.get_unread_count(user=request.user),
            "retention_days": services.NOTIFICATION_RETENTION_DAYS,
            "notifications": NotificationOutputSerializer(notifications, many=True).data,
        })


class NotificationReadView(APIView):
    """알림 확인 처리."""

    @extend_schema(
        tags=["Notifications"],
        summary="알림 확인 처리",
        description=(
            "## 🔥 설명\n"
            "알림을 확인(읽음) 처리한다. 본인 알림만 가능하며, 이미 확인한 알림은 그대로 200 을 반환한다(멱등).\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 404 | `not_found` | 본인 알림이 아니거나 없음 |\n"
        ),
        request=None,
        responses={
            200: NotificationOutputSerializer,
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="알림 미존재."),
        },
        examples=[
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="알림을 찾을 수 없습니다.", name="알림 미존재"),
        ],
    )
    def post(self, request: Request, notification_id: int) -> Response:
        try:
            notification = services.mark_read(user=request.user, notification_id=notification_id)
        except services.NotificationNotFoundError as e:
            raise NotFound(str(e)) from e

        return Response(NotificationOutputSerializer(notification).data)


class NotificationSettingView(APIView):
    """푸시 알림 설정 조회 / 수정."""

    @extend_schema(
        tags=["Notifications"],
        summary="푸시 알림 설정 조회",
        description=(
            "## 🔥 설명\n"
            "마이 화면(T5_My)의 푸시 알림 토글 상태를 반환한다. 설정이 없으면 전체 on 기본값으로 생성된다.\n\n"
            "`push_enabled` 가 마스터 토글이며, 꺼지면 카테고리 값과 무관하게 푸시를 발송하지 않는다. "
            "인앱 알림함 기록은 설정과 무관하게 항상 남는다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n"
        ),
        responses={
            200: NotificationSettingSerializer,
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
        },
        examples=[_AUTH_FAILED_EXAMPLE],
    )
    def get(self, request: Request) -> Response:
        setting = services.get_or_create_setting(user=request.user)
        return Response(NotificationSettingSerializer(setting).data)

    @extend_schema(
        tags=["Notifications"],
        summary="푸시 알림 설정 수정 (PATCH)",
        description=(
            "## 🔥 설명\n"
            "푸시 알림 토글을 부분 수정한다. 전달된 키만 반영된다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| body | `push_enabled` | boolean | - | 푸시 전체 on/off |\n"
            "| body | 카테고리 5종 (`home_member` 등) | boolean | - | 카테고리별 on/off |\n"
        ),
        request=NotificationSettingSerializer,
        responses={
            200: NotificationSettingSerializer,
            400: OpenApiResponse(response=ErrorResponseSerializer, description="입력 검증 실패."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
        },
        examples=[
            OpenApiExample("보드 알림만 끄기", value={"board": False}, request_only=True),
            OpenApiExample("푸시 전체 끄기", value={"push_enabled": False}, request_only=True),
            _AUTH_FAILED_EXAMPLE,
        ],
    )
    def patch(self, request: Request) -> Response:
        serializer = NotificationSettingSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        setting = services.update_setting(user=request.user, fields=serializer.validated_data)
        return Response(NotificationSettingSerializer(setting).data)


class AssignmentNudgeView(APIView):
    """분담안 생성 재촉 (구성원 → 관리자)."""

    @extend_schema(
        tags=["Notifications"],
        summary="분담안 생성 재촉 (구성원 → 관리자)",
        description=(
            "## 🔥 설명\n"
            "분담안이 아직 없을 때 구성원이 관리자에게 생성을 요청한다. 관리자에게 "
            "`이번 주 분담안을 기다리고 있어요` 알림이 적재된다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| body | `week_start` | date | - | 대상 주차의 월요일. 생략 시 이번 주차 |\n\n"
            "## 📤 응답 (201)\n"
            "| 위치 | 필드 | 타입 | 설명 |\n"
            "| --- | --- | --- | --- |\n"
            "| body | `notified_count` | integer | 알림을 받은 관리자 수 |\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 404 | `not_found` | 속한 집이 없음 |\n"
        ),
        request=AssignmentNudgeSerializer,
        responses={
            201: OpenApiResponse(description="재촉 알림 적재 완료."),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="week_start 형식 오류."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="속한 집이 없음."),
        },
        examples=[
            OpenApiExample("이번 주 재촉", value={}, request_only=True),
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="속한 집이 없습니다.", name="집 미존재"),
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = AssignmentNudgeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        week_start = serializer.validated_data.get("week_start") or week_start_of(timezone.localdate())
        try:
            created = services.nudge_assignment(user=request.user, week_start=week_start)
        except services.NotificationError as e:
            raise NotFound(str(e)) from e

        return Response({"notified_count": len(created)}, status=status.HTTP_201_CREATED)

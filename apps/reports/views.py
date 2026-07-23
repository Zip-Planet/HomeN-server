"""주간 리포트 컨트롤러."""

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.homes.selectors import get_user_home
from apps.homes.services import week_start_of
from apps.reports.models import WeeklyReport
from apps.reports.serializers import WeeklyReportOutputSerializer, WeeklyReportQuerySerializer
from common.error_responses import ErrorResponseSerializer, error_example


class WeeklyReportView(APIView):
    """주간 리포트 조회 (모든 구성원)."""

    @extend_schema(
        tags=["Reports"],
        summary="주간 리포트 조회",
        description=(
            "## 🔥 설명\n"
            "주간 리포트(R1_WeeklyReport)를 조회한다. 리포트는 **매주 일요일 21:00** 에 "
            "`generate_weekly_reports` 커맨드가 자동 생성한 스냅샷이며, 이후 집안일이 수정·삭제돼도 "
            "지난 리포트 값은 변하지 않는다.\n\n"
            "아직 생성되지 않았거나 그 주차에 분담안이 없으면 404 — 화면은 "
            "\"집안일을 완료하면 리포트가 도착해요\" 빈 상태를 노출한다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수. 모든 구성원 조회 가능.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| query | `week_start` | date |  | 조회할 주차의 월요일. 생략 시 이번 주차 |\n\n"
            "## 📤 응답 (200)\n"
            "| 위치 | 필드 | 타입 | 설명 |\n"
            "| --- | --- | --- | --- |\n"
            "| body | `progress_rate` | integer | 주간 진행률 % |\n"
            "| body | `completed_count` / `total_count` | integer | 완료 / 전체 항목 수 |\n"
            "| body | `mvp` | object | 우리집 MVP. 완료 이력이 없으면 null |\n"
            "| body | `member_stats[]` | array | 구성원별 `{assigned_count, completed_count, point}` |\n"
            "| body | `most_done` / `most_missed` | object | 하이라이트 `{name, count}` |\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 404 | `not_found` | 속한 집이 없거나 해당 주차 리포트가 없음 |\n"
        ),
        parameters=[
            OpenApiParameter(
                name="week_start",
                type=str,
                required=False,
                description="조회할 주차의 월요일 날짜 (YYYY-MM-DD). 생략 시 이번 주차.",
            ),
        ],
        responses={
            200: WeeklyReportOutputSerializer,
            400: OpenApiResponse(response=ErrorResponseSerializer, description="week_start 형식 오류."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="집 또는 리포트 미존재."),
        },
        examples=[
            error_example(
                code="authentication_failed",
                message="Authentication credentials were not provided.",
                name="인증 실패",
            ),
            error_example(code="not_found", message="해당 주차의 리포트가 없습니다.", name="리포트 미존재"),
        ],
    )
    def get(self, request: Request) -> Response:
        query = WeeklyReportQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)

        home = get_user_home(request.user)
        if home is None:
            raise NotFound("속한 집이 없습니다.")

        week_start = query.validated_data.get("week_start") or week_start_of(timezone.localdate())
        report = (
            WeeklyReport.objects.select_related("mvp_user")
            .filter(home=home, week_start=week_start)
            .first()
        )
        if report is None:
            raise NotFound("해당 주차의 리포트가 없습니다.")

        return Response(WeeklyReportOutputSerializer(report).data)

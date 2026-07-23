"""홈(집) / 집안일 / 스타터팩 컨트롤러.

본 모듈은 다음 API 묶음을 제공한다.

- **Homes** : 집 생성/조회/삭제, 멤버십 조회, 초대코드 미리보기, 집 참여/탈퇴,
  관리자 양도, 집안일 목록 추가·메모 수정.
- **StarterPacks** : 사전 정의된 집안일 프리셋 목록과 해당 프리셋의 집안일 미리보기.

모든 핸들러는 다음 약속을 따른다.

- 요청 유효성은 명시적인 `*Serializer` 로 검증한다 (`raise_exception=True`).
- 도메인 예외(`AlreadyHasHomeError`, `NotHomeAdminError`, `HomeHasMembersError`,
  `HomeNotFoundError`, `TransferAdminTargetError`, `HomeChoreNotFoundError` 등)
  는 서비스 레이어에서 발생시키며, 컨트롤러가 DRF 표준 예외 — `ValidationError`,
  `PermissionDenied`, `NotFound` — 로 매핑한다.
- swagger 노출은 `@extend_schema` 로 명시한다 (summary / description / responses).
"""

from datetime import date

from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.homes import selectors, services
from apps.homes.models import WeeklyAssignment
from apps.homes.serializers import (
    AssignmentCreateSerializer,
    AssignmentHistoryOutputSerializer,
    AssignmentHistoryQuerySerializer,
    AssignmentItemOutputSerializer,
    AssignmentWeekQuerySerializer,
    ChoreCompletionCreateSerializer,
    ChoreCompletionOutputSerializer,
    ChoreOutputSerializer,
    HomeChoreDetailOutputSerializer,
    HomeChoreListCreateSerializer,
    HomeChoreNoteCreateSerializer,
    HomeChoreNoteOutputSerializer,
    HomeChoreNoteUpdateSerializer,
    HomeChoreOutputSerializer,
    HomeChoreUpdateSerializer,
    HomeCreateSerializer,
    HomeDashboardOutputSerializer,
    HomeInviteDetailSerializer,
    HomeJoinSerializer,
    HomeMembershipSerializer,
    HomeOutputSerializer,
    ImageIdSerializer,
    StarterPackSerializer,
    TransferAdminSerializer,
    WeeklyAssignmentOutputSerializer,
)
from common.error_responses import ErrorResponseSerializer, error_example
from common.exceptions import Conflict

# 공통 응답 예시 (status_codes=["200"|"201"|"204"|...])
_AUTH_FAILED_EXAMPLE = error_example(
    code="authentication_failed",
    message="Authentication credentials were not provided.",
    name="인증 실패",
)


# ── 프리셋 ──────────────────────────────────────────────────────────────────


class HomeImageListView(APIView):
    """선택 가능한 집 이미지 enum 목록.

    `HomeImageType` 의 정수 choice 를 그대로 노출한다. 집 생성 시 `image_id` 로
    전송한다.
    """

    @extend_schema(
        tags=["Homes"],
        summary="프리셋 집 이미지 목록 조회",
        description=(
            "## 🔥 설명\n"
            "선택 가능한 집 이미지 enum 정수 목록을 반환한다. FE 는 응답의 `id` 를 그대로 "
            "`HomeCreate.image_id` 로 전송한다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "요청 파라미터 없음.\n\n"
            "## 📤 응답 (200)\n"
            "배열 응답.\n\n"
            "| 위치 | 필드 | 타입 | 설명 |\n"
            "| --- | --- | --- | --- |\n"
            "| body[*] | `id` | integer | 집 이미지 enum ID (1~8) |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X GET '{host}/api/v1/homes/images/' \\\n"
            "     -H 'Authorization: Bearer <access>'\n"
            "```\n\n"
            "**응답 (200):**\n"
            "```json\n"
            "[{\"id\": 1}, {\"id\": 2}, {\"id\": 3}, {\"id\": 4}, {\"id\": 5}, {\"id\": 6}, {\"id\": 7}, {\"id\": 8}]\n"
            "```\n"
        ),
        responses={
            200: OpenApiResponse(response=ImageIdSerializer(many=True), description="enum ID 배열."),
        },
        examples=[
            OpenApiExample(
                "전체 enum 목록",
                value=[{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}, {"id": 5}, {"id": 6}, {"id": 7}, {"id": 8}],
                response_only=True,
                status_codes=["200"],
            ),
        ],
    )
    def get(self, request: Request) -> Response:
        return Response(selectors.get_home_image_choices())


# ── 집 생성 ──────────────────────────────────────────────────────────────────


class HomeCreateView(APIView):
    """집 생성.

    호출자는 **자동으로 관리자(`HomeMember.Role.ADMIN`)** 로 등록된다. 빈
    `chores`/`rewards` 리스트는 무시되어 부속 객체를 생성하지 않는다.
    """

    @extend_schema(
        tags=["Homes"],
        summary="집 생성 (호출자를 관리자로 등록)",
        description=(
            "## 🔥 설명\n"
            "집을 생성하고 호출자를 관리자(`role=1`)로 자동 등록한다. 집안일은 **스타터팩 ID 또는 커스텀 배열 중 하나만** "
            "받으며, 둘 다 비어 있어도 된다(집만 생성).\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| body | `name` | string | ✓ | 집 이름 (한글·영문·숫자·공백 1~10자, 공백 단독 불가) |\n"
            "| body | `image_id` | integer | ✓ | 집 이미지 enum (1~8) |\n"
            "| body | `starter_pack_id` | integer\\|null | - | 적용할 스타터팩 PK. `chores` 와 동시 사용 불가 |\n"
            "| body | `chores` | array | - | 사용자 정의 집안일 목록. `starter_pack_id` 와 동시 사용 불가 |\n"
            "| body | `chores[].category` | integer | ✓ | 카테고리 (1=쓰레기, 2=욕실, 3=청소, 4=주방, 5=세탁) |\n"
            "| body | `chores[].name` | string | ✓ | 집안일 제목 (1~20자) |\n"
            "| body | `chores[].description` | string | - | 설명 (최대 20자, 기본 \"\") |\n"
            "| body | `chores[].repeat_days` | integer[] | - | 반복 요일 (0=월 ~ 6=일, 기본 []) |\n"
            "| body | `chores[].difficulty` | integer | ✓ | 난이도 (1=하 ~ 5=상) |\n"
            "| body | `rewards` | array | - | 함께 등록할 리워드 목록 |\n"
            "| body | `rewards[].name` | string | ✓ | 리워드 이름 (최대 50자) |\n"
            "| body | `rewards[].goal_point` | integer | ✓ | 목표 포인트 (1 이상) |\n\n"
            "## 📤 응답 (201)\n"
            "| 위치 | 필드 | 타입 | 설명 |\n"
            "| --- | --- | --- | --- |\n"
            "| body | `id` | integer | 집 PK |\n"
            "| body | `name` | string | 집 이름 |\n"
            "| body | `image` | integer | 집 이미지 enum |\n"
            "| body | `invite_code` | string | 6자리 대문자+숫자 초대코드 |\n"
            "| body | `status` | string | `active` 또는 `draft` |\n"
            "| body | `created_at` | string (datetime) | 생성 일시 (ISO 8601) |\n"
            "| body | `members` | array | 구성원 목록 (관리자 본인 포함) |\n"
            "| body | `members[].name` | string | 구성원 닉네임 |\n"
            "| body | `members[].profile_image` | integer\\|null | 프로필 이미지 enum |\n"
            "| body | `members[].role` | integer | 1=관리자, 2=구성원 |\n"
            "| body | `members[].role_label` | string | '관리자' 또는 '구성원' |\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 400 | `already_has_home` | 이미 다른 집에 속해 있음 |\n"
            "| 400 | `ambiguous_chore_input` | `starter_pack_id` 와 `chores` 동시 지정 |\n"
            "| 400 | `invalid` | 이름 형식 위반, image_id 무효 등 |\n"
            "| 401 | `authentication_failed` | access 토큰 누락/만료 |\n"
            "| 404 | `not_found` | `starter_pack_id` 에 해당하는 스타터팩 없음 |\n\n"
            "## 💻 예제\n"
            "**요청 (스타터팩 적용):**\n"
            "```bash\n"
            "curl -X POST '{host}/api/v1/homes/' \\\n"
            "     -H 'Authorization: Bearer <access>' \\\n"
            "     -H 'Content-Type: application/json' \\\n"
            "     -d '{\"name\":\"우리집\",\"image_id\":1,\"starter_pack_id\":1,\"chores\":[],\"rewards\":[]}'\n"
            "```\n\n"
            "**응답 (201):**\n"
            "```json\n"
            "{\n"
            "  \"id\": 12,\n"
            "  \"name\": \"우리집\",\n"
            "  \"image\": 1,\n"
            "  \"invite_code\": \"AB12CD\",\n"
            "  \"status\": \"active\",\n"
            "  \"created_at\": \"2026-05-13T12:00:00Z\",\n"
            "  \"members\": [\n"
            "    {\"name\": \"홍길동\", \"profile_image\": 3, \"role\": 1, \"role_label\": \"관리자\"}\n"
            "  ]\n"
            "}\n"
            "```\n"
        ),
        request=HomeCreateSerializer,
        responses={
            201: OpenApiResponse(response=HomeOutputSerializer, description="생성된 집 (관리자 본인 포함된 members)."),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="이미 집이 있거나 입력 유효성 실패."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="`starter_pack_id` 에 해당하는 스타터팩이 없음."),
        },
        examples=[
            OpenApiExample(
                "커스텀 chore + reward",
                value={
                    "name": "우리집",
                    "image_id": 1,
                    "chores": [
                        {
                            "category": 3,
                            "name": "거실 청소",
                            "description": "주 1회",
                            "repeat_days": [0, 3],
                            "difficulty": 2,
                        }
                    ],
                    "rewards": [{"name": "치킨", "goal_point": 50}],
                },
                request_only=True,
            ),
            OpenApiExample(
                "스타터팩 적용",
                value={"name": "우리집", "image_id": 2, "starter_pack_id": 1, "chores": [], "rewards": []},
                request_only=True,
            ),
            OpenApiExample(
                "집만 생성 (chore/reward 없음)",
                value={"name": "우리집", "image_id": 3, "chores": [], "rewards": []},
                request_only=True,
            ),
            OpenApiExample(
                "생성 성공",
                value={
                    "id": 1,
                    "name": "우리집",
                    "image_id": 1,
                    "invite_code": "AB12CD",
                    "members": [
                        {
                            "uid": "8f3e2b1a-1234-4abc-9def-1234567890ab",
                            "name": "홍길동",
                            "profile_image": 3,
                            "role": "admin",
                        }
                    ],
                },
                response_only=True,
                status_codes=["201"],
            ),
            error_example(code="already_has_home", message="이미 속한 집이 있습니다.", name="이미 집 있음"),
            error_example(
                code="ambiguous_chore_input",
                message="starter_pack_id 와 chores 는 동시에 지정할 수 없습니다.",
                name="입력 분기 오류",
            ),
            error_example(code="invalid", message="이름은 1~10자여야 합니다.", name="이름 형식 위반"),
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="스타터팩을 찾을 수 없습니다.", name="스타터팩 미존재"),
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = HomeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        try:
            home = services.create_home(
                user=request.user,
                name=data["name"],
                image_id=data["image_id"],
                chores=data["chores"],
                rewards=data["rewards"],
                starter_pack_id=data.get("starter_pack_id"),
                starter_pack_chore_ids=data.get("starter_pack_chore_ids"),
            )
        except services.AlreadyHasHomeError as e:
            raise ValidationError({"already_has_home": str(e)}) from e
        except services.AmbiguousChoreInputError as e:
            raise ValidationError({"ambiguous_chore_input": str(e)}) from e
        except services.StarterPackNotFoundError as e:
            raise NotFound(str(e)) from e

        return Response(HomeOutputSerializer(home).data, status=status.HTTP_201_CREATED)


# ── 집 조회 / 삭제 ───────────────────────────────────────────────────────────


class HomeDetailView(APIView):
    """본인이 속한 집의 단건 조회 / 삭제.

    GET 은 속한 집이 없으면 404 를, DELETE 는 관리자 + 구성원이 0명일 때만 허용한다.
    """

    @extend_schema(
        tags=["Homes"],
        summary="내 집 정보 조회",
        description=(
            "## 🔥 설명\n"
            "현재 유저가 속한 집의 상세 정보를 반환한다. 속한 집이 없으면 404 — `has_home` 만 확인하려면 "
            "`/homes/mine/membership/` 사용.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "요청 본문 없음.\n\n"
            "## 📤 응답 (200)\n"
            "| 위치 | 필드 | 타입 | 설명 |\n"
            "| --- | --- | --- | --- |\n"
            "| body | `id` | integer | 집 PK |\n"
            "| body | `name` | string | 집 이름 |\n"
            "| body | `image` | integer | 집 이미지 enum (1~8) |\n"
            "| body | `invite_code` | string | 6자리 대문자+숫자 초대코드 |\n"
            "| body | `status` | string | `active` 또는 `draft` |\n"
            "| body | `created_at` | string (datetime) | 생성 일시 (ISO 8601) |\n"
            "| body | `members` | array | 구성원 목록 (관리자 포함) |\n"
            "| body | `members[].name` | string | 닉네임 |\n"
            "| body | `members[].profile_image` | integer\\|null | 프로필 이미지 enum |\n"
            "| body | `members[].role` | integer | 1=관리자, 2=구성원 |\n"
            "| body | `members[].role_label` | string | '관리자' 또는 '구성원' |\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 401 | `authentication_failed` | access 토큰 누락/만료 |\n"
            "| 404 | `not_found` | 속한 집 없음 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X GET '{host}/api/v1/homes/mine/' \\\n"
            "     -H 'Authorization: Bearer <access>'\n"
            "```\n\n"
            "**응답 (200):**\n"
            "```json\n"
            "{\n"
            "  \"id\": 12,\n"
            "  \"name\": \"우리집\",\n"
            "  \"image\": 1,\n"
            "  \"invite_code\": \"AB12CD\",\n"
            "  \"status\": \"active\",\n"
            "  \"created_at\": \"2026-05-13T12:00:00Z\",\n"
            "  \"members\": [\n"
            "    {\"name\": \"홍길동\", \"profile_image\": 3, \"role\": 1, \"role_label\": \"관리자\"},\n"
            "    {\"name\": \"김철수\", \"profile_image\": 2, \"role\": 2, \"role_label\": \"구성원\"}\n"
            "  ]\n"
            "}\n"
            "```\n"
        ),
        responses={
            200: OpenApiResponse(response=HomeOutputSerializer, description="조회 성공."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="속한 집 없음."),
        },
        examples=[
            OpenApiExample(
                "조회 성공",
                value={
                    "id": 1,
                    "name": "우리집",
                    "image_id": 1,
                    "invite_code": "AB12CD",
                    "members": [
                        {
                            "uid": "8f3e2b1a-1234-4abc-9def-1234567890ab",
                            "name": "홍길동",
                            "profile_image": 3,
                            "role": "admin",
                        },
                        {
                            "uid": "9a4f3c2b-2345-4bcd-8def-2345678901bc",
                            "name": "김철수",
                            "profile_image": 1,
                            "role": "member",
                        },
                    ],
                },
                response_only=True,
                status_codes=["200"],
            ),
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="속한 집이 없습니다.", name="집 미존재"),
        ],
    )
    def get(self, request: Request) -> Response:
        home = selectors.get_user_home(request.user)
        if home is None:
            raise NotFound("속한 집이 없습니다.")
        return Response(HomeOutputSerializer(home).data)

    @extend_schema(
        tags=["Homes"],
        summary="내 집 삭제 (관리자 전용, 구성원 0명일 때만)",
        description=(
            "## 🔥 설명\n"
            "본인이 관리자인 집을 삭제한다. 구성원이 남아있으면 400(`home_has_members`) — 양도 후 탈퇴하거나 "
            "구성원이 모두 나간 뒤 호출 가능.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "요청 본문 없음.\n\n"
            "## 📤 응답 (204)\n"
            "응답 본문 없음.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 400 | `home_has_members` | 구성원이 남아있어 삭제 불가 |\n"
            "| 401 | `authentication_failed` | access 토큰 누락/만료 |\n"
            "| 403 | `permission_denied` | 관리자만 삭제 가능 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X DELETE '{host}/api/v1/homes/mine/' \\\n"
            "     -H 'Authorization: Bearer <access>'\n"
            "```\n"
        ),
        responses={
            204: OpenApiResponse(description="삭제 완료 — 응답 본문 없음."),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="구성원이 있어 삭제 불가 (`home_has_members`)."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="관리자만 집을 삭제할 수 있음."),
        },
        examples=[
            _AUTH_FAILED_EXAMPLE,
            error_example(
                code="home_has_members",
                message="구성원이 남아 있어 집을 삭제할 수 없습니다.",
                name="구성원 잔존",
            ),
            error_example(
                code="permission_denied",
                message="관리자만 집을 삭제할 수 있습니다.",
                name="관리자 아님",
            ),
        ],
    )
    def delete(self, request: Request) -> Response:
        try:
            services.delete_home(user=request.user)
        except services.NotHomeAdminError as e:
            raise PermissionDenied(str(e)) from e
        except services.HomeHasMembersError as e:
            raise ValidationError({"home_has_members": str(e)}) from e
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── 멤버십 / 초대 미리보기 / 참여 ────────────────────────────────────────────


class HomeMembershipView(APIView):
    """집 소속 여부 단건 조회.

    UI 상 라우팅 분기(집 만들기 vs 메인 진입)용 가벼운 엔드포인트.
    """

    @extend_schema(
        tags=["Homes"],
        summary="내 집 소속 여부 조회",
        description=(
            "## 🔥 설명\n"
            "현재 유저의 집 소속 여부를 반환한다. 속한 집이 없어도 404 가 아닌 200 + "
            "`{\"has_home\": false}` 를 반환한다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "요청 본문 없음.\n\n"
            "## 📤 응답 (200)\n"
            "| 위치 | 필드 | 타입 | 설명 |\n"
            "| --- | --- | --- | --- |\n"
            "| body | `has_home` | boolean | 집 관리자/구성원 소속 여부 |\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 401 | `authentication_failed` | access 토큰 누락/만료 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X GET '{host}/api/v1/homes/mine/membership/' \\\n"
            "     -H 'Authorization: Bearer <access>'\n"
            "```\n\n"
            "**응답 (200):**\n"
            "```json\n"
            "{\"has_home\": true}\n"
            "```\n"
        ),
        responses={
            200: OpenApiResponse(response=HomeMembershipSerializer, description="항상 200 반환."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
        },
        examples=[
            OpenApiExample("집 있음", value={"has_home": True}, response_only=True, status_codes=["200"]),
            OpenApiExample("집 없음", value={"has_home": False}, response_only=True, status_codes=["200"]),
            _AUTH_FAILED_EXAMPLE,
        ],
    )
    def get(self, request: Request) -> Response:
        home = selectors.get_user_home(request.user)
        return Response({"has_home": home is not None})


class HomeInviteView(APIView):
    """초대코드로 집 미리보기 (참여 전).

    FE 는 본 응답을 보여주고 사용자 확인 후 `POST /homes/join/` 으로 참여를 확정한다.
    """

    @extend_schema(
        tags=["Homes"],
        summary="초대코드로 집 정보 조회 (참여 전 미리보기)",
        description=(
            "## 🔥 설명\n"
            "초대코드로 집을 조회해 이름/이미지/구성원 등 미리보기 정보를 반환한다. 본 호출만으로 집에 "
            "참여되지는 않으며, 확정은 `POST /homes/join/` 으로 한다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `code` | string | ✓ | 6자리 대문자+숫자 초대코드 (예: 'AB12CD') |\n\n"
            "## 📤 응답 (200)\n"
            "| 위치 | 필드 | 타입 | 설명 |\n"
            "| --- | --- | --- | --- |\n"
            "| body | `invite_code` | string | 조회에 사용된 초대코드 |\n"
            "| body | `name` | string | 집 이름 |\n"
            "| body | `image` | integer | 집 이미지 enum (1~8) |\n"
            "| body | `member_count` | integer | 전체 구성원 수 (관리자 포함) |\n"
            "| body | `created_at` | string (datetime) | 집 생성 일시 |\n"
            "| body | `members` | array | 구성원 목록 |\n"
            "| body | `members[].name` | string | 닉네임 |\n"
            "| body | `members[].profile_image` | integer\\|null | 프로필 이미지 enum |\n"
            "| body | `members[].role` | integer | 1=관리자, 2=구성원 |\n"
            "| body | `members[].role_label` | string | 한글 라벨 |\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 401 | `authentication_failed` | access 토큰 누락/만료 |\n"
            "| 404 | `not_found` | 유효하지 않은 초대코드 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X GET '{host}/api/v1/homes/invite/AB12CD/' \\\n"
            "     -H 'Authorization: Bearer <access>'\n"
            "```\n\n"
            "**응답 (200):**\n"
            "```json\n"
            "{\n"
            "  \"invite_code\": \"AB12CD\",\n"
            "  \"name\": \"우리집\",\n"
            "  \"image\": 1,\n"
            "  \"member_count\": 2,\n"
            "  \"created_at\": \"2026-05-12T12:00:00Z\",\n"
            "  \"members\": [\n"
            "    {\"name\": \"홍길동\", \"profile_image\": 3, \"role\": 1, \"role_label\": \"관리자\"}\n"
            "  ]\n"
            "}\n"
            "```\n"
        ),
        parameters=[
            OpenApiParameter(
                "code",
                str,
                OpenApiParameter.PATH,
                description="6자리 대문자+숫자 초대코드 (예: 'AB12CD').",
            ),
        ],
        responses={
            200: OpenApiResponse(response=HomeInviteDetailSerializer, description="조회 성공."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="유효하지 않은 초대코드."),
        },
        examples=[
            OpenApiExample(
                "조회 성공",
                value={
                    "name": "우리집",
                    "image_id": 1,
                    "members": [
                        {
                            "uid": "8f3e2b1a-1234-4abc-9def-1234567890ab",
                            "name": "홍길동",
                            "profile_image": 3,
                            "role": "admin",
                        }
                    ],
                },
                response_only=True,
                status_codes=["200"],
            ),
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="유효하지 않은 초대코드입니다.", name="잘못된 초대코드"),
        ],
    )
    def get(self, request: Request, code: str) -> Response:
        home = selectors.get_home_by_invite_code(code)
        if home is None:
            raise NotFound("유효하지 않은 초대코드입니다.")
        return Response(HomeInviteDetailSerializer(home).data)


class HomeJoinView(APIView):
    """초대코드로 집 참여 (확정).

    이미 다른 집에 속한 유저는 먼저 나가야 한다 — 본 엔드포인트는 무한 멤버십을
    지원하지 않는다.
    """

    @extend_schema(
        tags=["Homes"],
        summary="초대코드로 집 참여 (구성원으로 합류)",
        description=(
            "## 🔥 설명\n"
            "초대코드 검증 후 호출자를 해당 집의 **구성원**(`role=2`)으로 등록한다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| body | `invite_code` | string | ✓ | 6자리 대문자+숫자 초대코드 |\n\n"
            "## 📤 응답 (200)\n"
            "참여 후 최신 집 정보. 필드는 `GET /homes/mine/` 와 동일.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 400 | `already_has_home` | 이미 다른 집에 속해 있음 |\n"
            "| 401 | `authentication_failed` | access 토큰 누락/만료 |\n"
            "| 404 | `not_found` | 유효하지 않은 초대코드 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X POST '{host}/api/v1/homes/join/' \\\n"
            "     -H 'Authorization: Bearer <access>' \\\n"
            "     -H 'Content-Type: application/json' \\\n"
            "     -d '{\"invite_code\":\"AB12CD\"}'\n"
            "```\n\n"
            "**응답 (200):**\n"
            "```json\n"
            "{\n"
            "  \"id\": 12,\n"
            "  \"name\": \"우리집\",\n"
            "  \"image\": 1,\n"
            "  \"invite_code\": \"AB12CD\",\n"
            "  \"status\": \"active\",\n"
            "  \"created_at\": \"2026-05-12T12:00:00Z\",\n"
            "  \"members\": [\n"
            "    {\"name\": \"홍길동\", \"profile_image\": 3, \"role\": 1, \"role_label\": \"관리자\"},\n"
            "    {\"name\": \"김철수\", \"profile_image\": 2, \"role\": 2, \"role_label\": \"구성원\"}\n"
            "  ]\n"
            "}\n"
            "```\n"
        ),
        request=HomeJoinSerializer,
        responses={
            200: OpenApiResponse(response=HomeOutputSerializer, description="참여 후 최신 집 정보."),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="이미 다른 집에 속해 있음."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="유효하지 않은 초대코드."),
        },
        examples=[
            OpenApiExample("정상 요청", value={"invite_code": "AB12CD"}, request_only=True),
            OpenApiExample(
                "참여 성공",
                value={
                    "id": 1,
                    "name": "우리집",
                    "image_id": 1,
                    "invite_code": "AB12CD",
                    "members": [
                        {
                            "uid": "8f3e2b1a-1234-4abc-9def-1234567890ab",
                            "name": "홍길동",
                            "profile_image": 3,
                            "role": "admin",
                        },
                        {
                            "uid": "9a4f3c2b-2345-4bcd-8def-2345678901bc",
                            "name": "김철수",
                            "profile_image": 1,
                            "role": "member",
                        },
                    ],
                },
                response_only=True,
                status_codes=["200"],
            ),
            error_example(code="already_has_home", message="이미 속한 집이 있습니다.", name="이미 집 있음"),
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="유효하지 않은 초대코드입니다.", name="잘못된 초대코드"),
        ],
    )
    def post(self, request: Request) -> Response:
        invite_code = request.data.get("invite_code", "")

        try:
            services.join_home(user=request.user, invite_code=invite_code)
        except services.AlreadyHasHomeError as e:
            raise ValidationError({"already_has_home": str(e)}) from e
        except services.HomeNotFoundError as e:
            raise NotFound(str(e)) from e

        home = selectors.get_user_home(request.user)
        return Response(HomeOutputSerializer(home).data)


# ── 나가기 / 관리자 양도 ──────────────────────────────────────────────────────


class HomeLeaveView(APIView):
    """집 나가기 (구성원 전용).

    관리자는 직접 나갈 수 없다 — 다른 구성원에게 양도하거나, 구성원이 0명이라면
    `DELETE /homes/mine/` 로 집을 삭제한 뒤 나갈 수 있다.
    """

    @extend_schema(
        tags=["Homes"],
        request=None,
        summary="집 나가기 (구성원 전용)",
        description=(
            "## 🔥 설명\n"
            "현재 유저가 집을 나간다. 관리자는 본 엔드포인트로 직접 나갈 수 없으며, 양도(`/homes/mine/transfer-admin/`) "
            "후 호출하거나 단독이라면 집을 삭제해야 한다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "요청 본문 없음.\n\n"
            "## 📤 응답 (204)\n"
            "응답 본문 없음.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 401 | `authentication_failed` | access 토큰 누락/만료 |\n"
            "| 403 | `admin_cannot_leave` | 관리자는 양도 또는 집 삭제 후 나가야 함 |\n"
            "| 404 | `not_found` | 속한 집 없음 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X POST '{host}/api/v1/homes/mine/leave/' \\\n"
            "     -H 'Authorization: Bearer <access>'\n"
            "```\n"
        ),
        responses={
            204: OpenApiResponse(description="나가기 완료 — 응답 본문 없음."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="관리자는 양도 또는 집 삭제 후 나갈 수 있음."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="속한 집 없음."),
        },
        examples=[
            _AUTH_FAILED_EXAMPLE,
            error_example(
                code="admin_cannot_leave",
                message="관리자는 직접 나갈 수 없습니다. 관리자를 양도하거나 집을 삭제해주세요.",
                name="관리자 직접 나가기 불가",
            ),
            error_example(code="not_found", message="속한 집이 없습니다.", name="집 미존재"),
        ],
    )
    def post(self, request: Request) -> Response:
        try:
            services.leave_home(user=request.user)
        except services.HomeNotFoundError as e:
            raise NotFound(str(e)) from e
        except services.AdminCannotLeaveError as e:
            raise PermissionDenied(str(e)) from e
        return Response(status=status.HTTP_204_NO_CONTENT)


class HomeTransferAdminView(APIView):
    """집 관리자 양도 (관리자 전용).

    대상은 **같은 집의 구성원**이어야 한다. 양도가 완료되면 호출자는 일반 구성원이
    되고, 대상은 관리자가 된다 — 이후 호출자가 추가 동작 없이 `/homes/mine/leave/`
    로 나갈 수 있다.
    """

    @extend_schema(
        tags=["Homes"],
        summary="관리자 양도 (관리자 전용)",
        description=(
            "## 🔥 설명\n"
            "집 관리자 권한을 같은 집의 구성원에게 양도한다. 양도 완료 시 호출자는 구성원, 대상은 관리자가 된다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| body | `user_id` | string (uuid) | ✓ | 양도받을 대상 유저의 uid. 반드시 같은 집의 구성원 |\n\n"
            "## 📤 응답 (204)\n"
            "응답 본문 없음.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 400 | `transfer_admin_target` | 대상이 같은 집의 구성원이 아니거나 본인 |\n"
            "| 401 | `authentication_failed` | access 토큰 누락/만료 |\n"
            "| 403 | `permission_denied` | 관리자만 양도 가능 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X POST '{host}/api/v1/homes/mine/transfer-admin/' \\\n"
            "     -H 'Authorization: Bearer <access>' \\\n"
            "     -H 'Content-Type: application/json' \\\n"
            "     -d '{\"user_id\":\"9a4f3c2b-2345-4bcd-8def-2345678901bc\"}'\n"
            "```\n"
        ),
        request=TransferAdminSerializer,
        responses={
            204: OpenApiResponse(description="양도 완료 — 응답 본문 없음."),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="대상이 같은 집의 구성원이 아님."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="관리자만 양도 가능."),
        },
        examples=[
            OpenApiExample(
                "정상 요청",
                value={"user_id": "9a4f3c2b-2345-4bcd-8def-2345678901bc"},
                request_only=True,
            ),
            error_example(
                code="transfer_admin_target",
                message="대상이 같은 집의 구성원이 아닙니다.",
                name="대상 무효",
            ),
            _AUTH_FAILED_EXAMPLE,
            error_example(
                code="permission_denied",
                message="관리자만 양도할 수 있습니다.",
                name="관리자 아님",
            ),
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = TransferAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            services.transfer_admin(user=request.user, target_uid=serializer.validated_data["user_id"])
        except services.NotHomeAdminError as e:
            raise PermissionDenied(str(e)) from e
        except services.TransferAdminTargetError as e:
            raise ValidationError({"transfer_admin_target": str(e)}) from e
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── 집안일 ────────────────────────────────────────────────────────────────────


class HomeChoreListView(APIView):
    """집안일 목록 조회 + 추가.

    - `GET`: 현재 유저가 속한 집의 집안일 목록을 반환 (속한 집 없으면 404).
    - `POST`: 관리자 전용. 단건/복수 등록을 동일한 `chores` 배열로 처리한다.
    """

    @extend_schema(
        tags=["Homes"],
        operation_id="v1_homes_mine_chores_list",
        summary="내 집의 집안일 목록 조회",
        description=(
            "## 🔥 설명\n"
            "현재 유저가 속한 집의 **활성** 집안일을 PK 오름차순으로 반환한다. 삭제(비활성화)된 집안일은 "
            "제외된다. 비어 있는 집은 200 + `[]`. 다른 집의 집안일은 노출되지 않는다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "요청 본문 없음.\n\n"
            "## 📤 응답 (200)\n"
            "배열 응답. 각 원소는 다음 필드를 포함한다.\n\n"
            "| 위치 | 필드 | 타입 | 설명 |\n"
            "| --- | --- | --- | --- |\n"
            "| body[*] | `id` | integer | HomeChore PK (메모 경로의 부모 ID) |\n"
            "| body[*] | `category` | integer | 카테고리 enum (1=쓰레기 ~ 5=세탁) |\n"
            "| body[*] | `category_label` | string | 카테고리 한글 |\n"
            "| body[*] | `name` | string | 집안일 제목 |\n"
            "| body[*] | `description` | string | 설명 (없으면 \"\") |\n"
            "| body[*] | `repeat_days` | integer[] | 반복 요일 (0=월 ~ 6=일) |\n"
            "| body[*] | `repeat_days_label` | string[] | 반복 요일 한글 (예: ['월','목']) |\n"
            "| body[*] | `difficulty` | integer | 난이도 enum (1~5) |\n"
            "| body[*] | `difficulty_label` | string | 3단계 라벨: '쉬움'(1~2), '중간'(3~4), '어려움'(5) |\n"
            "| body[*] | `point` | integer | 난이도 고정 포인트: 40/80/120/160/200 |\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 401 | `authentication_failed` | access 토큰 누락/만료 |\n"
            "| 404 | `not_found` | 속한 집 없음 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X GET '{host}/api/v1/homes/mine/chores/' \\\n"
            "     -H 'Authorization: Bearer <access>'\n"
            "```\n\n"
            "**응답 (200):**\n"
            "```json\n"
            "[\n"
            "  {\n"
            "    \"id\": 1,\n"
            "    \"category\": 3, \"category_label\": \"청소\",\n"
            "    \"name\": \"거실 청소\", \"description\": \"주 1회\",\n"
            "    \"repeat_days\": [0, 3], \"repeat_days_label\": [\"월\", \"목\"],\n"
            "    \"difficulty\": 2, \"difficulty_label\": \"쉬움\", \"point\": 80\n"
            "  }\n"
            "]\n"
            "```\n"
        ),
        responses={
            200: OpenApiResponse(
                response=HomeChoreOutputSerializer(many=True),
                description="집안일 배열 (비어 있을 수 있음).",
            ),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="속한 집 없음."),
        },
        examples=[
            OpenApiExample(
                "집안일 목록",
                value=[
                    {
                        "id": 1,
                        "category": 3,
                        "name": "거실 청소",
                        "description": "주 1회",
                        "repeat_days": [0, 3],
                        "repeat_days_label": ["월", "목"],
                        "difficulty": 2,
                        "difficulty_label": "쉬움",
                        "point": 80,
                    },
                    {
                        "id": 2,
                        "category": 5,
                        "name": "분리수거",
                        "description": "매주 화요일",
                        "repeat_days": [1],
                        "repeat_days_label": ["화"],
                        "difficulty": 3,
                        "difficulty_label": "중간",
                        "point": 120,
                    },
                ],
                response_only=True,
                status_codes=["200"],
            ),
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="속한 집이 없습니다.", name="집 미존재"),
        ],
    )
    def get(self, request: Request) -> Response:
        home = selectors.get_user_home(request.user)
        if home is None:
            raise NotFound("속한 집이 없습니다.")
        home_chores = selectors.get_home_chores(home)
        return Response(HomeChoreOutputSerializer(home_chores, many=True).data)

    @extend_schema(
        tags=["Homes"],
        summary="집안일 추가 (스타터팩 또는 커스텀)",
        description=(
            "## 🔥 설명\n"
            "현재 유저의 집에 집안일을 추가한다. **`starter_pack_id` 또는 `chores` 중 정확히 하나**만 지정한다. "
            "응답은 신규 생성된 `HomeChore` 배열(스타터팩 적용 시 skip 된 항목은 제외).\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| body | `starter_pack_id` | integer\\|null | - | 적용할 스타터팩 PK. `chores` 와 동시 사용 불가 |\n"
            "| body | `chores` | array | - | 사용자 정의 집안일 목록 (단건도 길이 1 배열) |\n"
            "| body | `chores[].category` | integer | ✓ | 카테고리 (1=쓰레기 ~ 5=세탁) |\n"
            "| body | `chores[].name` | string | ✓ | 집안일 제목 (1~20자) |\n"
            "| body | `chores[].description` | string | - | 설명 (최대 20자, 기본 \"\") |\n"
            "| body | `chores[].repeat_days` | integer[] | - | 반복 요일 (0=월 ~ 6=일) |\n"
            "| body | `chores[].difficulty` | integer | ✓ | 난이도 (1=하 ~ 5=상) |\n\n"
            "## 📤 응답 (201)\n"
            "배열 응답 — 각 원소는 `GET /homes/mine/chores/` 와 동일한 필드.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 400 | `ambiguous_chore_input` | `starter_pack_id` 와 `chores` 동시 지정 |\n"
            "| 400 | `missing_chore_input` | 둘 다 비어 있음 |\n"
            "| 401 | `authentication_failed` | access 토큰 누락/만료 |\n"
            "| 404 | `not_found` | 속한 집 없음 또는 `starter_pack_id` 미존재 |\n\n"
            "## 💻 예제\n"
            "**요청 (스타터팩):**\n"
            "```bash\n"
            "curl -X POST '{host}/api/v1/homes/mine/chores/' \\\n"
            "     -H 'Authorization: Bearer <access>' \\\n"
            "     -H 'Content-Type: application/json' \\\n"
            "     -d '{\"starter_pack_id\": 1}'\n"
            "```\n\n"
            "**요청 (커스텀):**\n"
            "```bash\n"
            "curl -X POST '{host}/api/v1/homes/mine/chores/' \\\n"
            "     -H 'Authorization: Bearer <access>' \\\n"
            "     -H 'Content-Type: application/json' \\\n"
            "     -d '{\"chores\":[{\"category\":3,\"name\":\"거실 청소\",\"repeat_days\":[0],\"difficulty\":2}]}'\n"
            "```\n\n"
            "**응답 (201):**\n"
            "```json\n"
            "[\n"
            "  {\n"
            "    \"id\": 1, \"category\": 3, \"category_label\": \"청소\",\n"
            "    \"name\": \"거실 청소\", \"description\": \"\",\n"
            "    \"repeat_days\": [0], \"repeat_days_label\": [\"월\"],\n"
            "    \"difficulty\": 2, \"difficulty_label\": \"쉬움\", \"point\": 80\n"
            "  }\n"
            "]\n"
            "```\n"
        ),
        request=HomeChoreListCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=HomeChoreOutputSerializer(many=True),
                description="생성된 집안일 배열 (스타터팩 적용 시 신규로 추가된 것만).",
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="유효성 검사 실패 / 입력 분기 오류 (`ambiguous_chore_input`, `missing_chore_input`).",
            ),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="속한 집 없음 또는 `starter_pack_id` 에 해당하는 chore 없음.",
            ),
        },
        examples=[
            OpenApiExample("스타터팩 적용", value={"starter_pack_id": 1}, request_only=True),
            OpenApiExample(
                "커스텀 단건",
                value={
                    "chores": [
                        {
                            "category": 3,
                            "name": "거실 청소",
                            "description": "주 1회",
                            "repeat_days": [0],
                            "difficulty": 2,
                        }
                    ]
                },
                request_only=True,
            ),
            OpenApiExample(
                "커스텀 복수",
                value={
                    "chores": [
                        {"category": 3, "name": "거실 청소", "description": "주 1회", "repeat_days": [0], "difficulty": 2},
                        {"category": 5, "name": "분리수거", "description": "매주 화요일", "repeat_days": [1], "difficulty": 3},
                    ]
                },
                request_only=True,
            ),
            OpenApiExample(
                "생성 성공 (단건)",
                value=[
                    {
                        "id": 1,
                        "category": 3,
                        "name": "거실 청소",
                        "description": "주 1회",
                        "repeat_days": [0],
                        "repeat_days_label": ["월"],
                        "difficulty": 2,
                        "difficulty_label": "쉬움",
                        "point": 80,
                    }
                ],
                response_only=True,
                status_codes=["201"],
            ),
            error_example(
                code="ambiguous_chore_input",
                message="starter_pack_id 와 chores 는 동시에 지정할 수 없습니다.",
                name="입력 분기 오류",
            ),
            error_example(
                code="missing_chore_input",
                message="starter_pack_id 또는 chores 중 하나는 필수입니다.",
                name="입력 누락",
            ),
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="속한 집이 없습니다.", name="집 미존재"),
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = HomeChoreListCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        starter_pack_id = data.get("starter_pack_id")

        try:
            if starter_pack_id is not None:
                home_chores = services.apply_starter_pack(
                    user=request.user,
                    starter_pack_id=starter_pack_id,
                    chore_ids=data.get("starter_pack_chore_ids"),
                )
            else:
                home_chores = services.create_home_chores(
                    user=request.user,
                    chores=data["chores"],
                )
        except services.HomeNotFoundError as e:
            raise NotFound(str(e)) from e
        except services.StarterPackNotFoundError as e:
            raise NotFound(str(e)) from e

        return Response(HomeChoreOutputSerializer(home_chores, many=True).data, status=status.HTTP_201_CREATED)


# ── 집안일 단건 상세 / 수정 / 삭제 ────────────────────────────────────────────


class HomeChoreDetailView(APIView):
    """집안일 단건 상세조회 / 수정 / 삭제.

    본인 집의 HomeChore 만 접근 가능 — 다른 집·미존재는 항상 404 (존재 비노출).
    수정/삭제는 구성원 누구나 가능하며, 수정은 항상 copy-on-write 로 본인 집 전용
    사본을 만들어 원본(과거 데이터)을 보존한다. 삭제는 완료 이력이 있으면
    비활성화(soft-delete), 없으면 물리 삭제한다. 삭제된 집안일은 상세 조회만
    가능하다 (`is_active=false` 로 구분).
    """

    _OUTPUT_FIELDS_TABLE = (
        "| 위치 | 필드 | 타입 | 설명 |\n"
        "| --- | --- | --- | --- |\n"
        "| body | `id` | integer | HomeChore PK |\n"
        "| body | `category` | integer | 카테고리 enum (1=쓰레기 ~ 5=세탁) |\n"
        "| body | `category_label` | string | 카테고리 한글 |\n"
        "| body | `name` | string | 집안일 제목 |\n"
        "| body | `description` | string | 설명 (없으면 \"\") |\n"
        "| body | `repeat_days` | integer[] | 반복 요일 (0=월 ~ 6=일) |\n"
        "| body | `repeat_days_label` | string[] | 반복 요일 한글 (예: ['월','목']) |\n"
        "| body | `difficulty` | integer | 난이도 enum (1~5) |\n"
        "| body | `difficulty_label` | string | 3단계 라벨: '쉬움'(1~2), '중간'(3~4), '어려움'(5) |\n"
        "| body | `point` | integer | 난이도 고정 포인트: 40/80/120/160/200 |\n"
        "| body | `is_active` | boolean | 활성 여부. false 면 삭제(비활성화)된 집안일 — 상세 화면에서 안내 |\n\n"
    )

    @extend_schema(
        tags=["Homes"],
        operation_id="v1_homes_mine_chores_retrieve",
        summary="내 집 집안일 단건 상세조회",
        description=(
            "## 🔥 설명\n"
            "본인 집의 집안일 한 건을 상세 조회한다. 다른 집의 집안일은 존재 자체를 노출하지 않고 404 를 반환한다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `home_chore_id` | integer | ✓ | 조회할 HomeChore PK |\n\n"
            "## 📤 응답 (200)\n"
            + _OUTPUT_FIELDS_TABLE
            + "### 이번 주 진행상태 (`weekly_progress`)\n"
            "월 시작 ~ 일 종료, 7개 원소(0=월 ~ 6=일) 배열. 완료는 **집(home) 단위** — 같은 날 누군가 끝내면 "
            "그 날 = `completed`, `completed_by` 에 완료자 정보(닉네임/uid/profile_image)가 채워진다.\n\n"
            "| 필드 | 타입 | 설명 |\n"
            "| --- | --- | --- |\n"
            "| `weekday` | integer | 0=월 ~ 6=일 |\n"
            "| `label` | string | 한글 요일 (월/화/…/일) |\n"
            "| `status` | string | `completed` / `incomplete` / `not_scheduled` |\n"
            "| `completed_by` | object \\| null | `status=completed` 시 "
            "`{uid, name, profile_image}`. 탈퇴 유저면 null |\n\n"
            "상태값 정의:\n"
            "- `completed` — 그 요일에 해당하는 이번 주 날짜에 완료 이력이 있다.\n"
            "- `incomplete` — `repeat_days` 에 포함된 요일이지만 이번 주 완료 이력이 없다.\n"
            "- `not_scheduled` — `repeat_days` 에 포함되지 않은 요일.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 401 | `authentication_failed` | access 토큰 누락/만료 |\n"
            "| 404 | `not_found` | 집안일 미존재 또는 다른 집의 집안일 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X GET '{host}/api/v1/homes/mine/chores/12/' \\\n"
            "     -H 'Authorization: Bearer <access>'\n"
            "```\n\n"
            "**응답 (200):**\n"
            "```json\n"
            "{\n"
            "  \"id\": 12, \"category\": 3, \"category_label\": \"청소\",\n"
            "  \"name\": \"거실 청소\", \"description\": \"주 1회\",\n"
            "  \"repeat_days\": [0, 3], \"repeat_days_label\": [\"월\", \"목\"],\n"
            "  \"difficulty\": 2, \"difficulty_label\": \"쉬움\", \"point\": 80,\n"
            "  \"weekly_progress\": [\n"
            "    {\"weekday\": 0, \"label\": \"월\", \"status\": \"completed\","
            " \"completed_by\": {\"uid\": \"8f3e...\", \"name\": \"홍길동\", \"profile_image\": 3}},\n"
            "    {\"weekday\": 1, \"label\": \"화\", \"status\": \"not_scheduled\", \"completed_by\": null},\n"
            "    {\"weekday\": 2, \"label\": \"수\", \"status\": \"not_scheduled\", \"completed_by\": null},\n"
            "    {\"weekday\": 3, \"label\": \"목\", \"status\": \"incomplete\", \"completed_by\": null},\n"
            "    {\"weekday\": 4, \"label\": \"금\", \"status\": \"not_scheduled\", \"completed_by\": null},\n"
            "    {\"weekday\": 5, \"label\": \"토\", \"status\": \"not_scheduled\", \"completed_by\": null},\n"
            "    {\"weekday\": 6, \"label\": \"일\", \"status\": \"not_scheduled\", \"completed_by\": null}\n"
            "  ]\n"
            "}\n"
            "```\n"
        ),
        responses={
            200: OpenApiResponse(response=HomeChoreDetailOutputSerializer, description="조회 성공."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="집안일 미존재 또는 다른 집의 집안일.",
            ),
        },
        examples=[
            OpenApiExample(
                "조회 성공",
                value={
                    "id": 12,
                    "category": 3,
                    "category_label": "청소",
                    "name": "거실 청소",
                    "description": "주 1회",
                    "repeat_days": [0, 3],
                    "repeat_days_label": ["월", "목"],
                    "difficulty": 2,
                    "difficulty_label": "쉬움",
                    "point": 80,
                    "weekly_progress": [
                        {
                            "weekday": 0,
                            "label": "월",
                            "status": "completed",
                            "completed_by": {
                                "uid": "8f3e2b1a-1234-4abc-9def-1234567890ab",
                                "name": "홍길동",
                                "profile_image": 3,
                            },
                        },
                        {"weekday": 1, "label": "화", "status": "not_scheduled", "completed_by": None},
                        {"weekday": 2, "label": "수", "status": "not_scheduled", "completed_by": None},
                        {"weekday": 3, "label": "목", "status": "incomplete", "completed_by": None},
                        {"weekday": 4, "label": "금", "status": "not_scheduled", "completed_by": None},
                        {"weekday": 5, "label": "토", "status": "not_scheduled", "completed_by": None},
                        {"weekday": 6, "label": "일", "status": "not_scheduled", "completed_by": None},
                    ],
                },
                response_only=True,
                status_codes=["200"],
            ),
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="집안일을 찾을 수 없습니다.", name="집안일 미존재"),
        ],
    )
    def get(self, request: Request, home_chore_id: int) -> Response:
        home_chore = selectors.get_user_home_chore(request.user, home_chore_id)
        if home_chore is None:
            raise NotFound("집안일을 찾을 수 없습니다.")
        return Response(HomeChoreDetailOutputSerializer(home_chore).data)

    @extend_schema(
        tags=["Homes"],
        summary="내 집 집안일 부분 수정 (PATCH)",
        description=(
            "## 🔥 설명\n"
            "본인 집의 집안일 메타를 부분 수정한다. **구성원 누구나** 호출 가능. 모든 필드는 optional 이며 "
            "전달된 키만 적용된다. 수정은 항상 **copy-on-write** — 원본 Chore 는 보존되고(과거 이력·분담안 "
            "히스토리 보존) 본인 집 전용 사본이 새로 생성되어 `HomeChore.chore` 가 교체된다(응답의 `id` 는 그대로). "
            "포인트는 난이도에 따라 자동 재계산된다. 삭제(비활성화)된 집안일은 404.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `home_chore_id` | integer | ✓ | 수정할 HomeChore PK |\n"
            "| body | `category` | integer | - | 카테고리 (1~5) |\n"
            "| body | `name` | string | - | 집안일 제목 (1~20자) |\n"
            "| body | `description` | string | - | 설명 (최대 20자, 빈 문자열 허용) |\n"
            "| body | `repeat_days` | integer[] | - | 반복 요일 (0=월 ~ 6=일) |\n"
            "| body | `difficulty` | integer | - | 난이도 (1~5) |\n\n"
            "## 📤 응답 (200)\n"
            + _OUTPUT_FIELDS_TABLE
            + "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 400 | `invalid` | 필드 형식 위반 (잘못된 enum 값, 길이 초과 등) |\n"
            "| 401 | `authentication_failed` | access 토큰 누락/만료 |\n"
            "| 404 | `not_found` | 집안일 미존재 또는 다른 집의 집안일 |\n\n"
            "## 💻 예제\n"
            "**요청 (이름·요일만 수정):**\n"
            "```bash\n"
            "curl -X PATCH '{host}/api/v1/homes/mine/chores/12/' \\\n"
            "     -H 'Authorization: Bearer <access>' \\\n"
            "     -H 'Content-Type: application/json' \\\n"
            "     -d '{\"name\":\"거실 대청소\",\"repeat_days\":[0,3]}'\n"
            "```\n\n"
            "**응답 (200):**\n"
            "```json\n"
            "{\n"
            "  \"id\": 12, \"category\": 3, \"category_label\": \"청소\",\n"
            "  \"name\": \"거실 대청소\", \"description\": \"주 1회\",\n"
            "  \"repeat_days\": [0, 3], \"repeat_days_label\": [\"월\", \"목\"],\n"
            "  \"difficulty\": 2, \"difficulty_label\": \"쉬움\", \"point\": 80\n"
            "}\n"
            "```\n"
        ),
        request=HomeChoreUpdateSerializer,
        responses={
            200: OpenApiResponse(response=HomeChoreOutputSerializer, description="수정된 집안일."),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="유효성 검사 실패."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="집안일 미존재 또는 다른 집의 집안일.",
            ),
        },
        examples=[
            OpenApiExample(
                "이름·요일 부분 수정",
                value={"name": "거실 대청소", "repeat_days": [0, 3]},
                request_only=True,
            ),
            OpenApiExample(
                "난이도만 수정",
                value={"difficulty": 4},
                request_only=True,
            ),
            error_example(code="invalid", message="\"difficulty\" 는 1~5 사이의 정수여야 합니다.", name="잘못된 enum"),
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="집안일을 찾을 수 없습니다.", name="집안일 미존재"),
        ],
    )
    def patch(self, request: Request, home_chore_id: int) -> Response:
        serializer = HomeChoreUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            home_chore = services.update_home_chore(
                user=request.user,
                home_chore_id=home_chore_id,
                fields=serializer.validated_data,
            )
        except services.HomeChoreNotFoundError as e:
            raise NotFound(str(e)) from e
        return Response(HomeChoreOutputSerializer(home_chore).data)

    @extend_schema(
        tags=["Homes"],
        summary="내 집 집안일 삭제 (구성원 누구나, 이력 있으면 비활성화)",
        description=(
            "## 🔥 설명\n"
            "본인 집의 집안일을 삭제한다. **구성원 누구나** 호출 가능. 완료 이력이 있으면 물리 삭제 대신 "
            "**비활성화(soft-delete)** 되어 리포트/기여도/히스토리 데이터가 보존되고, 이력이 전혀 없으면 물리 "
            "삭제된다. 비활성화된 집안일은 목록·다음 분담안에서 제외되며 상세 조회(`is_active=false`)만 가능하다. "
            "원본 `Chore` 는 항상 보존되고, 스타터팩 chore 의 경우 다른 집 연결에 영향을 주지 않는다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `home_chore_id` | integer | ✓ | 삭제할 HomeChore PK |\n\n"
            "## 📤 응답 (204)\n"
            "응답 본문 없음.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 401 | `authentication_failed` | access 토큰 누락/만료 |\n"
            "| 404 | `not_found` | 집안일 미존재 또는 다른 집의 집안일 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X DELETE '{host}/api/v1/homes/mine/chores/12/' \\\n"
            "     -H 'Authorization: Bearer <access>'\n"
            "```\n"
        ),
        responses={
            204: OpenApiResponse(description="삭제 성공 (응답 본문 없음)."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="집안일 미존재 또는 다른 집의 집안일.",
            ),
        },
        examples=[
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="집안일을 찾을 수 없습니다.", name="집안일 미존재"),
        ],
    )
    def delete(self, request: Request, home_chore_id: int) -> Response:
        try:
            services.delete_home_chore(user=request.user, home_chore_id=home_chore_id)
        except services.HomeChoreNotFoundError as e:
            raise NotFound(str(e)) from e
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── 집안일 메모 (1:N) ──────────────────────────────────────────────────────────


class HomeChoreNoteListView(APIView):
    """집안일 메모 목록 조회 / 작성.

    Figma \"집안일 상세\" 의 메모 섹션이 다중 작성자 메모를 노출하므로 1:N 으로
    설계되어 있다.
    """

    @extend_schema(
        tags=["Homes"],
        summary="집안일 메모 목록 조회",
        description=(
            "## 🔥 설명\n"
            "지정한 집안일의 메모 목록을 PK 오름차순으로 반환한다. 본인 집의 집안일이 아니면 404. "
            "메모 0개여도 200 + `[]`.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `home_chore_id` | integer | ✓ | 대상 HomeChore PK |\n\n"
            "## 📤 응답 (200)\n"
            "배열 응답.\n\n"
            "| 위치 | 필드 | 타입 | 설명 |\n"
            "| --- | --- | --- | --- |\n"
            "| body[*] | `id` | integer | HomeChoreNote PK |\n"
            "| body[*] | `author.uid` | string (uuid) | 작성자 uid |\n"
            "| body[*] | `author.name` | string | 작성자 닉네임 |\n"
            "| body[*] | `author.profile_image` | integer\\|null | 작성자 프로필 이미지 enum |\n"
            "| body[*] | `content` | string | 메모 본문 (1~200자) |\n"
            "| body[*] | `created_at` | string (datetime) | 생성 일시 |\n"
            "| body[*] | `updated_at` | string (datetime) | 최종 수정 일시 |\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 401 | `authentication_failed` | access 토큰 누락/만료 |\n"
            "| 404 | `not_found` | 해당 집안일이 본인 집에 없음 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X GET '{host}/api/v1/homes/mine/chores/1/notes/' \\\n"
            "     -H 'Authorization: Bearer <access>'\n"
            "```\n\n"
            "**응답 (200):**\n"
            "```json\n"
            "[\n"
            "  {\n"
            "    \"id\": 1,\n"
            "    \"author\": {\"uid\": \"8f3e2b1a-1234-4abc-9def-1234567890ab\", \"name\": \"홍길동\", \"profile_image\": 3},\n"
            "    \"content\": \"락스 사용 시 환기 필수\",\n"
            "    \"created_at\": \"2026-05-13T12:00:00Z\",\n"
            "    \"updated_at\": \"2026-05-13T12:00:00Z\"\n"
            "  }\n"
            "]\n"
            "```\n"
        ),
        parameters=[
            OpenApiParameter(
                "home_chore_id", int, OpenApiParameter.PATH, description="대상 HomeChore PK."
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=HomeChoreNoteOutputSerializer(many=True),
                description="메모 배열 (작성자 정보 포함).",
            ),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="해당 집안일이 본인 집에 없음."),
        },
        examples=[
            OpenApiExample(
                "메모 목록",
                value=[
                    {
                        "id": 1,
                        "author": {
                            "uid": "8f3e2b1a-1234-4abc-9def-1234567890ab",
                            "name": "홍길동",
                            "profile_image": 3,
                        },
                        "content": "락스 사용 시 환기 필수",
                        "created_at": "2026-05-12T10:00:00Z",
                        "updated_at": "2026-05-12T10:00:00Z",
                    }
                ],
                response_only=True,
                status_codes=["200"],
            ),
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="집안일을 찾을 수 없습니다.", name="집안일 미존재"),
        ],
    )
    def get(self, request: Request, home_chore_id: int) -> Response:
        notes = selectors.get_home_chore_notes(request.user, home_chore_id)
        if notes is None:
            raise NotFound("집안일을 찾을 수 없습니다.")
        return Response(HomeChoreNoteOutputSerializer(notes, many=True).data)

    @extend_schema(
        tags=["Homes"],
        summary="집안일 메모 작성",
        description=(
            "## 🔥 설명\n"
            "지정한 집안일에 메모를 작성한다. 작성자(`author`) 는 호출자로 자동 설정된다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `home_chore_id` | integer | ✓ | 대상 HomeChore PK |\n"
            "| body | `content` | string | ✓ | 메모 본문 (1~200자, 빈 문자열 불가) |\n\n"
            "## 📤 응답 (201)\n"
            "필드는 `GET` 응답의 단일 원소와 동일.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 400 | `invalid` | content 길이 위반 또는 빈 문자열 |\n"
            "| 401 | `authentication_failed` | access 토큰 누락/만료 |\n"
            "| 404 | `not_found` | 해당 집안일이 본인 집에 없음 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X POST '{host}/api/v1/homes/mine/chores/1/notes/' \\\n"
            "     -H 'Authorization: Bearer <access>' \\\n"
            "     -H 'Content-Type: application/json' \\\n"
            "     -d '{\"content\":\"락스 사용 시 환기 필수\"}'\n"
            "```\n\n"
            "**응답 (201):**\n"
            "```json\n"
            "{\n"
            "  \"id\": 1,\n"
            "  \"author\": {\"uid\": \"8f3e2b1a-1234-4abc-9def-1234567890ab\", \"name\": \"홍길동\", \"profile_image\": 3},\n"
            "  \"content\": \"락스 사용 시 환기 필수\",\n"
            "  \"created_at\": \"2026-05-13T12:00:00Z\",\n"
            "  \"updated_at\": \"2026-05-13T12:00:00Z\"\n"
            "}\n"
            "```\n"
        ),
        parameters=[
            OpenApiParameter(
                "home_chore_id", int, OpenApiParameter.PATH, description="대상 HomeChore PK."
            ),
        ],
        request=HomeChoreNoteCreateSerializer,
        responses={
            201: OpenApiResponse(response=HomeChoreNoteOutputSerializer, description="생성된 메모."),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="유효성 검사 실패 (`content` 길이 초과 등).",
            ),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="해당 집안일이 본인 집에 없음."),
        },
        examples=[
            OpenApiExample("메모 작성", value={"content": "락스 사용 시 환기 필수"}, request_only=True),
            OpenApiExample(
                "작성 성공",
                value={
                    "id": 1,
                    "author": {
                        "uid": "8f3e2b1a-1234-4abc-9def-1234567890ab",
                        "name": "홍길동",
                        "profile_image": 3,
                    },
                    "content": "락스 사용 시 환기 필수",
                    "created_at": "2026-05-12T10:00:00Z",
                    "updated_at": "2026-05-12T10:00:00Z",
                },
                response_only=True,
                status_codes=["201"],
            ),
            error_example(code="invalid", message="content 는 200자 이하여야 합니다.", name="내용 길이 초과"),
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="집안일을 찾을 수 없습니다.", name="집안일 미존재"),
        ],
    )
    def post(self, request: Request, home_chore_id: int) -> Response:
        serializer = HomeChoreNoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            note = services.create_home_chore_note(
                user=request.user,
                home_chore_id=home_chore_id,
                content=serializer.validated_data["content"],
            )
        except services.HomeChoreNotFoundError as e:
            raise NotFound(str(e)) from e

        return Response(HomeChoreNoteOutputSerializer(note).data, status=status.HTTP_201_CREATED)


class HomeChoreNoteDetailView(APIView):
    """집안일 메모 수정 / 삭제 (작성자 전용)."""

    @extend_schema(
        tags=["Homes"],
        summary="집안일 메모 수정 (작성자 전용)",
        description=(
            "## 🔥 설명\n"
            "지정한 메모의 본문을 변경한다. **본인이 작성한 메모만** 수정 가능 (위반 시 403).\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `home_chore_id` | integer | ✓ | 대상 HomeChore PK |\n"
            "| path | `note_id` | integer | ✓ | 대상 메모 PK |\n"
            "| body | `content` | string | ✓ | 새 메모 본문 (1~200자) |\n\n"
            "## 📤 응답 (200)\n"
            "필드는 `GET` 응답의 단일 원소와 동일.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 400 | `invalid` | content 길이 위반 또는 빈 문자열 |\n"
            "| 401 | `authentication_failed` | access 토큰 누락/만료 |\n"
            "| 403 | `permission_denied` | 작성자만 수정 가능 |\n"
            "| 404 | `not_found` | 집안일/메모 미존재 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X PATCH '{host}/api/v1/homes/mine/chores/1/notes/1/' \\\n"
            "     -H 'Authorization: Bearer <access>' \\\n"
            "     -H 'Content-Type: application/json' \\\n"
            "     -d '{\"content\":\"수정된 내용\"}'\n"
            "```\n"
        ),
        parameters=[
            OpenApiParameter(
                "home_chore_id", int, OpenApiParameter.PATH, description="대상 HomeChore PK."
            ),
            OpenApiParameter("note_id", int, OpenApiParameter.PATH, description="대상 메모 PK."),
        ],
        request=HomeChoreNoteUpdateSerializer,
        responses={
            200: OpenApiResponse(response=HomeChoreNoteOutputSerializer, description="수정된 메모."),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="유효성 검사 실패."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="작성자만 수정 가능."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="해당 집안일 또는 메모를 찾을 수 없음."),
        },
        examples=[
            OpenApiExample("메모 수정", value={"content": "수정된 내용"}, request_only=True),
            OpenApiExample(
                "수정 성공",
                value={
                    "id": 1,
                    "author": {
                        "uid": "8f3e2b1a-1234-4abc-9def-1234567890ab",
                        "name": "홍길동",
                        "profile_image": 3,
                    },
                    "content": "수정된 내용",
                    "created_at": "2026-05-12T10:00:00Z",
                    "updated_at": "2026-05-12T11:30:00Z",
                },
                response_only=True,
                status_codes=["200"],
            ),
            error_example(code="invalid", message="content 는 200자 이하여야 합니다.", name="내용 길이 초과"),
            _AUTH_FAILED_EXAMPLE,
            error_example(
                code="permission_denied",
                message="본인이 작성한 메모만 수정할 수 있습니다.",
                name="작성자 아님",
            ),
            error_example(code="not_found", message="메모를 찾을 수 없습니다.", name="메모 미존재"),
        ],
    )
    def patch(self, request: Request, home_chore_id: int, note_id: int) -> Response:
        serializer = HomeChoreNoteUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            note = services.update_home_chore_note(
                user=request.user,
                home_chore_id=home_chore_id,
                note_id=note_id,
                content=serializer.validated_data["content"],
            )
        except services.HomeChoreNotFoundError as e:
            raise NotFound(str(e)) from e
        except services.HomeChoreNoteNotFoundError as e:
            raise NotFound(str(e)) from e
        except services.NotNoteAuthorError as e:
            raise PermissionDenied(str(e)) from e

        return Response(HomeChoreNoteOutputSerializer(note).data)

    @extend_schema(
        tags=["Homes"],
        summary="집안일 메모 삭제 (작성자 전용)",
        description=(
            "## 🔥 설명\n"
            "**본인이 작성한 메모만** 삭제 가능 (위반 시 403).\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `home_chore_id` | integer | ✓ | 대상 HomeChore PK |\n"
            "| path | `note_id` | integer | ✓ | 대상 메모 PK |\n\n"
            "## 📤 응답 (204)\n"
            "응답 본문 없음.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 401 | `authentication_failed` | access 토큰 누락/만료 |\n"
            "| 403 | `permission_denied` | 작성자만 삭제 가능 |\n"
            "| 404 | `not_found` | 집안일/메모 미존재 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X DELETE '{host}/api/v1/homes/mine/chores/1/notes/1/' \\\n"
            "     -H 'Authorization: Bearer <access>'\n"
            "```\n"
        ),
        parameters=[
            OpenApiParameter(
                "home_chore_id", int, OpenApiParameter.PATH, description="대상 HomeChore PK."
            ),
            OpenApiParameter("note_id", int, OpenApiParameter.PATH, description="대상 메모 PK."),
        ],
        responses={
            204: OpenApiResponse(description="삭제 완료 — 응답 본문 없음."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="작성자만 삭제 가능."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="해당 집안일 또는 메모를 찾을 수 없음."),
        },
        examples=[
            _AUTH_FAILED_EXAMPLE,
            error_example(
                code="permission_denied",
                message="본인이 작성한 메모만 삭제할 수 있습니다.",
                name="작성자 아님",
            ),
            error_example(code="not_found", message="메모를 찾을 수 없습니다.", name="메모 미존재"),
        ],
    )
    def delete(self, request: Request, home_chore_id: int, note_id: int) -> Response:
        try:
            services.delete_home_chore_note(
                user=request.user,
                home_chore_id=home_chore_id,
                note_id=note_id,
            )
        except services.HomeChoreNotFoundError as e:
            raise NotFound(str(e)) from e
        except services.HomeChoreNoteNotFoundError as e:
            raise NotFound(str(e)) from e
        except services.NotNoteAuthorError as e:
            raise PermissionDenied(str(e)) from e

        return Response(status=status.HTTP_204_NO_CONTENT)


# ── 스타터팩 ──────────────────────────────────────────────────────────────────


class StarterPackListView(APIView):
    """스타터팩 메타 목록.

    각 스타터팩의 집안일 상세는 `/starter-packs/{id}/chores/` 로 별도 조회한다.
    """

    @extend_schema(
        tags=["StarterPacks"],
        summary="스타터팩 목록 조회",
        description=(
            "## 🔥 설명\n"
            "사전 등록된 스타터팩(집안일 프리셋 묶음) 의 메타 정보 배열을 반환한다. 집안일 상세는 "
            "`/starter-packs/{id}/chores/` 로 별도 조회한다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "요청 본문 없음.\n\n"
            "## 📤 응답 (200)\n"
            "배열 응답.\n\n"
            "| 위치 | 필드 | 타입 | 설명 |\n"
            "| --- | --- | --- | --- |\n"
            "| body[*] | `id` | integer | 스타터팩 PK |\n"
            "| body[*] | `name` | string | 스타터팩 이름 |\n"
            "| body[*] | `description` | string | 설명 (없으면 \"\") |\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 401 | `authentication_failed` | access 토큰 누락/만료 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X GET '{host}/api/v1/starter-packs/' \\\n"
            "     -H 'Authorization: Bearer <access>'\n"
            "```\n\n"
            "**응답 (200):**\n"
            "```json\n"
            "[\n"
            "  {\"id\": 1, \"name\": \"기본 청소\", \"description\": \"1인 가구용 기본 팩\"},\n"
            "  {\"id\": 2, \"name\": \"패밀리\", \"description\": \"아이 있는 가정용 확장 팩\"}\n"
            "]\n"
            "```\n"
        ),
        responses={
            200: OpenApiResponse(
                response=StarterPackSerializer(many=True),
                description="스타터팩 메타 배열.",
            ),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
        },
        examples=[
            OpenApiExample(
                "스타터팩 목록",
                value=[
                    {"id": 1, "name": "기본 청소", "description": "신혼/1인 가구용 기본 팩"},
                    {"id": 2, "name": "패밀리", "description": "아이 있는 가정용 확장 팩"},
                ],
                response_only=True,
                status_codes=["200"],
            ),
            _AUTH_FAILED_EXAMPLE,
        ],
    )
    def get(self, request: Request) -> Response:
        packs = selectors.get_starter_packs()
        return Response(StarterPackSerializer(packs, many=True).data)


class StarterPackChoreListView(APIView):
    """특정 스타터팩의 집안일 목록."""

    @extend_schema(
        tags=["StarterPacks"],
        summary="스타터팩 집안일 목록 조회",
        description=(
            "## 🔥 설명\n"
            "지정한 스타터팩에 묶인 마스터 `Chore` 들을 반환한다. FE 는 이 응답을 사용자에게 보여주고, "
            "선택한 항목을 `HomeChoreCreate` 형식으로 변환해 `POST /homes/mine/chores/` 에 전달한다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `starter_pack_id` | integer | ✓ | 대상 StarterPack PK |\n\n"
            "## 📤 응답 (200)\n"
            "배열 응답.\n\n"
            "| 위치 | 필드 | 타입 | 설명 |\n"
            "| --- | --- | --- | --- |\n"
            "| body[*] | `id` | integer | 집안일 마스터 PK |\n"
            "| body[*] | `category` | integer | 카테고리 enum (1~5) |\n"
            "| body[*] | `category_label` | string | 카테고리 한글 |\n"
            "| body[*] | `name` | string | 집안일 제목 |\n"
            "| body[*] | `description` | string | 설명 |\n"
            "| body[*] | `repeat_days` | integer[] | 반복 요일 (0=월 ~ 6=일) |\n"
            "| body[*] | `repeat_days_label` | string[] | 요일 한글 |\n"
            "| body[*] | `difficulty` | integer | 난이도 enum (1~5) |\n"
            "| body[*] | `difficulty_label` | string | '쉬움'/'중간'/'어려움' |\n"
            "| body[*] | `point` | integer | 난이도 고정 포인트 |\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 401 | `authentication_failed` | access 토큰 누락/만료 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X GET '{host}/api/v1/starter-packs/1/chores/' \\\n"
            "     -H 'Authorization: Bearer <access>'\n"
            "```\n\n"
            "**응답 (200):**\n"
            "```json\n"
            "[\n"
            "  {\n"
            "    \"id\": 1, \"category\": 3, \"category_label\": \"청소\",\n"
            "    \"name\": \"거실 청소\", \"description\": \"주 1회\",\n"
            "    \"repeat_days\": [0, 3], \"repeat_days_label\": [\"월\", \"목\"],\n"
            "    \"difficulty\": 2, \"difficulty_label\": \"쉬움\", \"point\": 80\n"
            "  }\n"
            "]\n"
            "```\n"
        ),
        parameters=[
            OpenApiParameter(
                "starter_pack_id",
                int,
                OpenApiParameter.PATH,
                description="대상 `StarterPack` PK.",
            ),
        ],
        responses={
            200: OpenApiResponse(response=ChoreOutputSerializer(many=True), description="집안일 배열."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="access 토큰 누락/만료."),
        },
        examples=[
            OpenApiExample(
                "스타터팩 집안일 목록",
                value=[
                    {
                        "id": 1,
                        "category": 3,
                        "name": "거실 청소",
                        "description": "주 1회",
                        "repeat_days": [0, 3],
                        "repeat_days_label": ["월", "목"],
                        "difficulty": 2,
                        "difficulty_label": "쉬움",
                        "point": 80,
                    },
                    {
                        "id": 2,
                        "category": 5,
                        "name": "분리수거",
                        "description": "매주 화요일",
                        "repeat_days": [1],
                        "repeat_days_label": ["화"],
                        "difficulty": 3,
                        "difficulty_label": "중간",
                        "point": 120,
                    },
                ],
                response_only=True,
                status_codes=["200"],
            ),
            _AUTH_FAILED_EXAMPLE,
        ],
    )
    def get(self, request: Request, starter_pack_id: int) -> Response:
        chores = selectors.get_starter_pack_chores(starter_pack_id)
        return Response(ChoreOutputSerializer(chores, many=True).data)


# ── 분담안 (WeeklyAssignment) ─────────────────────────────────────────────────


def _serialize_assignment(assignment, *, assignee: str | None = None, request_user=None) -> dict:
    """분담안을 완료 여부 / 변경 감지 컨텍스트와 함께 직렬화합니다.

    변경 감지(`changes`)는 제안됨 상태에서만 의미가 있다 — 확정/만료 분담안은
    불변 히스토리이므로 원본이 바뀌어도 배지를 노출하지 않는다.

    `assignee` 가 주어지면 항목 목록만 해당 담당자로 좁힌다(`me` 또는 uid).
    `member_points` 는 화면의 "구성원 배정 포인트" 카드가 항상 전체를 보여주므로
    필터의 영향을 받지 않는다.
    """
    completed_keys = selectors.get_completed_item_keys(assignment)
    changes = (
        selectors.get_assignment_changes(assignment)
        if assignment.status == WeeklyAssignment.Status.PROPOSED
        else None
    )
    data = WeeklyAssignmentOutputSerializer(
        assignment,
        context={"completed_keys": completed_keys, "changes": changes},
    ).data

    if assignee:
        target_uid = str(request_user.uid) if assignee == "me" and request_user else assignee
        data["items"] = [
            item for item in data["items"]
            if item["assignee"] and item["assignee"]["uid"] == target_uid
        ]
    return data


# 분담안 응답 필드 표 — 조회/생성/재생성/확정 4개 엔드포인트가 동일 구조를 반환한다.
_ASSIGNMENT_OUTPUT_TABLE = (
    "| 위치 | 필드 | 타입 | 설명 |\n"
    "| --- | --- | --- | --- |\n"
    "| body | `id` | integer | 분담안 PK |\n"
    "| body | `week_start` | date | 적용 주차의 월요일 날짜 |\n"
    "| body | `status` | string | `proposed`(제안됨) / `confirmed`(확정됨) / `expired`(만료됨) |\n"
    "| body | `generated_at` | datetime | 분담안 생성(재생성) 시점 |\n"
    "| body | `confirmed_at` | datetime | 확정 시각 (미확정이면 null) |\n"
    "| body | `items[].id` | integer | 분담안 항목 PK (요일순 정렬) |\n"
    "| body | `items[].home_chore_id` | integer | 원본 집안일(HomeChore) PK — 원본 물리 삭제 시 null |\n"
    "| body | `items[].weekday` / `weekday_label` | integer / string | 실행 요일 (0=월 ~ 6=일) / 한글 라벨 |\n"
    "| body | `items[].chore_name` | string | 집안일명 (생성 시점 **스냅샷** — 이후 원본 수정에 불변) |\n"
    "| body | `items[].category` / `category_label` | integer / string | 카테고리 enum / 한글 (스냅샷) |\n"
    "| body | `items[].difficulty` / `difficulty_label` | integer / string | 난이도 enum / 3단계 라벨 (스냅샷) |\n"
    "| body | `items[].point` | integer | 포인트 (생성 시점 스냅샷) |\n"
    "| body | `items[].assignee` | object | 담당자 `{uid, name, profile_image}` — 탈퇴 시 null |\n"
    "| body | `items[].date` | date | 실행 날짜 (week_start + weekday) |\n"
    "| body | `items[].is_completed` | boolean | 완료 여부 (해당 날짜 ChoreCompletion 존재) |\n"
    "| body | `member_points[]` | array | 멤버별 예상 포인트 합계 `{uid, name, profile_image, expected_point}` |\n\n"
)

# 💻 예제 코드블록용 응답 JSON (항목 1건으로 축약)
_ASSIGNMENT_EXAMPLE_JSON = (
    "```json\n"
    "{\n"
    "  \"id\": 7,\n"
    "  \"week_start\": \"2026-07-13\",\n"
    "  \"status\": \"proposed\",\n"
    "  \"generated_at\": \"2026-07-12T21:05:00+09:00\",\n"
    "  \"confirmed_at\": null,\n"
    "  \"items\": [\n"
    "    {\n"
    "      \"id\": 31, \"home_chore_id\": 3,\n"
    "      \"weekday\": 0, \"weekday_label\": \"월\",\n"
    "      \"chore_name\": \"분리수거\", \"category\": 1, \"category_label\": \"쓰레기\",\n"
    "      \"difficulty\": 3, \"difficulty_label\": \"중간\", \"point\": 120,\n"
    "      \"assignee\": {\"uid\": \"8f3e…\", \"name\": \"김현수\", \"profile_image\": 2},\n"
    "      \"date\": \"2026-07-13\", \"is_completed\": false\n"
    "    }\n"
    "  ],\n"
    "  \"member_points\": [{\"uid\": \"8f3e…\", \"name\": \"김현수\", \"profile_image\": 2, \"expected_point\": 120}]\n"
    "}\n"
    "```\n"
)

# Swagger 응답 예시(OpenApiExample)용 값 — proposed 기본, 확정 뷰는 confirmed 변형 사용.
_ASSIGNMENT_EXAMPLE_VALUE = {
    "id": 7,
    "week_start": "2026-07-13",
    "status": "proposed",
    "generated_at": "2026-07-12T21:05:00+09:00",
    "confirmed_at": None,
    "items": [
        {
            "id": 31,
            "home_chore_id": 3,
            "weekday": 0,
            "weekday_label": "월",
            "chore_name": "분리수거",
            "category": 1,
            "category_label": "쓰레기",
            "difficulty": 3,
            "difficulty_label": "중간",
            "point": 120,
            "assignee": {"uid": "8f3e2b1a-1234-4abc-9def-1234567890ab", "name": "김현수", "profile_image": 2},
            "date": "2026-07-13",
            "is_completed": False,
        },
        {
            "id": 32,
            "home_chore_id": 4,
            "weekday": 5,
            "weekday_label": "토",
            "chore_name": "화장실 청소",
            "category": 2,
            "category_label": "욕실",
            "difficulty": 4,
            "difficulty_label": "중간",
            "point": 160,
            "assignee": {"uid": "1a2b3c4d-5678-4abc-9def-abcdef123456", "name": "김수환", "profile_image": 5},
            "date": "2026-07-18",
            "is_completed": False,
        },
    ],
    "member_points": [
        {"uid": "1a2b3c4d-5678-4abc-9def-abcdef123456", "name": "김수환", "profile_image": 5, "expected_point": 160},
        {"uid": "8f3e2b1a-1234-4abc-9def-1234567890ab", "name": "김현수", "profile_image": 2, "expected_point": 120},
    ],
}

_ASSIGNMENT_CONFIRMED_EXAMPLE_VALUE = {
    **_ASSIGNMENT_EXAMPLE_VALUE,
    "status": "confirmed",
    "confirmed_at": "2026-07-12T22:10:00+09:00",
}


class HomeAssignmentView(APIView):
    """분담안 조회(모든 구성원) / 수동 생성(관리자 전용).

    상태·정책은 specs/assignments.md 참조. 생성/재생성/확정 권한은 관리자에게만
    있으며, 조회는 모든 구성원이 가능하다.
    """

    @extend_schema(
        tags=["Homes"],
        summary="내 집 분담안 조회 (주차별)",
        description=(
            "## 🔥 설명\n"
            "내 집의 특정 주차 분담안을 조회한다. `week_start` 생략 시 **이번 주차** "
            "(분담안 탭의 기본 진입 탭이 `이번 주`). 모든 구성원이 조회 가능하다. "
            "항목의 집안일명/난이도/포인트는 분담안 생성 시점 스냅샷이다.\n\n"
            "제안됨(proposed) 상태에서는 생성 이후 집안일 변경을 `changes` 와 항목별 "
            "`change_type` 으로 함께 내려준다 (화면의 NEW / UPDATE 배지).\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| query | `week_start` | date |  | 조회할 주차의 월요일 (YYYY-MM-DD). 생략 시 이번 주차 |\n"
            "| query | `assignee` | string |  | 항목 담당자 필터 — `me` 또는 구성원 uid. 생략 시 전체 |\n\n"
            "## 📤 응답 (200)\n"
            + _ASSIGNMENT_OUTPUT_TABLE
            + "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 400 | `invalid` | week_start 가 월요일이 아님 |\n"
            "| 401 | `authentication_failed` | 토큰 누락/만료 |\n"
            "| 404 | `not_found` | 속한 집 없음 / 해당 주차 분담안 없음 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X GET '{host}/api/v1/homes/mine/assignments/?week_start=2026-07-13' \\\n"
            "     -H 'Authorization: Bearer <access>'\n"
            "```\n\n"
            "**응답 (200):**\n"
            + _ASSIGNMENT_EXAMPLE_JSON
        ),
        parameters=[
            OpenApiParameter(
                name="week_start", type=str, description="조회할 주차의 월요일 날짜 (YYYY-MM-DD). 생략 시 다음 주차."
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=WeeklyAssignmentOutputSerializer, description="분담안 (항목 + 멤버별 예상 포인트)."
            ),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="week_start 형식/요일 오류."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="속한 집 없음 / 분담안 없음."),
        },
        examples=[
            OpenApiExample(
                "분담안 (proposed)",
                value=_ASSIGNMENT_EXAMPLE_VALUE,
                response_only=True,
                status_codes=["200"],
            ),
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="해당 주차의 분담안이 없습니다.", name="분담안 없음"),
        ],
    )
    def get(self, request: Request) -> Response:
        query = AssignmentWeekQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)

        home = selectors.get_user_home(request.user)
        if home is None:
            raise NotFound("속한 집이 없습니다.")

        week_start = query.validated_data.get("week_start") or services.week_start_of(
            timezone.localdate()
        )
        assignment = selectors.get_week_assignment(home, week_start)
        if assignment is None:
            raise NotFound("해당 주차의 분담안이 없습니다.")

        return Response(
            _serialize_assignment(
                assignment,
                assignee=query.validated_data.get("assignee"),
                request_user=request.user,
            )
        )

    @extend_schema(
        tags=["Homes"],
        summary="분담안 수동 생성 (관리자 전용)",
        description=(
            "## 🔥 설명\n"
            "분담안을 수동 생성한다. **관리자 전용**. `week_start` 생략 시 다음 주차, 과거 주차 불가. "
            "수동 생성된 주차는 일요일 자동 생성에서 스킵된다.\n\n"
            "배정: 활성 집안일 × 반복 요일을 펼쳐 멤버별 예상 포인트 총합이 균등하도록 배정한다 "
            "(동점 시 최근 3주 기여도 낮은 멤버 우선). 활성 집안일 3개 이상 필요.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수. **관리자만** 호출 가능 (구성원은 403).\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| body | `week_start` | date |  | 대상 주차의 월요일 (YYYY-MM-DD). 생략 시 다음 주차. 과거 불가 |\n\n"
            "## 📤 응답 (201)\n"
            + _ASSIGNMENT_OUTPUT_TABLE
            + "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 400 | `invalid_week_start` | 월요일 아님 / 과거 주차 |\n"
            "| 400 | `assignment_already_exists` | 해당 주차 분담안 이미 존재 |\n"
            "| 400 | `not_enough_chores` | 활성 집안일 3개 미만 |\n"
            "| 403 | `permission_denied` | 관리자 아님 |\n"
            "| 404 | `not_found` | 속한 집 없음 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X POST '{host}/api/v1/homes/mine/assignments/' \\\n"
            "     -H 'Authorization: Bearer <access>' \\\n"
            "     -H 'Content-Type: application/json' \\\n"
            "     -d '{\"week_start\": \"2026-07-13\"}'\n"
            "```\n\n"
            "**응답 (201):**\n"
            + _ASSIGNMENT_EXAMPLE_JSON
        ),
        request=AssignmentCreateSerializer,
        responses={
            201: OpenApiResponse(response=WeeklyAssignmentOutputSerializer, description="생성된 분담안 (proposed)."),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="주차 오류 / 중복 / 집안일 부족."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="관리자 아님."),
        },
        examples=[
            OpenApiExample(
                "생성된 분담안 (proposed)",
                value=_ASSIGNMENT_EXAMPLE_VALUE,
                response_only=True,
                status_codes=["201"],
            ),
            _AUTH_FAILED_EXAMPLE,
            error_example(
                code="not_enough_chores",
                message="분담안을 만들려면 활성 집안일이 3개 이상이어야 합니다.",
                name="집안일 부족",
            ),
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = AssignmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            assignment = services.generate_assignment(user=request.user, **serializer.validated_data)
        except services.NotHomeAdminError as e:
            raise PermissionDenied(str(e)) from e
        except services.AssignmentStateError as e:
            raise ValidationError({e.code: str(e)}) from e

        return Response(_serialize_assignment(assignment), status=status.HTTP_201_CREATED)


class HomeAssignmentRegenerateView(APIView):
    """분담안 재생성 (관리자 전용, proposed 상태만)."""

    @extend_schema(
        tags=["Homes"],
        summary="분담안 재생성 (관리자 전용, proposed 만)",
        description=(
            "## 🔥 설명\n"
            "proposed 상태의 분담안을 폐기하고 최신 원본(집안일/구성원) 기준으로 새 분담안을 생성한다. "
            "**관리자 전용**. confirmed 상태는 재생성 불가. 동점 배정에 무작위성이 있어 동일 결과 반복을 피한다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수. **관리자만** 호출 가능 (구성원은 403).\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `assignment_id` | integer | ✓ | 재생성할 분담안 PK (proposed 상태) |\n\n"
            "요청 본문 없음.\n\n"
            "## 📤 응답 (201)\n"
            "기존 분담안은 폐기되고 **새 PK 의 분담안**이 반환된다.\n\n"
            + _ASSIGNMENT_OUTPUT_TABLE
            + "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 400 | `not_proposed` | proposed 상태가 아님 |\n"
            "| 400 | `not_enough_chores` | 활성 집안일 3개 미만 |\n"
            "| 403 | `permission_denied` | 관리자 아님 |\n"
            "| 404 | `not_found` | 분담안 없음/다른 집 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X POST '{host}/api/v1/homes/mine/assignments/7/regenerate/' \\\n"
            "     -H 'Authorization: Bearer <access>'\n"
            "```\n\n"
            "**응답 (201):**\n"
            + _ASSIGNMENT_EXAMPLE_JSON
        ),
        request=None,
        responses={
            201: OpenApiResponse(response=WeeklyAssignmentOutputSerializer, description="재생성된 분담안 (proposed)."),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="상태/집안일 수 조건 위반."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="관리자 아님."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="분담안 없음."),
        },
        examples=[
            OpenApiExample(
                "재생성된 분담안 (proposed)",
                value=_ASSIGNMENT_EXAMPLE_VALUE,
                response_only=True,
                status_codes=["201"],
            ),
            _AUTH_FAILED_EXAMPLE,
            error_example(
                code="not_proposed", message="제안됨 상태의 분담안만 재생성할 수 있습니다.", name="상태 오류"
            ),
        ],
    )
    def post(self, request: Request, assignment_id: int) -> Response:
        try:
            assignment = services.regenerate_assignment(user=request.user, assignment_id=assignment_id)
        except services.NotHomeAdminError as e:
            raise PermissionDenied(str(e)) from e
        except services.AssignmentNotFoundError as e:
            raise NotFound(str(e)) from e
        except services.AssignmentStateError as e:
            raise ValidationError({e.code: str(e)}) from e

        return Response(_serialize_assignment(assignment), status=status.HTTP_201_CREATED)


class HomeAssignmentConfirmView(APIView):
    """분담안 확정 (관리자 전용, 확정 조건 검증)."""

    @extend_schema(
        tags=["Homes"],
        summary="분담안 확정 (관리자 전용)",
        description=(
            "## 🔥 설명\n"
            "proposed 분담안을 확정한다. **관리자 전용**. 확정된 분담안은 수정/삭제/재생성이 불가하다.\n\n"
            "확정 조건: proposed 상태 / 같은 주차 확정본 없음 / 구성원 1명 이상 / "
            "생성 시점 이후 **집안일 변경 없음** / **활성 집안일 3개 이상** / **구성원 변화 없음**. "
            "뒤의 3개 조건 위반 시 409 를 반환하며, 재생성 후 다시 확정해야 한다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수. **관리자만** 호출 가능 (구성원은 403).\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `assignment_id` | integer | ✓ | 확정할 분담안 PK (proposed 상태) |\n\n"
            "요청 본문 없음.\n\n"
            "## 📤 응답 (200)\n"
            "`status` 가 `confirmed` 로 전이되고 `confirmed_at` 이 채워진다.\n\n"
            + _ASSIGNMENT_OUTPUT_TABLE
            + "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 400 | `not_proposed` | proposed 상태가 아님 |\n"
            "| 400 | `already_confirmed_week` | 같은 주차에 확정본 존재 |\n"
            "| 403 | `permission_denied` | 관리자 아님 |\n"
            "| 404 | `not_found` | 분담안 없음/다른 집 |\n"
            "| 409 | `chores_changed` | 생성 이후 집안일 변경 감지 — 재생성 필요 |\n"
            "| 409 | `members_changed` | 생성 이후 구성원 변화 감지 — 재생성 필요 |\n"
            "| 409 | `not_enough_chores` | 활성 집안일 3개 미만 — 재생성 필요 |\n\n"
            "## 💻 예제\n"
            "**요청:**\n"
            "```bash\n"
            "curl -X POST '{host}/api/v1/homes/mine/assignments/7/confirm/' \\\n"
            "     -H 'Authorization: Bearer <access>'\n"
            "```\n\n"
            "**응답 (200):** 위 분담안 응답 구조와 동일하되 `status: \"confirmed\"`, `confirmed_at` 채워짐.\n"
        ),
        request=None,
        responses={
            200: OpenApiResponse(response=WeeklyAssignmentOutputSerializer, description="확정된 분담안 (confirmed)."),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="상태 조건 위반."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="관리자 아님."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="분담안 없음."),
            409: OpenApiResponse(response=ErrorResponseSerializer, description="생성 이후 변경 감지 — 재생성 필요."),
        },
        examples=[
            OpenApiExample(
                "확정된 분담안 (confirmed)",
                value=_ASSIGNMENT_CONFIRMED_EXAMPLE_VALUE,
                response_only=True,
                status_codes=["200"],
            ),
            _AUTH_FAILED_EXAMPLE,
            error_example(
                code="chores_changed",
                message="분담안 생성 이후 집안일이 변경되었습니다. 분담안을 재생성해 주세요.",
                name="집안일 변경 감지",
            ),
        ],
    )
    def post(self, request: Request, assignment_id: int) -> Response:
        try:
            assignment = services.confirm_assignment(user=request.user, assignment_id=assignment_id)
        except services.NotHomeAdminError as e:
            raise PermissionDenied(str(e)) from e
        except services.AssignmentNotFoundError as e:
            raise NotFound(str(e)) from e
        except services.AssignmentConflictError as e:
            raise Conflict({e.code: str(e)}) from e
        except services.AssignmentStateError as e:
            raise ValidationError({e.code: str(e)}) from e

        return Response(_serialize_assignment(assignment))


# ── 집안일 완료 처리 ─────────────────────────────────────────────────────────


class HomeChoreCompletionView(APIView):
    """집안일 완료 처리 (담당자 전용).

    완료 여부는 별도 컬럼 없이 `ChoreCompletion(home_chore, date)` 로 기록되며,
    분담안 항목의 `is_completed` / 대시보드 진행률 / 기여도 / MVP 가 모두 이
    테이블을 근거로 계산된다.
    """

    @extend_schema(
        tags=["Homes"],
        summary="집안일 완료 처리 (담당자 전용)",
        description=(
            "## 🔥 설명\n"
            "확정된 분담안에서 **본인에게 배정된** 집안일을 완료 처리한다. "
            "같은 (집안일, 날짜) 조합은 1건만 기록되며 중복 요청은 409 로 차단된다.\n\n"
            "완료 처리 후 진행률·기여도·MVP·리포트·리워드 포인트에 즉시 반영된다. "
            "화면 스낵바용으로 획득 포인트(`point`)를 함께 반환한다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수. **해당 항목의 담당자만** 호출 가능 (그 외 403).\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `home_chore_id` | integer | ✓ | 대상 HomeChore PK |\n"
            "| body | `date` | date | - | 완료 기준 날짜. 생략 시 오늘 |\n\n"
            "## 📤 응답 (201)\n"
            "| 위치 | 필드 | 타입 | 설명 |\n"
            "| --- | --- | --- | --- |\n"
            "| body | `id` | integer | 완료 이력 PK |\n"
            "| body | `home_chore_id` | integer | 완료된 집안일 PK |\n"
            "| body | `date` | date | 완료 기준 날짜 |\n"
            "| body | `point` | integer | 획득 포인트 (분담안 스냅샷) |\n"
            "| body | `completed_by` | object | 완료자 `{uid, name, profile_image}` |\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 400 | `assignment_not_confirmed` | 해당 주차에 확정된 분담안이 없음 |\n"
            "| 400 | `not_assigned_on_date` | 그 날짜에 배정되지 않은 집안일 |\n"
            "| 403 | `not_assignee` | 담당자가 아님 |\n"
            "| 404 | `not_found` | 본인 집의 활성 집안일이 아님 |\n"
            "| 409 | `already_completed` | 이미 완료 처리됨 |\n"
        ),
        request=ChoreCompletionCreateSerializer,
        responses={
            201: ChoreCompletionOutputSerializer,
            400: OpenApiResponse(response=ErrorResponseSerializer, description="확정 분담안 없음 / 미배정 날짜."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="담당자가 아님."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="집안일 미존재."),
            409: OpenApiResponse(response=ErrorResponseSerializer, description="이미 완료 처리됨."),
        },
        examples=[
            OpenApiExample("오늘 완료", value={}, request_only=True),
            OpenApiExample("특정 날짜 완료", value={"date": "2026-07-15"}, request_only=True),
            OpenApiExample(
                "완료 성공",
                value={
                    "id": 12,
                    "home_chore_id": 3,
                    "date": "2026-07-15",
                    "point": 120,
                    "completed_by": {
                        "uid": "8f3e2b1a-1234-4abc-9def-1234567890ab",
                        "name": "김현수",
                        "profile_image": 2,
                    },
                },
                response_only=True,
                status_codes=["201"],
            ),
            _AUTH_FAILED_EXAMPLE,
            error_example(
                code="assignment_not_confirmed",
                message="확정된 분담안이 없어 완료 처리할 수 없습니다.",
                name="확정 분담안 없음",
            ),
            error_example(
                code="not_assigned_on_date",
                message="해당 날짜에 배정된 집안일이 아닙니다.",
                name="미배정 날짜",
            ),
            error_example(code="not_assignee", message="담당자만 완료 처리할 수 있습니다.", name="담당자 아님"),
            error_example(code="not_found", message="집안일을 찾을 수 없습니다.", name="집안일 미존재"),
            error_example(code="already_completed", message="이미 완료 처리된 집안일입니다.", name="중복 완료"),
        ],
    )
    def post(self, request: Request, home_chore_id: int) -> Response:
        serializer = ChoreCompletionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            completion = services.complete_chore(
                user=request.user,
                home_chore_id=home_chore_id,
                target_date=serializer.validated_data.get("date"),
            )
        except services.HomeChoreNotFoundError as e:
            raise NotFound(str(e)) from e
        except services.NotChoreAssigneeError as e:
            raise PermissionDenied({e.code: str(e)}) from e
        except services.ChoreAlreadyCompletedError as e:
            raise Conflict({e.code: str(e)}) from e
        except services.ChoreCompletionError as e:
            raise ValidationError({e.code: str(e)}) from e

        return Response(
            _serialize_completion(completion),
            status=status.HTTP_201_CREATED,
        )


class HomeChoreCompletionDetailView(APIView):
    """집안일 완료 처리 취소 (스낵바 "실행 취소")."""

    @extend_schema(
        tags=["Homes"],
        summary="집안일 완료 취소 (완료한 본인 전용)",
        description=(
            "## 🔥 설명\n"
            "완료 처리를 되돌린다. 완료 직후 스낵바의 **실행 취소**에 대응한다. "
            "완료를 기록한 본인만 취소할 수 있다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수. **완료를 기록한 본인만** 호출 가능 (그 외 403).\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `home_chore_id` | integer | ✓ | 대상 HomeChore PK |\n"
            "| path | `completion_date` | date | ✓ | 취소할 완료 이력의 날짜 (YYYY-MM-DD) |\n\n"
            "## 📤 응답 (204)\n"
            "본문 없음.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 403 | `not_assignee` | 완료를 기록한 본인이 아님 |\n"
            "| 404 | `not_found` | 집안일 또는 완료 이력 미존재 |\n"
        ),
        responses={
            204: OpenApiResponse(description="취소 완료 (본문 없음)."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="완료자 본인이 아님."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="집안일 또는 완료 이력 미존재."),
        },
        examples=[
            _AUTH_FAILED_EXAMPLE,
            error_example(
                code="not_assignee",
                message="완료 처리한 본인만 취소할 수 있습니다.",
                name="완료자 아님",
            ),
            error_example(code="not_found", message="완료 이력을 찾을 수 없습니다.", name="완료 이력 미존재"),
        ],
    )
    def delete(self, request: Request, home_chore_id: int, completion_date: str) -> Response:
        try:
            parsed = date.fromisoformat(completion_date)
        except ValueError as e:
            raise ValidationError({"invalid": "날짜 형식이 올바르지 않습니다 (YYYY-MM-DD)."}) from e

        try:
            services.uncomplete_chore(
                user=request.user,
                home_chore_id=home_chore_id,
                target_date=parsed,
            )
        except services.HomeChoreNotFoundError as e:
            raise NotFound(str(e)) from e
        except services.ChoreCompletionNotFoundError as e:
            raise NotFound(str(e)) from e
        except services.NotChoreAssigneeError as e:
            raise PermissionDenied({e.code: str(e)}) from e

        return Response(status=status.HTTP_204_NO_CONTENT)


def _serialize_completion(completion) -> dict:
    """완료 이력을 응답 dict 로 변환합니다 (획득 포인트 포함)."""
    return {
        "id": completion.id,
        "home_chore_id": completion.home_chore_id,
        "date": completion.date,
        "point": getattr(completion, "earned_point", 0),
        "completed_by": {
            "uid": str(completion.completed_by.uid),
            "name": completion.completed_by.name,
            "profile_image": completion.completed_by.profile_image,
        },
    }


# ── 홈 대시보드 ──────────────────────────────────────────────────────────────


class HomeDashboardView(APIView):
    """홈 대시보드(T1_HomeDashboard) 집계 조회."""

    @extend_schema(
        tags=["Homes"],
        summary="홈 대시보드 집계 조회",
        description=(
            "## 🔥 설명\n"
            "홈 탭 상단을 한 번에 그리기 위한 집계 응답. 이번 주 진행률, 내 기여도, 우리집 MVP, "
            "다음 주 분담안 상태 라벨, 이번 주 항목 목록(멤버 필터 탭용)을 함께 반환한다.\n\n"
            "- **진행률** = 완료 항목 수 / 전체 항목 수\n"
            "- **기여도** = 내가 완료한 포인트 / 집 전체 완료 포인트 (배정 담당자가 아니라 **실제 완료자** 기준)\n"
            "- **MVP** = 완료 포인트 최고 구성원 (동점이면 완료 건수 우선)\n"
            "- `next_week.status` 가 null 이면 화면은 '생성 필요' + 레드닷으로 표시한다\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📤 응답 (200)\n"
            "| 위치 | 필드 | 타입 | 설명 |\n"
            "| --- | --- | --- | --- |\n"
            "| body | `home` | object | `{id, name, image, member_count}` |\n"
            "| body | `this_week.week_start` | date | 이번 주 월요일 |\n"
            "| body | `this_week.status` | string | 분담안 상태. 없으면 null |\n"
            "| body | `this_week.completed_count` / `total_count` | integer | 완료 / 전체 항목 수 |\n"
            "| body | `this_week.progress_rate` | integer | 진행률 % |\n"
            "| body | `this_week.my_contribution_rate` | integer | 내 기여도 % |\n"
            "| body | `this_week.mvp` | object | `{uid, name, profile_image, point, completed_count}` 또는 null |\n"
            "| body | `next_week.status` | string | `proposed` / `confirmed` / null(생성 필요) |\n"
            "| body | `items[]` | array | 이번 주 분담안 항목 (분담안 없으면 빈 배열) |\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 404 | `not_found` | 속한 집이 없음 |\n"
        ),
        responses={
            200: HomeDashboardOutputSerializer,
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="속한 집이 없음."),
        },
        examples=[
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="속한 집이 없습니다.", name="집 미존재"),
        ],
    )
    def get(self, request: Request) -> Response:
        dashboard = selectors.get_home_dashboard(user=request.user)
        if dashboard is None:
            raise NotFound("속한 집이 없습니다.")

        assignment = dashboard.pop("assignment")
        if assignment is None:
            dashboard["items"] = []
        else:
            completed_keys = selectors.get_completed_item_keys(assignment)
            dashboard["items"] = AssignmentItemOutputSerializer(
                assignment.items.all(),
                many=True,
                context={"completed_keys": completed_keys},
            ).data

        return Response(dashboard)


# ── 분담안 히스토리 ──────────────────────────────────────────────────────────


class HomeAssignmentHistoryView(APIView):
    """과거 주차 분담안 히스토리 조회 (모든 구성원)."""

    @extend_schema(
        tags=["Homes"],
        summary="분담안 히스토리 조회 (최대 4주 전)",
        description=(
            "## 🔥 설명\n"
            "분담안 탭의 `히스토리` 화면(T3C_PlanHistory) 용. 주차 셀렉터 목록(`weeks`)과 "
            "선택된 주차의 분담안(`selected`)을 한 번에 반환한다. **최대 4주 전까지** 조회할 수 있고, "
            "기본 선택은 지난 주(`weeks_ago=1`)다.\n\n"
            "분담안이 없는 주차는 `assignment_id` 와 `selected` 가 null 이며, 화면은 "
            "\"해당 주차의 분담안 기록이 없어요\" 를 노출한다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수. 모든 구성원 조회 가능.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| query | `weeks_ago` | integer |  | 1(지난 주) ~ 4(4주 전). 생략 시 1 |\n\n"
            "## 📤 응답 (200)\n"
            "| 위치 | 필드 | 타입 | 설명 |\n"
            "| --- | --- | --- | --- |\n"
            "| body | `weeks[].week_start` | date | 해당 주차의 월요일 |\n"
            "| body | `weeks[].weeks_ago` | integer | 1 ~ 4 |\n"
            "| body | `weeks[].assignment_id` | integer | 분담안 PK. 없으면 null |\n"
            "| body | `weeks[].status` | string | confirmed / expired / proposed. 없으면 null |\n"
            "| body | `selected` | object | 선택 주차의 분담안 (조회 응답과 동일 구조). 없으면 null |\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 400 | `invalid` | `weeks_ago` 가 1~4 범위 밖 |\n"
            "| 404 | `not_found` | 속한 집이 없음 |\n"
        ),
        parameters=[
            OpenApiParameter(
                name="weeks_ago",
                type=int,
                required=False,
                description="조회할 과거 주차 (1=지난 주 ~ 4=4주 전). 생략 시 1.",
            ),
        ],
        responses={
            200: AssignmentHistoryOutputSerializer,
            400: OpenApiResponse(response=ErrorResponseSerializer, description="weeks_ago 범위 오류."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="속한 집이 없음."),
        },
        examples=[
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="속한 집이 없습니다.", name="집 미존재"),
        ],
    )
    def get(self, request: Request) -> Response:
        query = AssignmentHistoryQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)

        home = selectors.get_user_home(request.user)
        if home is None:
            raise NotFound("속한 집이 없습니다.")

        history = selectors.get_assignment_history(
            home=home, weeks_ago=query.validated_data["weeks_ago"]
        )
        selected = history["selected"]
        return Response({
            "weeks": history["weeks"],
            "selected": _serialize_assignment(selected) if selected else None,
        })


# ── 집안일 삭제 복구 ─────────────────────────────────────────────────────────


class HomeChoreRestoreView(APIView):
    """비활성화된 집안일 복구 (삭제 스낵바의 "실행 취소")."""

    @extend_schema(
        tags=["Homes"],
        summary="집안일 삭제 복구 (실행 취소)",
        description=(
            "## 🔥 설명\n"
            "`DELETE /homes/mine/chores/{id}/` 로 비활성화(soft-delete)된 집안일을 다시 활성화한다. "
            "삭제 직후 노출되는 스낵바의 **실행 취소**에 대응한다. 같은 집 구성원이면 누구나 호출할 수 있다.\n\n"
            "완료·분담안 이력이 전혀 없어 **물리 삭제**된 집안일은 복구할 수 없다 (404).\n"
            "이미 활성 상태면 그대로 200 을 반환한다 (멱등).\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `home_chore_id` | integer | ✓ | 복구할 HomeChore PK |\n\n"
            "## 📤 응답 (200)\n"
            "복구된 집안일 (집안일 목록 응답과 동일 구조, `is_active=true`).\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 404 | `not_found` | 본인 집의 집안일이 아니거나 물리 삭제됨 |\n"
        ),
        request=None,
        responses={
            200: HomeChoreOutputSerializer,
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="집안일 미존재."),
        },
        examples=[
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="집안일을 찾을 수 없습니다.", name="집안일 미존재"),
        ],
    )
    def post(self, request: Request, home_chore_id: int) -> Response:
        try:
            home_chore = services.restore_home_chore(user=request.user, home_chore_id=home_chore_id)
        except services.HomeChoreNotFoundError as e:
            raise NotFound(str(e)) from e

        return Response(HomeChoreOutputSerializer(home_chore).data)

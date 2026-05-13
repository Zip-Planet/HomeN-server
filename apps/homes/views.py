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

from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.homes import selectors, services
from apps.homes.serializers import (
    ChoreOutputSerializer,
    HomeChoreListCreateSerializer,
    HomeChoreNoteCreateSerializer,
    HomeChoreNoteOutputSerializer,
    HomeChoreNoteUpdateSerializer,
    HomeChoreOutputSerializer,
    HomeChoreUpdateSerializer,
    HomeCreateSerializer,
    HomeInviteDetailSerializer,
    HomeJoinSerializer,
    HomeMembershipSerializer,
    HomeOutputSerializer,
    ImageIdSerializer,
    StarterPackSerializer,
    TransferAdminSerializer,
)
from common.error_responses import ErrorResponseSerializer, error_example


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
        summary="내 집의 집안일 목록 조회",
        description=(
            "## 🔥 설명\n"
            "현재 유저가 속한 집의 집안일을 PK 오름차순으로 반환한다. 비어 있는 집은 200 + `[]`. 다른 집의 "
            "집안일은 노출되지 않는다.\n\n"
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
    수정/삭제는 구성원 누구나 가능하며, 스타터팩 chore 수정은 copy-on-write 로
    본인 집 전용 사본을 만들어 프리셋 데이터를 보존한다.
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
        "| body | `point` | integer | 난이도 고정 포인트: 40/80/120/160/200 |\n\n"
    )

    @extend_schema(
        tags=["Homes"],
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
            + "## ❌ 에러\n"
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
            "  \"difficulty\": 2, \"difficulty_label\": \"쉬움\", \"point\": 80\n"
            "}\n"
            "```\n"
        ),
        responses={
            200: OpenApiResponse(response=HomeChoreOutputSerializer, description="조회 성공."),
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
        return Response(HomeChoreOutputSerializer(home_chore).data)

    @extend_schema(
        tags=["Homes"],
        summary="내 집 집안일 부분 수정 (PATCH)",
        description=(
            "## 🔥 설명\n"
            "본인 집의 집안일 메타를 부분 수정한다. **구성원 누구나** 호출 가능. 모든 필드는 optional 이며 "
            "전달된 키만 적용된다. 스타터팩에서 비롯된 chore 는 **copy-on-write** — 프리셋 Chore 는 보존되고 "
            "본인 집 전용 사본이 새로 생성되어 `HomeChore.chore` 가 교체된다(응답의 `id` 는 그대로).\n\n"
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
        summary="내 집 집안일 삭제 (구성원 누구나, 링크 해제)",
        description=(
            "## 🔥 설명\n"
            "본인 집에서 해당 집안일 연결을 제거한다. **구성원 누구나** 호출 가능. 원본 `Chore` 는 보존되며, "
            "스타터팩 chore 의 경우 다른 집에서 살아있는 연결에 영향을 주지 않는다.\n\n"
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

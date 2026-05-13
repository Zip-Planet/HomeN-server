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
            "선택 가능한 집 이미지 enum 정수 목록을 반환한다.\n"
            "FE 는 응답의 `id` 를 그대로 `HomeCreate.image_id` 로 전송한다."
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
            "집을 생성하고 호출자를 관리자로 자동 등록한다. 집안일은 **스타터팩 ID 또는 커스텀 배열 중 하나** 만 받으며, 둘 다 비어 있어도 된다 (집만 생성).\n\n"
            "**검증**\n"
            "- 이름: 한글·영문·숫자·공백, 1~10자. 공백 단독 불가.\n"
            "- `image_id`: `HomeImageType` choice 정수 (1~8) 중 하나.\n"
            "- `starter_pack_id`: 스타터팩 PK (선택). 지정 시 해당 팩의 chore 가 일괄 연결.\n"
            "- `chores`: 사용자 정의 집안일 배열. `starter_pack_id` 와 동시 지정 불가.\n"
            "- `rewards`: 빈 배열이면 부속 생성을 건너뛴다 (집안일 입력과 독립).\n\n"
            "**에러**\n"
            "- 400 `already_has_home`: 이미 다른 집에 속해 있음 (먼저 나가야 함).\n"
            "- 400 `ambiguous_chore_input`: `starter_pack_id` 와 `chores` 동시 지정.\n"
            "- 404: `starter_pack_id` 에 해당하는 chore 가 없음.\n"
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
            "현재 유저가 속한 집의 상세 정보를 반환한다.\n"
            "속한 집이 없으면 404 (`NotFound`) — `has_home` 만 확인하려면 `/homes/mine/membership/` 사용."
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
            "본인이 관리자인 집을 삭제한다.\n\n"
            "**선결 조건**\n"
            "- 호출자가 해당 집의 **관리자** 여야 한다 (구성원은 403).\n"
            "- 구성원이 0명이어야 한다 (남아있으면 400 `home_has_members`).\n"
            "  → 구성원이 있으면 양도 후 탈퇴하거나, 구성원들이 모두 나간 뒤에 삭제 가능.\n"
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
            "현재 유저의 집 소속 여부를 반환한다.\n"
            "속한 집이 없어도 404 가 아닌 200 + `{ \"has_home\": false }` 를 반환한다."
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
            "초대코드로 집을 조회해 이름/이미지/구성원 등 미리보기 정보를 반환한다.\n"
            "**유의**: 본 호출만으로 집에 참여되지는 않으며, 확정은 `POST /homes/join/` 으로 한다."
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
            "초대코드 검증 후 호출자를 해당 집의 **구성원**(`Role.MEMBER`)으로 등록한다.\n\n"
            "**에러**\n"
            "- 400 `already_has_home`: 이미 다른 집에 속해 있음.\n"
            "- 404: 유효하지 않은 초대코드.\n"
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
            "현재 유저가 집을 나간다.\n\n"
            "**제약**\n"
            "- 관리자는 본 엔드포인트로 직접 나갈 수 없다 (403).\n"
            "  → 먼저 `/homes/mine/transfer-admin/` 으로 양도하거나, 단독이라면 `/homes/mine/` 을 삭제.\n"
            "- 속한 집이 없으면 404.\n"
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
            "집 관리자 권한을 같은 집의 구성원에게 양도한다.\n\n"
            "**검증**\n"
            "- 호출자가 해당 집의 **관리자** 여야 한다 (구성원은 403).\n"
            "- 대상 `user_id` 는 같은 집의 구성원이어야 한다 (위반 시 400 `transfer_admin_target`).\n"
            "- 본인에게 양도는 불가 (서비스 레이어가 거절).\n"
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
            "현재 유저가 속한 집의 집안일을 PK 오름차순으로 반환한다.\n\n"
            "- 비어 있는 집(아직 집안일을 추가하지 않은 집) 도 200 + 빈 배열로 응답한다.\n"
            "- 응답 형식은 `POST` 응답의 단일 원소와 동일 (`HomeChoreOutputSerializer`).\n"
            "  난이도 3단계 라벨/포인트/요일 한글 라벨 포함.\n"
            "- 다른 집의 집안일은 노출되지 않는다.\n"
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
            "현재 유저의 집에 집안일을 추가한다. 입력은 다음 둘 중 정확히 하나:\n\n"
            "- `starter_pack_id`: 스타터팩의 chore 일괄 연결. 동일 (home, chore) 가 이미 있으면 skip — 멱등.\n"
            "- `chores`: 사용자 정의 chore 배열. 단건도 길이 1 배열로.\n\n"
            "- 응답은 새로 생성된 `HomeChore` 의 배열 (스타터팩 적용 시 skip 된 항목은 제외).\n"
            "- 같은 마스터 `Chore` 가 같은 집에 중복 배정되지 않도록 unique 제약이 있다.\n"
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
            "지정한 집안일의 메모 목록을 PK 오름차순으로 반환한다.\n\n"
            "- 본인 집의 집안일이 아니면 404.\n"
            "- 메모 0개여도 200 + 빈 배열.\n"
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
            "지정한 집안일에 메모를 새로 작성한다.\n\n"
            "- 작성자(`author`) 는 호출자로 자동 설정.\n"
            "- 본인 집의 집안일이 아니면 404.\n"
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
            "지정한 메모의 본문을 변경한다. **본인이 작성한 메모만** 수정 가능 (위반 시 403).\n"
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
        description="**본인이 작성한 메모만** 삭제 가능 (위반 시 403).",
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
            "사전 등록된 스타터팩(집안일 프리셋 묶음) 의 메타 정보 배열을 반환한다.\n"
            "집안일 상세는 `/starter-packs/{id}/chores/` 로 별도 조회한다."
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
            "지정한 스타터팩에 묶인 마스터 `Chore` 들을 반환한다.\n"
            "FE 는 이 응답을 사용자에게 보여주고, 선택한 항목들을 `HomeChoreCreate` 형식으로 변환해\n"
            "`POST /homes/mine/chores/` 에 전달한다."
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

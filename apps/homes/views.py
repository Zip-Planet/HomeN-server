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
    ChoreMemoUpdateSerializer,
    HomeChoreListCreateSerializer,
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
            "집을 생성하고 호출자를 관리자로 자동 등록한다. 집안일과 리워드를 함께 등록할 수 있다.\n\n"
            "**검증**\n"
            "- 이름: 한글·영문·숫자·공백, 1~10자. 공백 단독 불가.\n"
            "- `image_id`: `HomeImageType` choice 정수 (1~8) 중 하나.\n"
            "- `chores`/`rewards`: 빈 배열이면 부속 생성을 건너뛴다.\n\n"
            "**에러**\n"
            "- 400 `already_has_home`: 이미 다른 집에 속해 있음 (먼저 나가야 함).\n"
            "- 400: 입력 유효성 실패.\n"
        ),
        request=HomeCreateSerializer,
        responses={
            201: OpenApiResponse(response=HomeOutputSerializer, description="생성된 집 (관리자 본인 포함된 members)."),
            400: OpenApiResponse(description="이미 집이 있거나 입력 유효성 실패."),
            401: OpenApiResponse(description="access 토큰 누락/만료."),
        },
        examples=[
            OpenApiExample(
                "정상 요청",
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
            )
        except services.AlreadyHasHomeError as e:
            raise ValidationError({"already_has_home": str(e)}) from e

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
            401: OpenApiResponse(description="access 토큰 누락/만료."),
            404: OpenApiResponse(description="속한 집 없음."),
        },
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
            400: OpenApiResponse(description="구성원이 있어 삭제 불가 (`home_has_members`)."),
            401: OpenApiResponse(description="access 토큰 누락/만료."),
            403: OpenApiResponse(description="관리자만 집을 삭제할 수 있음."),
        },
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
            401: OpenApiResponse(description="access 토큰 누락/만료."),
        },
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
            401: OpenApiResponse(description="access 토큰 누락/만료."),
            404: OpenApiResponse(description="유효하지 않은 초대코드."),
        },
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
            400: OpenApiResponse(description="이미 다른 집에 속해 있음."),
            401: OpenApiResponse(description="access 토큰 누락/만료."),
            404: OpenApiResponse(description="유효하지 않은 초대코드."),
        },
        examples=[
            OpenApiExample("정상 요청", value={"invite_code": "AB12CD"}, request_only=True),
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
            401: OpenApiResponse(description="access 토큰 누락/만료."),
            403: OpenApiResponse(description="관리자는 양도 또는 집 삭제 후 나갈 수 있음."),
            404: OpenApiResponse(description="속한 집 없음."),
        },
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
            400: OpenApiResponse(description="대상이 같은 집의 구성원이 아님."),
            401: OpenApiResponse(description="access 토큰 누락/만료."),
            403: OpenApiResponse(description="관리자만 양도 가능."),
        },
        examples=[
            OpenApiExample(
                "정상 요청",
                value={"user_id": "8f3e2b1a-1234-4abc-9def-1234567890ab"},
                request_only=True,
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
            401: OpenApiResponse(description="access 토큰 누락/만료."),
            404: OpenApiResponse(description="속한 집 없음."),
        },
    )
    def get(self, request: Request) -> Response:
        home = selectors.get_user_home(request.user)
        if home is None:
            raise NotFound("속한 집이 없습니다.")
        home_chores = selectors.get_home_chores(home)
        return Response(HomeChoreOutputSerializer(home_chores, many=True).data)

    @extend_schema(
        tags=["Homes"],
        summary="집안일 리스트 추가 (관리자 전용)",
        description=(
            "현재 유저가 관리자인 집에 집안일을 추가한다.\n\n"
            "- 입력은 항상 `chores` 배열로 받는다 (단건이면 길이 1).\n"
            "- 응답도 항상 배열이며, 각 원소는 새로 생성된 `HomeChore` 의 응답 표현.\n"
            "- 같은 마스터 `Chore` 가 같은 집에 중복으로 배정되지 않도록 unique 제약이 있다.\n"
        ),
        request=HomeChoreListCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=HomeChoreOutputSerializer(many=True),
                description="생성된 집안일 배열.",
            ),
            400: OpenApiResponse(description="유효성 검사 실패 또는 중복 배정."),
            401: OpenApiResponse(description="access 토큰 누락/만료."),
            403: OpenApiResponse(description="관리자만 등록 가능."),
            404: OpenApiResponse(description="속한 집 없음."),
        },
        examples=[
            OpenApiExample(
                "단건 등록",
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
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = HomeChoreListCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            home_chores = services.create_home_chores(
                user=request.user,
                chores=serializer.validated_data["chores"],
            )
        except services.HomeNotFoundError as e:
            raise NotFound(str(e)) from e

        return Response(HomeChoreOutputSerializer(home_chores, many=True).data, status=status.HTTP_201_CREATED)


class HomeChoreDetailView(APIView):
    """집안일 단건 — 메모 수정.

    현재는 PATCH 만 노출하며, 메모만 변경 가능하다 (이름/카테고리 등 마스터는 별도 흐름).
    """

    @extend_schema(
        tags=["Homes"],
        summary="집안일 메모 수정",
        description=(
            "지정한 집안일의 `memo` 만 변경한다.\n\n"
            "- 빈 문자열을 보내면 메모를 비운다 (필수 필드는 아님).\n"
            "- 다른 집의 집안일을 지정하면 404 (`HomeChoreNotFoundError`).\n"
        ),
        parameters=[
            OpenApiParameter(
                "home_chore_id",
                int,
                OpenApiParameter.PATH,
                description="대상 `HomeChore` PK.",
            ),
        ],
        request=ChoreMemoUpdateSerializer,
        responses={
            200: OpenApiResponse(response=HomeChoreOutputSerializer, description="수정된 집안일."),
            401: OpenApiResponse(description="access 토큰 누락/만료."),
            404: OpenApiResponse(description="집안일을 찾을 수 없거나 다른 집 소유."),
        },
        examples=[
            OpenApiExample("메모 입력", value={"memo": "다음 주는 청소 패스"}, request_only=True),
            OpenApiExample("메모 비우기", value={"memo": ""}, request_only=True),
        ],
    )
    def patch(self, request: Request, home_chore_id: int) -> Response:
        serializer = ChoreMemoUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            home_chore = services.update_home_chore_memo(
                user=request.user,
                home_chore_id=home_chore_id,
                memo=serializer.validated_data["memo"],
            )
        except services.HomeChoreNotFoundError as e:
            raise NotFound(str(e)) from e

        return Response(HomeChoreOutputSerializer(home_chore).data)


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
            401: OpenApiResponse(description="access 토큰 누락/만료."),
        },
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
            401: OpenApiResponse(description="access 토큰 누락/만료."),
        },
    )
    def get(self, request: Request, starter_pack_id: int) -> Response:
        chores = selectors.get_starter_pack_chores(starter_pack_id)
        return Response(ChoreOutputSerializer(chores, many=True).data)

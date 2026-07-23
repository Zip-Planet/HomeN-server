import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.boards.models import BotCardKind, RequestStatus
from apps.boards.services import create_help_request, create_swap_request, publish_bot_card
from apps.boards.tests.test_services import _confirmed_home_two_members, _item_of
from apps.homes.services import complete_chore
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

_BOARD_URL = "/api/v1/homes/mine/board/"


def auth_client(user) -> APIClient:
    client = APIClient()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


class TestBoardFeedView:
    def test_봇_카드와_조율_카드가_함께_내려온다(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        publish_bot_card(
            home=home,
            kind=BotCardKind.ASSIGNMENT_CONFIRMED,
            week_start=assignment.week_start,
            payload={"total_count": 4},
        )
        item = _item_of(assignment, admin)
        create_help_request(user=admin, item_id=item.id, message="대신해줄 사람?")

        res = auth_client(admin).get(_BOARD_URL)

        assert res.status_code == 200
        types = {c["type"] for c in res.data["cards"]}
        assert types == {"bot", "help"}
        bot = next(c for c in res.data["cards"] if c["type"] == "bot")
        assert bot["payload"]["total_count"] == 4
        assert bot["kind_label"] == "분담안 확정"
        help_card = next(c for c in res.data["cards"] if c["type"] == "help")
        assert help_card["status"] == RequestStatus.PENDING
        assert help_card["item"]["chore_name"]

    def test_집이_없으면_404(self):
        assert auth_client(UserFactory()).get(_BOARD_URL).status_code == 404

    def test_인증_없으면_401(self):
        assert APIClient().get(_BOARD_URL).status_code == 401


class TestBoardItemListView:
    url = f"{_BOARD_URL}items/"

    def test_내_항목만_필터(self):
        home, admin, member, assignment = _confirmed_home_two_members()

        res = auth_client(admin).get(self.url, {"assignee": "me"})

        assert res.status_code == 200
        assert all(row["assignee"]["uid"] == str(admin.uid) for row in res.data)

    def test_완료된_항목은_제외된다(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        item = _item_of(assignment, admin)
        complete_chore(user=admin, home_chore_id=item.home_chore_id)

        res = auth_client(admin).get(self.url, {"assignee": "me"})

        assert item.id not in [row["id"] for row in res.data]

    def test_이미_요청된_항목은_is_requested_true(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        item = _item_of(assignment, admin)
        create_help_request(user=admin, item_id=item.id)

        res = auth_client(admin).get(self.url, {"assignee": "me"})

        row = next(r for r in res.data if r["id"] == item.id)
        assert row["is_requested"] is True


class TestHelpRequestViews:
    def test_생성_201(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        item = _item_of(assignment, admin)

        res = auth_client(admin).post(
            f"{_BOARD_URL}help/", {"item_id": item.id, "message": "부탁해요"}, format="json"
        )

        assert res.status_code == 201
        assert res.data["status"] == RequestStatus.PENDING

    def test_남의_항목_요청은_403(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        item = _item_of(assignment, admin)

        res = auth_client(member).post(f"{_BOARD_URL}help/", {"item_id": item.id}, format="json")

        assert res.status_code == 403

    def test_중복_요청_409(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        item = _item_of(assignment, admin)
        client = auth_client(admin)
        client.post(f"{_BOARD_URL}help/", {"item_id": item.id}, format="json")

        res = client.post(f"{_BOARD_URL}help/", {"item_id": item.id}, format="json")

        assert res.status_code == 409
        assert res.data["error"]["code"] == "already_requested"

    def test_수락_200_이후_담당자_변경(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        item = _item_of(assignment, admin)
        help_request = create_help_request(user=admin, item_id=item.id)

        res = auth_client(member).post(f"{_BOARD_URL}help/{help_request.id}/accept/")

        assert res.status_code == 200
        item.refresh_from_db()
        assert item.assignee == member

    def test_취소_204(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        item = _item_of(assignment, admin)
        help_request = create_help_request(user=admin, item_id=item.id)

        res = auth_client(admin).delete(f"{_BOARD_URL}help/{help_request.id}/")

        assert res.status_code == 204

    def test_없는_카드_404(self):
        _home, admin, _member, _assignment = _confirmed_home_two_members()

        assert auth_client(admin).post(f"{_BOARD_URL}help/999999/accept/").status_code == 404


class TestSwapRequestViews:
    def test_생성_201(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        mine = _item_of(assignment, admin)
        theirs = _item_of(assignment, member)

        res = auth_client(admin).post(
            f"{_BOARD_URL}swap/",
            {"requester_item_id": mine.id, "target_item_id": theirs.id, "message": "바꿔줄래?"},
            format="json",
        )

        assert res.status_code == 201

    def test_수락_시_담당자_맞바꿈(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        mine = _item_of(assignment, admin)
        theirs = _item_of(assignment, member)
        swap = create_swap_request(user=admin, requester_item_id=mine.id, target_item_id=theirs.id)

        res = auth_client(member).post(f"{_BOARD_URL}swap/{swap.id}/accept/")

        assert res.status_code == 200
        mine.refresh_from_db()
        theirs.refresh_from_db()
        assert mine.assignee == member
        assert theirs.assignee == admin

    def test_거절_200(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        mine = _item_of(assignment, admin)
        theirs = _item_of(assignment, member)
        swap = create_swap_request(user=admin, requester_item_id=mine.id, target_item_id=theirs.id)

        res = auth_client(member).post(f"{_BOARD_URL}swap/{swap.id}/reject/")

        assert res.status_code == 200
        assert res.data["status"] == RequestStatus.REJECTED

    def test_요청자가_수락하려_하면_403(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        mine = _item_of(assignment, admin)
        theirs = _item_of(assignment, member)
        swap = create_swap_request(user=admin, requester_item_id=mine.id, target_item_id=theirs.id)

        assert auth_client(admin).post(f"{_BOARD_URL}swap/{swap.id}/accept/").status_code == 403

    def test_취소_204(self):
        home, admin, member, assignment = _confirmed_home_two_members()
        mine = _item_of(assignment, admin)
        theirs = _item_of(assignment, member)
        swap = create_swap_request(user=admin, requester_item_id=mine.id, target_item_id=theirs.id)

        assert auth_client(admin).delete(f"{_BOARD_URL}swap/{swap.id}/").status_code == 204

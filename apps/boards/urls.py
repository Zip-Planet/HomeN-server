"""집안 보드 URL 매핑.

`config.urls` 에서 `path("api/v1/homes/mine/board/", include(board_urlpatterns))`
로 마운트된다.
"""

from django.urls import path

from apps.boards.views import (
    BoardFeedView,
    BoardItemListView,
    HelpRequestAcceptView,
    HelpRequestDetailView,
    HelpRequestListView,
    SwapRequestAcceptView,
    SwapRequestDetailView,
    SwapRequestListView,
    SwapRequestRejectView,
)

board_urlpatterns = [
    path("", BoardFeedView.as_view()),
    path("items/", BoardItemListView.as_view()),
    path("help/", HelpRequestListView.as_view()),
    path("help/<int:help_request_id>/", HelpRequestDetailView.as_view()),
    path("help/<int:help_request_id>/accept/", HelpRequestAcceptView.as_view()),
    path("swap/", SwapRequestListView.as_view()),
    path("swap/<int:swap_id>/", SwapRequestDetailView.as_view()),
    path("swap/<int:swap_id>/accept/", SwapRequestAcceptView.as_view()),
    path("swap/<int:swap_id>/reject/", SwapRequestRejectView.as_view()),
]

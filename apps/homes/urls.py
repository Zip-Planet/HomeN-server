from django.urls import path

from apps.homes.views import (
    HomeChoreDetailView,
    HomeChoreListView,
    HomeCreateView,
    HomeDetailView,
    HomeImageListView,
    HomeInviteView,
    HomeJoinView,
    HomeLeaveView,
    HomeMembershipView,
    HomeTransferAdminView,
    StarterPackChoreListView,
    StarterPackListView,
)

home_urlpatterns = [
    path("", HomeCreateView.as_view()),
    path("images/", HomeImageListView.as_view()),
    path("mine/", HomeDetailView.as_view()),
    path("mine/membership/", HomeMembershipView.as_view()),
    path("mine/leave/", HomeLeaveView.as_view()),
    path("mine/transfer-admin/", HomeTransferAdminView.as_view()),
    path("mine/chores/", HomeChoreListView.as_view()),
    path("mine/chores/<int:home_chore_id>/", HomeChoreDetailView.as_view()),
    path("invite/<str:code>/", HomeInviteView.as_view()),
    path("join/", HomeJoinView.as_view()),
]

starter_pack_urlpatterns = [
    path("", StarterPackListView.as_view()),
    path("<int:starter_pack_id>/chores/", StarterPackChoreListView.as_view()),
]

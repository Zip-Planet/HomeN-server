from django.urls import path

from apps.homes.views import (
    HomeChoreView,
    HomeCreateView,
    HomeDetailView,
    HomeImageListView,
    HomeInviteView,
    HomeJoinView,
    HomeRewardView,
    StarterPackChoreListView,
    StarterPackListView,
)

home_urlpatterns = [
    path("", HomeCreateView.as_view()),
    path("images/", HomeImageListView.as_view()),
    path("mine/", HomeDetailView.as_view()),
    path("invite/<str:code>/", HomeInviteView.as_view()),
    path("join/", HomeJoinView.as_view()),
    path("<int:pk>/chores/", HomeChoreView.as_view()),
    path("<int:pk>/rewards/", HomeRewardView.as_view()),
]

starter_pack_urlpatterns = [
    path("", StarterPackListView.as_view()),
    path("<int:pk>/chores/", StarterPackChoreListView.as_view()),
]

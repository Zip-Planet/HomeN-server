"""리워드 URL 매핑.

`config.urls` 에서 `path("api/v1/homes/mine/rewards/", include(reward_urlpatterns))`
로 마운트된다 — 리워드는 집에 종속된 리소스다.
"""

from django.urls import path

from apps.rewards.views import RewardClaimView, RewardDetailView, RewardListView

reward_urlpatterns = [
    path("", RewardListView.as_view()),
    path("<int:reward_id>/", RewardDetailView.as_view()),
    path("<int:reward_id>/claim/", RewardClaimView.as_view()),
]

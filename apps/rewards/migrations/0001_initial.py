"""리워드 도메인 앱 초기 마이그레이션.

`Reward` 는 원래 `apps.homes` 에 있던 모델이다. 테이블(`rewards`)은 그대로 두고
**앱 소속만 이동**하므로 `SeparateDatabaseAndState` 로 상태만 생성한다 —
DDL 이 실행되지 않아 기존 데이터가 보존된다. 짝이 되는 상태 삭제는
`homes.0011_move_reward_to_rewards` 에 있다.

`RewardClaim` 은 신규 테이블이므로 일반 `CreateModel` 이다.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("homes", "0010_weeklyassignment_assignmentitem_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Reward",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                            ),
                        ),
                        ("name", models.CharField(max_length=50)),
                        ("goal_point", models.PositiveIntegerField()),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "home",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="rewards",
                                to="homes.home",
                            ),
                        ),
                    ],
                    options={"db_table": "rewards"},
                ),
            ],
            database_operations=[],
        ),
        migrations.CreateModel(
            name="RewardClaim",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("claimed_point", models.PositiveIntegerField()),
                ("claimed_at", models.DateTimeField(auto_now_add=True)),
                (
                    "claimed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reward_claims",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reward",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="claim",
                        to="rewards.reward",
                    ),
                ),
            ],
            options={"db_table": "reward_claims"},
        ),
    ]

"""`Reward` 를 `apps.rewards` 로 이동 (상태만 변경).

테이블 `rewards` 는 그대로 두고 모델의 앱 소속만 옮긴다. 실제 생성 쪽은
`rewards.0001_initial` 의 `SeparateDatabaseAndState` 이며, 여기서는 짝이 되는
상태 삭제만 수행한다. DDL 이 없으므로 데이터 손실이 발생하지 않는다.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("homes", "0010_weeklyassignment_assignmentitem_and_more"),
        ("rewards", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.DeleteModel(name="Reward")],
            database_operations=[],
        ),
    ]

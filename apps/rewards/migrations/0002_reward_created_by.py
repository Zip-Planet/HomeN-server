"""리워드 작성자(`created_by`) 컬럼 추가.

최종 디자인의 리워드 리스트가 항목별 수정/삭제 메뉴를 노출하므로 작성자를
기록해 둔다. 기존 행은 작성자를 알 수 없어 NULL 로 남는다.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("rewards", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="reward",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_rewards",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]

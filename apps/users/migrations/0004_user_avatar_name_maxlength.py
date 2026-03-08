from django.db import migrations, models


class Migration(migrations.Migration):
    """User 모델에 avatar 필드 추가 및 name max_length를 8로 변경합니다."""

    dependencies = [
        ("users", "0003_remove_user_email_socialaccount_updated_at_user_uid_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="avatar",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="user",
            name="name",
            field=models.CharField(blank=True, default="", max_length=8),
        ),
    ]

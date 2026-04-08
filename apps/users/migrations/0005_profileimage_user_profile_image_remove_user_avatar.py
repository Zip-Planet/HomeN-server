import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """ProfileImage 모델 추가, User에 profile_image FK 추가, avatar 필드 제거."""

    dependencies = [
        ("users", "0004_user_avatar_name_maxlength"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProfileImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(upload_to="preset_profiles/")),
            ],
            options={"db_table": "profile_images"},
        ),
        migrations.AddField(
            model_name="user",
            name="profile_image",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="users",
                to="users.profileimage",
            ),
        ),
        migrations.RemoveField(
            model_name="user",
            name="avatar",
        ),
    ]

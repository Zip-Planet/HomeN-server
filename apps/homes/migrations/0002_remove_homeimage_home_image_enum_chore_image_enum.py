from django.db import migrations, models


class Migration(migrations.Migration):
    """HomeImage 모델 삭제, Home.image FK를 IntegerField(enum)로 변경, Chore.image를 IntegerField(enum)로 변경."""

    dependencies = [
        ("homes", "0001_initial"),
    ]

    operations = [
        # Home.image: ForeignKey(HomeImage) → IntegerField(enum)
        # 기존 image_id FK 컬럼 제거 후 image IntegerField 추가
        migrations.RemoveField(
            model_name="home",
            name="image",
        ),
        migrations.AddField(
            model_name="home",
            name="image",
            field=models.IntegerField(
                choices=[
                    (1, "집 이미지 1"),
                    (2, "집 이미지 2"),
                    (3, "집 이미지 3"),
                    (4, "집 이미지 4"),
                    (5, "집 이미지 5"),
                    (6, "집 이미지 6"),
                    (7, "집 이미지 7"),
                    (8, "집 이미지 8"),
                ],
                default=1,
            ),
            preserve_default=False,
        ),
        # HomeImage 모델 삭제
        migrations.DeleteModel(
            name="HomeImage",
        ),
        # Chore.image: ImageField → IntegerField(enum)
        migrations.RemoveField(
            model_name="chore",
            name="image",
        ),
        migrations.AddField(
            model_name="chore",
            name="image",
            field=models.IntegerField(
                choices=[
                    (1, "집안일 이미지 1"),
                    (2, "집안일 이미지 2"),
                    (3, "집안일 이미지 3"),
                    (4, "집안일 이미지 4"),
                    (5, "집안일 이미지 5"),
                    (6, "집안일 이미지 6"),
                    (7, "집안일 이미지 7"),
                    (8, "집안일 이미지 8"),
                    (9, "집안일 이미지 9"),
                    (10, "집안일 이미지 10"),
                    (11, "집안일 이미지 11"),
                    (12, "집안일 이미지 12"),
                    (13, "집안일 이미지 13"),
                    (14, "집안일 이미지 14"),
                    (15, "집안일 이미지 15"),
                    (16, "집안일 이미지 16"),
                    (17, "집안일 이미지 17"),
                    (18, "집안일 이미지 18"),
                    (19, "집안일 이미지 19"),
                    (20, "집안일 이미지 20"),
                ],
                default=1,
            ),
            preserve_default=False,
        ),
    ]

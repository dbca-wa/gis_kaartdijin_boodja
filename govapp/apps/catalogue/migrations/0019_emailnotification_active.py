# Generated by Django 3.2.19 on 2023-06-30 02:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogue', '0018_layerattributetype'),
    ]

    operations = [
        migrations.AddField(
            model_name='emailnotification',
            name='active',
            field=models.BooleanField(default=True),
        ),
    ]

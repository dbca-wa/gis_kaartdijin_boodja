# Generated by Django 3.2.18 on 2023-05-03 06:52

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('publisher', '0006_remove_names'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='cddppublishchannel',
            name='description',
        ),
    ]

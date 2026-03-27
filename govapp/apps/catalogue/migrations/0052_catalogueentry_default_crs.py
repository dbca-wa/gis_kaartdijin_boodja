# Generated manually 2026-03-27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogue', '0051_layersubmission_crs'),
    ]

    operations = [
        migrations.AddField(
            model_name='catalogueentry',
            name='default_crs',
            field=models.CharField(
                blank=True,
                choices=[
                    ('EPSG:4283', 'GDA94 (EPSG:4283)'),
                    ('EPSG:7844', 'GDA2020 (EPSG:7844)'),
                ],
                help_text='Expected CRS for uploaded spatial files. If set, uploads with a different CRS will be declined.',
                max_length=64,
                null=True,
            ),
        ),
    ]

# Generated manually 2026-03-27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogue', '0050_layersubmission_file_size'),
    ]

    operations = [
        migrations.AddField(
            model_name='layersubmission',
            name='crs',
            field=models.CharField(
                blank=True,
                help_text="CRS of the submitted spatial file, e.g. 'EPSG:7844'.",
                max_length=64,
                null=True,
            ),
        ),
    ]

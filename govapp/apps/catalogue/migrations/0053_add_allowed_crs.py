# Generated manually 2026-05-04

from django.db import migrations, models


def insert_initial_crs(apps, schema_editor):
    AllowedCRS = apps.get_model('catalogue', 'AllowedCRS')
    AllowedCRS.objects.bulk_create([
        AllowedCRS(epsg_code='EPSG:4283', label='GDA94'),
        AllowedCRS(epsg_code='EPSG:7844', label='GDA2020'),
    ])


def remove_initial_crs(apps, schema_editor):
    AllowedCRS = apps.get_model('catalogue', 'AllowedCRS')
    AllowedCRS.objects.filter(
        epsg_code__in=['EPSG:4283', 'EPSG:7844']
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('catalogue', '0052_catalogueentry_default_crs'),
    ]

    operations = [
        migrations.CreateModel(
            name='AllowedCRS',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('epsg_code', models.CharField(help_text="EPSG CRS identifier, e.g. 'EPSG:7844'.", max_length=64, unique=True)),
                ('label', models.CharField(help_text="Human-readable name, e.g. 'GDA2020'.", max_length=256)),
            ],
            options={
                'verbose_name': 'Allowed CRS',
                'verbose_name_plural': 'Allowed CRS',
                'ordering': ['epsg_code'],
            },
        ),
        migrations.RunPython(insert_initial_crs, reverse_code=remove_initial_crs),
        migrations.AlterField(
            model_name='catalogueentry',
            name='default_crs',
            field=models.CharField(
                blank=True,
                help_text='Expected CRS for uploaded spatial files. If set, uploads with a different CRS will be declined.',
                max_length=64,
                null=True,
            ),
        ),
    ]

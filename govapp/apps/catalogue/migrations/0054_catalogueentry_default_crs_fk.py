# Generated manually 2026-05-04

import logging

import django.db.models.deletion
from django.db import migrations, models


logger = logging.getLogger(__name__)


def migrate_data(apps, schema_editor):
    """Convert existing epsg_code strings to AllowedCRS FK references."""
    CatalogueEntry = apps.get_model('catalogue', 'CatalogueEntry')
    AllowedCRS = apps.get_model('catalogue', 'AllowedCRS')
    for entry in CatalogueEntry.objects.filter(
        default_crs_epsg__isnull=False
    ).exclude(default_crs_epsg=''):
        try:
            allowed_crs = AllowedCRS.objects.get(epsg_code=entry.default_crs_epsg)
            entry.default_crs = allowed_crs
            entry.save()
        except AllowedCRS.DoesNotExist:
            logger.warning(
                f"CatalogueEntry id={entry.id}: epsg_code '{entry.default_crs_epsg}' "
                "not found in AllowedCRS. Setting to null."
            )


def reverse_migrate_data(apps, schema_editor):
    """Restore epsg_code strings from AllowedCRS FK references."""
    CatalogueEntry = apps.get_model('catalogue', 'CatalogueEntry')
    for entry in CatalogueEntry.objects.filter(default_crs__isnull=False):
        entry.default_crs_epsg = entry.default_crs.epsg_code
        entry.save()


class Migration(migrations.Migration):

    dependencies = [
        ('catalogue', '0053_add_allowed_crs'),
    ]

    operations = [
        migrations.RenameField(
            model_name='catalogueentry',
            old_name='default_crs',
            new_name='default_crs_epsg',
        ),
        migrations.AddField(
            model_name='catalogueentry',
            name='default_crs',
            field=models.ForeignKey(
                blank=True,
                help_text='Expected CRS for uploaded spatial files. If set, uploads with a different CRS will be declined.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='catalogue_entries',
                to='catalogue.allowedcrs',
            ),
        ),
        migrations.RunPython(migrate_data, reverse_code=reverse_migrate_data),
        migrations.RemoveField(
            model_name='catalogueentry',
            name='default_crs_epsg',
        ),
    ]

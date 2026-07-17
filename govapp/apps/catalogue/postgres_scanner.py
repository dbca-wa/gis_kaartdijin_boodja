"""Kaartdijin Boodja Catalogue Django Application Scanner."""

# Standard
import logging
import os
import shutil
import calendar
from datetime import datetime
from zoneinfo import ZoneInfo
from dateutil.relativedelta import relativedelta

# Third-Party
from django import conf

# Local
from govapp.apps.catalogue.models import layer_subscriptions
from govapp.apps.catalogue.models import catalogue_entries
from govapp.apps.catalogue.models import custom_query_frequency
from govapp.gis import conversions
from django import conf
# from govapp.common import local_storage
# from govapp.apps.catalogue import directory_absorber
# from govapp.apps.catalogue import notifications


# Logging
log = logging.getLogger(__name__)


class Scanner:
    def __init__(self) -> None:
        """Instantiates the Scanner."""
        # Storage        
        #self.storage = local_storage.LocalStorage()

    def scan(self) -> None:
        # Log
        log.info("Start scanning postgres queries...")

        catalogue_entry_list = catalogue_entries.CatalogueEntry.objects.filter(
            type=catalogue_entries.CatalogueEntryType.SUBSCRIPTION_QUERY,
        )
        for ce in catalogue_entry_list:
            log.debug(f'{ce}')

        for catalogue_entry_obj in catalogue_entry_list:
            log.info(f'Scanning postgres queries for the CatalogueEntry: [{catalogue_entry_obj}]...')

            if catalogue_entry_obj.layer_subscription.status != layer_subscriptions.LayerSubscriptionStatus.LOCKED:
                log.warning(f'CatalogueEntry: [{catalogue_entry_obj}] is skipped to process because its layer_subscription is not LOCKED.')
                continue

            for custom_query_freq in catalogue_entry_obj.custom_query_frequencies.all():  # CatalogueEntry can have 0 or 1 custom_query_frequency.
                log.info(f'Working on the CustomQueryFrequency: [{catalogue_entry_obj}] for the CatalogueEntry: [{catalogue_entry_obj}]...')
                generate_shp = False
                skip_reason = "An unknown scheduling condition was not met."  # Fallback message
                now_dt = datetime.now(tz=ZoneInfo(conf.settings.TIME_ZONE))
                log.info(f'Now datetime is [{now_dt}].')

                if catalogue_entry_obj.force_run_postgres_scanner:
                    # When force_run_postgres_scanner is set to True, we don't need to check the schedule
                    log.info(f'CatalogueEntry: [{custom_query_freq.catalogue_entry}] has force_run_postgres_scanner=True.  Run scanning.')
                    generate_shp = True
                elif not custom_query_freq.last_job_run:
                    # Scanning has never been run so far.  --> Run scanning
                    log.info(f'CatalogueEntry: [{custom_query_freq.catalogue_entry}] has never been scanned for custom query with this frequency: [{custom_query_freq}].  Run scanning.')
                    generate_shp = True
                else:
                    # Retrieve the last job run datetime
                    last_job_run = custom_query_freq.last_job_run.astimezone(ZoneInfo(conf.settings.TIME_ZONE))

                    # Every minute scheduler.
                    if custom_query_freq.type == custom_query_frequency.FrequencyType.EVERY_MINUTES:
                        dt_diff = now_dt - last_job_run
                        last_job_run_in_minutes = dt_diff.total_seconds() / 60
                        if last_job_run_in_minutes > custom_query_freq.every_minutes:
                            generate_shp = True
                        else:
                            skip_reason = (f"the last run was only {last_job_run_in_minutes:.2f} minutes ago, which is within the {custom_query_freq.every_minutes}-minute schedule.")

                    # Every hour scheduler.
                    elif custom_query_freq.type == custom_query_frequency.FrequencyType.EVERY_HOURS:
                        dt_diff = now_dt - last_job_run
                        last_job_run_in_hours = dt_diff.total_seconds() / 3600
                        if last_job_run_in_hours >= custom_query_freq.every_hours:
                            generate_shp = True
                        else:
                            skip_reason = (f"the last run was only {last_job_run_in_hours:.2f} hours ago, which is within the {custom_query_freq.every_hours}-hour schedule.")

                    # Daily scheduler.
                    elif custom_query_freq.type == custom_query_frequency.FrequencyType.DAILY:
                        # Calculate most recent scheduled datetime
                        most_recent_schedule = Scanner.get_most_recent_past_schedule_daily(now_dt, custom_query_freq)
                        generate_shp = Scanner.should_run_scanner(last_job_run, most_recent_schedule)
                        if not generate_shp:
                            skip_reason = (f"the last run at {last_job_run.strftime('%Y-%m-%d %H:%M')} is not before the most recent schedule at {most_recent_schedule.strftime('%Y-%m-%d %H:%M')}.")

                    # Weekly scedhuler
                    elif custom_query_freq.type == custom_query_frequency.FrequencyType.WEEKLY:
                        # Calculate most recent scheduled datetime
                        most_recent_schedule = Scanner.get_most_recent_past_schedule_weekly(now_dt, custom_query_freq)
                        generate_shp = Scanner.should_run_scanner(last_job_run, most_recent_schedule)
                        if not generate_shp:
                            skip_reason = (f"the last run at {last_job_run.strftime('%Y-%m-%d %H:%M')} is not before the most recent schedule at {most_recent_schedule.strftime('%Y-%m-%d %H:%M')}.")

                    # Monthly Schedule
                    elif custom_query_freq.type == custom_query_frequency.FrequencyType.MONTHLY:  
                        # Calculate most recent scheduled datetime
                        most_recent_schedule = Scanner.get_most_recent_past_schedule_monthly(now_dt, custom_query_freq)
                        generate_shp = Scanner.should_run_scanner(last_job_run, most_recent_schedule)
                        if not generate_shp:
                            skip_reason = (f"the last run at {last_job_run.strftime('%Y-%m-%d %H:%M')} is not before the most recent schedule at {most_recent_schedule.strftime('%Y-%m-%d %H:%M')}.")

                if generate_shp:  
                    Scanner.run_postgres_to_shapefile(catalogue_entry_obj, custom_query_freq, now_dt)
                    catalogue_entry_obj.force_run_postgres_scanner = False
                    catalogue_entry_obj.save()
                else:
                    log.info(f"Skipping postgres_to_shapefile for CatalogueEntry: [{custom_query_freq.catalogue_entry}] because {skip_reason}")

        # Log
        log.info("Scanning postgres queries complete!")

    @staticmethod
    def get_most_recent_past_schedule_weekly(now_dt, custom_query_freq):
        # Convert day_of_week to 0-based index (0: Monday, 6: Sunday)
        target_weekday = custom_query_freq.day_of_week - 1

        # Calculate the difference in days to the target weekday
        current_weekday = now_dt.weekday()
        days_difference = (target_weekday - current_weekday) % 7

        # If the target weekday is in the future, subtract 7 days to get the most recent past date
        if days_difference >= 0:
            days_difference -= 7

        # Calculate the most recent schedule date
        most_recent_date = now_dt + relativedelta(days=days_difference)

        # Replace the time part with the scheduled time
        most_recent_schedule = most_recent_date.replace(
            hour=custom_query_freq.hour,
            minute=custom_query_freq.minute,
            second=0,
            microsecond=0
        )

        return most_recent_schedule

    @staticmethod
    def get_most_recent_past_schedule_monthly(now_dt, custom_query_freq):
        # Handle monthly schedule
        most_recent_schedule = datetime(now_dt.year, now_dt.month, custom_query_freq.date, custom_query_freq.hour, custom_query_freq.minute).astimezone(ZoneInfo(conf.settings.TIME_ZONE))

        # If the target date is in the future, subtract one month
        if most_recent_schedule > now_dt:
            if now_dt.month == 1:
                most_recent_schedule = most_recent_schedule.replace(year=now_dt.year - 1, month=12)
            else:
                most_recent_schedule = most_recent_schedule.replace(month=now_dt.month - 1)

        return most_recent_schedule
    
    @staticmethod
    def get_most_recent_past_schedule_daily(now_dt, custom_query_freq):
        # Handle daily schedule
        most_recent_schedule = now_dt.replace(
            hour=custom_query_freq.hour,
            minute=custom_query_freq.minute,
            second=0,
            microsecond=0
        )

        # If the target time is in the future, subtract one day
        if most_recent_schedule > now_dt:
            most_recent_schedule -= relativedelta(days=1)

        return most_recent_schedule

    @staticmethod
    def should_run_scanner(last_job_run, most_recent_schedule):
        if last_job_run < most_recent_schedule:
            log.info(f'The last job run datetime: [{last_job_run}] is before the most recent scheduled datetime: [{most_recent_schedule}].  Run scanning.')
            return True
        else:
            log.info(f'The last job run datetime: [{last_job_run}] is after the most recent scheduled datetime: [{most_recent_schedule}].  Do not run scanning.')
            return False
    
    @staticmethod
    def run_postgres_to_shapefile(catalogue_entry_obj, custom_query_freq=None, now_dt=datetime.now(tz=ZoneInfo(conf.settings.TIME_ZONE))):
        destination_path = None
        try:
            co = conversions.postgres_to_shapefile(
                catalogue_entry_obj.name,
                catalogue_entry_obj.layer_subscription.host,
                catalogue_entry_obj.layer_subscription.username,
                catalogue_entry_obj.layer_subscription.userpassword,
                catalogue_entry_obj.layer_subscription.database,
                catalogue_entry_obj.layer_subscription.port,
                catalogue_entry_obj.sql_query
            )

            if co:
                log.debug(f'co: {co}')
                # Case 1: A shapefile was successfully created. 'co' is a dictionary.
                log.info(f"Shapefile created for CatalogueEntry: [{catalogue_entry_obj}]. Processing file...")
                source_path = co["compressed_filepath"]
                destination_path = os.path.join(conf.settings.PENDING_IMPORT_PATH, os.path.basename(source_path))
                shutil.copyfile(source_path, destination_path)
                os.unlink(source_path)
                log.info(f'CatalogueEntry: [{catalogue_entry_obj}] has been converted to the shapefile: [{destination_path}].')
            elif co is None:
                # Case 2: The query returned no results. 'co' is None.
                log.info(f"Custom query for the CatalogueEntry: [{catalogue_entry_obj}] returned no results. No shapefile was created, which is a valid outcome.")
            elif co is False:
                # Case 3: Unexpectedly failed to create shapefile
                # log.info(f"Unexpectedly, no shapefile was created for the CatalogueEntry: [{catalogue_entry_obj}].  Check the the previous before.")
                log.error(
                    f"Unexpectedly, no shapefile was created for the CatalogueEntry: [{catalogue_entry_obj}]. "
                    f"This usually indicates a failure in pgsql2shp execution. Please check the conversion logs above for details."
                )

            # Step 3: Update the timestamp regardless of the results.  We don't want cron to keep trying to perform the postgres_to_shapefile until success.
            log.info(f"Updating last_job_run timestamp for CatalogueEntry: [{catalogue_entry_obj}].")
            if custom_query_freq:
                custom_query_freq.last_job_run = now_dt
                custom_query_freq.save()
            else:
                catalogue_entry_obj.custom_query_frequencies.update(last_job_run=now_dt)
            return destination_path

        except Exception as e:
            log.error(f"ERROR Running POSTGIS to Shapefile conversation for the CatalogueEntry: [{catalogue_entry_obj}]. error: [{e}]")
            # raise

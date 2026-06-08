# Task Summary: DBCA Staff Group

## What was implemented

Automated management of a DBCA staff-specific GeoServer user group called `DBCA_Users`.

### Files changed

| File | Change |
|---|---|
| `govapp/settings.py` | Added `GEOSERVER_GROUP_DBCA_USERS = 'DBCA_Users'` and the `CUSTOM_GEOSERVER_GROUPS` list |
| `govapp/apps/accounts/checks.py` | Added a Django System Check that auto-creates the `DBCA_Users` GeoServerGroup in the DB at startup |
| `govapp/apps/accounts/apps.py` | Registered the system check in `AccountsConfig.ready()` |
| `govapp/apps/publisher/models/geoserver_roles_groups.py` | Added a `unique_together` constraint to `GeoServerGroupUser` and a `link_users_to_group()` manager method for bulk-linking users to a group |
| `govapp/apps/accounts/management/commands/sync_itassets_users.py` | After syncing users from Itassets, automatically assigns all active DBCA domain users to the `DBCA_Users` group |
| (migration) `0056_alter_geoservergroupuser_unique_together.py` | Migration for the `unique_together` constraint on `GeoServerGroupUser` |

---

## How it works

### 1. Automatic group creation (at startup)

When the Django app starts, the System Check Framework runs `perform_geoserver_group_check()` in `govapp/apps/accounts/checks.py`. It calls `GeoServerGroup.objects.get_or_create()` for each group listed in `settings.CUSTOM_GEOSERVER_GROUPS` (currently just `DBCA_Users`). No manual DB setup is required.

### 2. User sync and group assignment (on command run)

Running `python manage.py sync_itassets_users`:

1. Fetches staff data from the Itassets API
2. Bulk-creates or updates Django users whose email matches `settings.DEPT_DOMAINS` (e.g. `@dbca.wa.gov.au`), setting `is_staff=True`
3. Bulk-links all active DBCA domain users to the `DBCA_Users` group via `GeoServerGroupUser` records (duplicates are prevented by the `unique_together` constraint)

### Data flow

```
Itassets API (staff data)
    ↓ sync_itassets_users command
Django Users created/updated (is_staff=True)
    ↓
GeoServerGroupUser records created
    ↓
GeoServer recognises users as members of the DBCA_Users group
```

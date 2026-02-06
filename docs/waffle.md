# django-waffle (Feature Flags)

This short guide explains how we use django-waffle to control runtime feature flags and how to add/remove them.

## Why use Waffle

- Provides runtime feature flagging that can be changed from Django Admin or via the ORM/management commands. ✅
- Our code consults a Flag/Switch to enable/disable certain behavior (e.g., auditing) without redeploying.

---

## How to add a Flag via Django Admin

The Django Admin interface provides granular control over who sees a feature.

1. Log in to Django Admin.
2. Go to **Waffle → Flags** → **Add Flag**.
3. Configure the fields based on the requirements below:

### Configuration Fields

| Field             | Description                                                                                                                                                                                                                                            |
| :---------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Name**          | The unique, computer-readable name used in the code (e.g., `audit.enabled`).                                                                                                                                                                           |
| **Everyone**      | **The Master Switch.** <br>• **Yes:** On for everyone, ignoring all other settings.<br>• **No:** Off for everyone, ignoring all other settings.<br>• **Unknown:** (Recommended) Waffle will check the specific criteria below (Groups, Percent, etc.). |
| **Percent**       | A value between 0.0 and 99.9. This enables the feature for a random percentage of your user base. Useful for canary.<br>Note: For a 100% rollout, set Everyone to Yes instead.deployments.                                                             |
| **Testing**       | If checked, the flag can be toggled on/off for a specific session via a query parameter (e.g., `?dwf=flag_name`), which is useful for QA.                                                                                                              |
| **Superusers**    | If checked, the flag is always active for any user with `is_superuser=True`.                                                                                                                                                                           |
| **Staff**         | If checked, the flag is always active for any user with `is_staff=True`.                                                                                                                                                                               |
| **Authenticated** | If checked, the flag is active for all logged-in users.                                                                                                                                                                                                |
| **Languages**     | A comma-separated list of language codes (e.g., `en, fr`). The flag will only be active for users with these language preferences.                                                                                                                     |
| **Rollout**       | Enables "Rollout Mode." When active, users who are NOT in the "Percent" group will have the flag cached as "off" to ensure a consistent experience.                                                                                                    |
| **Note**          | A text field for internal documentation explaining why the flag exists and who "owns" it.                                                                                                                                                              |
| **Groups**        | Select specific Django Auth Groups. The flag will be active for any user belonging to the selected groups.                                                                                                                                             |
| **Users**         | Select specific individual users to whitelist for this feature.                                                                                                                                                                                        |

1. Click **Save**.

---

## How to add a Switch via Django Admin (recommended for global toggles)

1. Log in to Django Admin.
2. Go to **Waffle → Switches → Add Switch**.
3. Set **Name** (e.g. `audit.enabled`) and toggle **Everyone** or other criteria.
4. Save.

> Notes:
>
> - This project now prefers an env var/setting `AUDIT_ENABLED` (default: `True`) to enable/disable audit globally at startup. Waffle can still be used for feature flags unrelated to the audit subsystem.
> - If you previously created a **Flag** with the same name, consider converting it to a Switch so the project behaves as intended.
>
> Convert or create via shell:
>
> ```py
> python manage.py shell
> from waffle.models import Flag, Switch
> # optional: delete existing Flag with the same name
> Flag.objects.filter(name='audit.enabled').delete()
> # create Switch enabled for everyone
> Switch.objects.create(name='audit.enabled', everyone=True)
> ```

## How to add via Django shell

While Admin is recommended for UI-based control, you can also manage flags via the ORM:

```py
python manage.py shell
from waffle.models import Flag

# create a flag enabled for everyone
Flag.objects.create(name='audit.enabled', everyone=True)

# enable it only for superusers
Flag.objects.filter(name='audit.enabled').update(everyone=None, superusers=True)
```

---

## How the project uses Flags and Switches

- By default, features are controlled by Waffle (not environment variables).
- The switch name can be configured in settings via `AUDIT_WAFFLE_SWITCH_NAME` (default: `audit.enabled`).
- This project prefers a **Switch** (global on/off) for simple, runtime toggles. For compatibility, we also accept a **Flag** with the same name when it targets `everyone` or `superusers` (this is a pragmatic fallback).
- If waffle is not installed, features default to the _enabled_ state to avoid accidental disable.

---

## Switch configuration fields (admin / ORM)

- **Name**: Unique identifier used in code (e.g., `audit.enabled`).
- **Active**: Boolean toggle. When True the switch is considered enabled for everyone (global on/off).
- **Note**: Free text explaining the purpose and owner of the Switch.
- **Created / Modified**: Timestamps maintained by Waffle for auditing changes.

> Example (ORM):
>
> ```py
> from waffle.models import Switch
> Switch.objects.create(name='audit.enabled', active=True)
> ```

## Flag configuration fields (admin / ORM)

Flags are request-scoped and provide granular control. Key fields:

- **Name**: Unique identifier used in code (e.g., `some_feature.rollout`).
- **Everyone**: Override to force the flag on/off for everyone.
- **Percent**: Percentage of users who will randomly have the flag active (useful for canaries).
- **Testing**: If checked, the flag can be toggled via querystring (e.g., `?dwf=flag_name`) for session testing.
- **Superusers**: Always active for superusers when checked.
- **Staff**: Always active for staff users when checked.
- **Authenticated**: Active for all authenticated users when checked.
- **Languages**: Comma-separated language codes the flag applies to.
- **Rollout**: Controls cookie TTL semantics to support staged rollouts.
- **Groups**: Select specific Django groups to enable the flag for.
- **Users**: Select specific users to whitelist for the flag.
- **Note / Created / Modified**: Metadata fields as with Switches.

> Example (ORM):
>
> ```py
> from waffle.models import Flag
> Flag.objects.create(name='audit.enabled', everyone=True)
> ```

---

## Differences and when to use each 🧭

- **Switches (global)** ✅
  - Simple global on/off toggle (single boolean).
  - Use when you need to enable or disable a feature for all users immediately (e.g., emergency kill-switch, global audit toggle).
  - Accessed with `waffle.switch_is_active(name)` in code.

- **Flags (granular)** ✅
  - Support per-user, per-group, percentage rollouts, and test-mode via querystring.
  - Use when you need phased rollouts, targeted exposure, or to test behavior for specific groups/users.
  - Accessed with `waffle.flag_is_active(request, name)` (request-scoped).

- **Practical rule**: prefer a **Switch** for global toggles (like `audit.enabled`). Use a **Flag** when you want gradual rollout or targeted enabling.

---

## Current available Flags/Switches

> Update this list whenever a new flag/switch is added to the codebase.

| Flag/Switch name | Purpose                                                                                                                                       | Default behaviour                                                                        |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `audit.enabled`  | Controls audit logging/forwarding (CRUD, auth, and request events). When **off**, audit persistence and structured audit logging are skipped. | Enabled by default when waffle is missing or switch/flag is active for the request/user. |

---

## Testing tips

- Unit tests may mock `waffle` or create an actual `Flag` in the test DB.
- Example: `with patch.dict('sys.modules', {'waffle': mock_waffle})` where `mock_waffle.flag_is_active = lambda request, name: False`.

---

## Notes

- **Flags vs. Switches:** Use **Switches** for simple global on/off toggles. Use **Flags** (shown in the screenshot) when you need granular control over specific users, groups, or percentages.
- Keep this document updated: when adding a new flag to the codebase, add an entry to the table above.

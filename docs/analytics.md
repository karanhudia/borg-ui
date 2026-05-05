# Analytics and Privacy

Borg UI has optional product analytics. The goal is to understand which parts of the app are used and where users hit errors, without sending backup contents, repository secrets, or private hostnames.

Analytics is shown behind a consent banner after login. Users can change the setting later in Settings > Preferences.

## Provider

Borg UI uses Umami Cloud:

```text
https://cloud.umami.is
```

The public dashboard is:

```text
https://analytics.nullcodeai.dev/
```

## What Can Be Sent

When analytics is enabled, the frontend can send:

- page views
- UI events, such as create, edit, delete, start, complete, fail, test, search, filter, export
- broad feature categories, such as repository, backup, archive, mount, SSH connection, settings, plan, announcement
- app version
- browser language
- document title
- a hashed per-install user identifier

The real browser hostname and URL are masked before sending. Borg UI reports them as:

```text
app.borgui
```

## What Is Not Intentionally Sent

Borg UI should not send:

- file contents
- Borg repository contents
- passphrases
- SSH private keys
- real hostnames or private IP addresses
- real repository names or paths as raw values

Analytics code must keep this boundary. If a future event needs extra metadata, prefer counts, categories, durations, or anonymized values.

## Identifier Behavior

For logged-in users, Borg UI creates a random install ID in browser local storage and combines it with the username. The combined value is hashed before it is sent as `user_id`.

This means analytics can count repeated use from the same browser/user without receiving the raw username.

## Consent Event

The consent banner records whether analytics was accepted or declined. That event can be sent before the preference is saved.

## Disable Analytics

Open Settings > Preferences and turn analytics off.

If analytics is disabled or preferences cannot be loaded, normal tracking is skipped.

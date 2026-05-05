---
layout: default
title: Notifications
nav_order: 5
description: "Configure Apprise notifications and JSON webhooks"
---

# Notifications

Borg UI uses [Apprise](https://github.com/caronc/apprise) for notifications.

Configure services in Settings > Notifications.

## Supported Targets

Any Apprise URL supported by the installed Apprise version can be used, including:

- email
- Slack
- Discord
- Telegram
- Microsoft Teams
- ntfy
- Pushover
- JSON webhooks

Examples:

```text
mailto://user:app_password@gmail.com?smtp=smtp.gmail.com&mode=starttls
slack://TokenA/TokenB/TokenC/
discord://webhook_id/webhook_token
tgram://bot_token/chat_id
ntfy://topic_name
jsons://example.com/webhooks/borg-ui
```

Use `jsons://` for HTTPS JSON webhooks and `json://` for HTTP JSON webhooks. Do not write `json://https://...`.

## Event Triggers

Notification services can subscribe to these events:

| Event | Default |
| --- | --- |
| Backup start | off |
| Backup success | off |
| Backup warning | off |
| Backup failure | on |
| Restore success | off |
| Restore failure | on |
| Check success | off |
| Check failure | on |
| Schedule failure | on |

Recommended minimum for production:

- backup failure
- backup warning
- restore failure
- check failure
- schedule failure

## Repository Scope

Each notification service can monitor:

- all repositories
- selected repositories only

Use selected repositories when different teams or channels own different backup sets.

## JSON Webhooks

For `json://` and `jsons://` URLs, Apprise sends a JSON webhook wrapper. Borg UI puts the event data in the `message` field as a JSON string.

Example wrapper:

```json
{
  "version": "1.0",
  "title": "[SUCCESS] Backup Successful - Daily Backup",
  "message": "{\"event_type\":\"backup_success\",\"repository_name\":\"laptop\",\"archive_name\":\"laptop-2026-05-05\"}",
  "attachments": [],
  "type": "success"
}
```

Parse it like this:

```python
import json

def handle_webhook(payload):
    event = json.loads(payload["message"])
    print(event["event_type"])
    print(event.get("repository_name"))
```

Only `json://` and `jsons://` targets receive this machine-friendly JSON body. Email, Slack, Discord, and similar targets receive human-readable notification text.

## Event Payloads

Payload fields vary by event. Common fields include:

| Field | Meaning |
| --- | --- |
| `event_type` | Event name, for example `backup_failure` |
| `timestamp` | Event time |
| `repository_name` | Repository display name |
| `repository_path` | Repository path |
| `archive_name` | Archive name, when relevant |
| `job_name` | Schedule/job name, when relevant |
| `error_message` | Failure text, when relevant |
| `stats` | Backup stats, when available |

Do not assume every field exists for every event.

## Test a Service

1. Add the service URL.
2. Choose the event triggers.
3. Choose all repositories or selected repositories.
4. Click Test.

The test verifies Apprise delivery. It does not prove that a real backup or restore event has occurred.

## Troubleshooting

### No notification arrives

- Check the Apprise URL format.
- Use the Test button.
- Check Borg UI logs.
- Check whether the event trigger is enabled.
- Check whether the repository is included in the service scope.

### JSON webhook fails

- Use `jsons://host/path` for HTTPS.
- Do not include `https://` after `jsons://`.
- Parse `payload["message"]` as JSON.

### Too many notifications

Disable success/start events and keep warning/failure events enabled.

---
layout: default
title: Notifications
nav_order: 5
description: "Configure alerts via email, Slack, Discord, and 100+ services"
---

# Notifications Setup

Get real-time alerts for backup failures, restore completions, and scheduled job issues via 100+ notification services.

---

## Supported Services

Borg Web UI uses [Apprise](https://github.com/caronc/apprise) for notifications, which supports:

- **Email** (Gmail, Outlook, Yahoo, custom SMTP)
- **Messaging** (Slack, Discord, Telegram, Microsoft Teams, Matrix)
- **Push Notifications** (Pushover, Pushbullet, ntfy)
- **SMS** (Twilio, AWS SNS, Nexmo)
- **Custom Webhooks** (JSON, XML)
- **And 100+ more services**

Full list: [Apprise Supported Notifications](https://github.com/caronc/apprise/wiki)

---

## Quick Start

1. Navigate to **Settings** > **Notifications** tab
2. Click **Add Service**
3. Enter service details:
   - **Name**: Friendly identifier (e.g., "Gmail Alerts", "Slack - DevOps")
   - **Service URL**: Apprise URL format for your service
   - **Title Prefix**: Optional prefix for notification titles (e.g., "[Production]")
   - **Event Triggers**: Select which events should trigger notifications
4. Click **Test** to verify the configuration
5. Click **Add** to save

---

## Service URL Examples

### Email (Gmail)

**Requirements:**
- Gmail account with 2-Step Verification enabled
- App Password generated ([instructions](https://support.google.com/accounts/answer/185833))

**URL Format:**
```
mailto://username:app_password@gmail.com?smtp=smtp.gmail.com&mode=starttls
```

**Example:**
```
mailto://john:abcdwxyzpqrs@gmail.com?smtp=smtp.gmail.com&mode=starttls
```

### Slack

**Requirements:**
- Slack Incoming Webhook URL ([create one](https://api.slack.com/messaging/webhooks))

**URL Format:**
```
slack://TokenA/TokenB/TokenC/
```

**Example:**
```
slack://T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX/
```

### Discord

**Requirements:**
- Discord Webhook URL from channel settings

**URL Format:**
```
discord://webhook_id/webhook_token
```

**Example:**
```
discord://123456789012345678/abcdef-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

### Telegram

**Requirements:**
- Bot token from [@BotFather](https://t.me/botfather)
- Chat ID (send a message to your bot, then get chat_id from `https://api.telegram.org/bot<token>/getUpdates`)

**URL Format:**
```
tgram://bot_token/chat_id
```

**Example:**
```
tgram://123456789:ABCdefGHIjklMNOpqrsTUVwxyz/987654321
```

### Microsoft Teams

**Requirements:**
- Teams Incoming Webhook URL ([create one](https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-incoming-webhook))

**URL Format:**
```
msteams://TokenA/TokenB/TokenC/
```

### Pushover

**Requirements:**
- Pushover user key and application token ([get them here](https://pushover.net/))

**URL Format:**
```
pover://user_key@app_token
```

**Example:**
```
pover://uQiRzpo4DXghDmr9QzzfQu27cmVRsG@azGDORePK8gMaC0QOYAMyEEuzJnyUi
```

### ntfy

**Requirements:**
- Topic name (public or self-hosted ntfy server)

**URL Format:**
```
ntfy://topic_name
```

**Example:**
```
ntfy://my-backup-alerts
```

### Custom Webhook (JSON)

Send structured notifications to custom endpoints for automation and monitoring.

**URL Format:**
```
jsons://hostname/path/to/endpoint    # HTTPS (secure)
json://hostname/path/to/endpoint     # HTTP
```

**Examples:**
```
jsons://webhook.site/abc-123-def-456
jsons://myserver.com/api/webhooks/backup-alerts
json://localhost:8080/notifications
```

**❌ Common Mistakes:**
```
json://https://webhook.site/abc-123   ← WRONG (double protocol)
https://webhook.site/abc-123          ← Won't work with Apprise
```

**✅ Correct:**
```
jsons://webhook.site/abc-123          ← Use jsons:// for HTTPS webhooks
```

**Payload Structure:**
```json
{
  "version": "1.0",
  "title": "✅ Backup Successful",
  "message": "Archive: backup-2026-01-30\n...",
  "type": "success"
}
```

See [Notification Enhancements](#notification-enhancements) for details on JSON data extraction and automation.

---

## Notification Events

Configure which events trigger notifications for each service:

### Backup Events

- **Backup Success** - Sent when a manual or scheduled backup completes successfully
  - Includes: Archive name, repository, file statistics, completion time
  - Recommended: Disable for frequent backups to avoid notification fatigue

- **Backup Failure** - Sent when a backup fails
  - Includes: Repository name, error details, job ID
  - Recommended: Always enable for critical repositories

### Restore Events

- **Restore Success** - Sent when a restore operation completes
  - Includes: Archive name, repository, destination path

- **Restore Failure** - Sent when a restore operation fails
  - Includes: Archive name, repository, error details

### Schedule Events

- **Schedule Failure** - Sent when a scheduled backup job fails
  - Includes: Schedule name, repository, error details
  - Recommended: Always enable to catch missed backups

---

## Notification Message Format

### Success Notifications

Example backup success notification:

**Title:** `[Production] ✅ Backup Successful` (if title prefix is "[Production]")

**Body:**
```
Archive: manual-backup-2025-11-23T18:28:30
Repository: /local/backups/important-data

Statistics:
  • Original size: 3.94 GB
  • Compressed size: 3.94 GB
  • Deduplicated size: 245.82 MB

✓ Completed at 2025-11-23 18:28:35 UTC
```

### Failure Notifications

Example backup failure notification:

**Title:** `[Production] ❌ Backup Failed`

**Body:**
```
Repository: /local/backups/important-data

Error Details:
  Repository does not exist at /local/backups/important-data

⚠ Failed at 2025-11-23 19:15:42 UTC
```

---

## Title Prefixes

Add a custom prefix to all notification titles from a service to:
- Distinguish between environments (e.g., "[Production]", "[Staging]", "[Dev]")
- Identify the source system (e.g., "[Main Server]", "[Backup NAS]")
- Categorize notifications (e.g., "[Critical]", "[Info]")

**Examples:**
- `[Production]` → "[Production] ✅ Backup Successful"
- `[NAS]` → "[NAS] ❌ Backup Failed"
- `[Dev Server]` → "[Dev Server] ✅ Restore Successful"

---

## Testing Notifications

Always test your notification configuration before relying on it:

1. Click the **Test** button (flask icon) next to the notification service
2. Check your configured service for the test message
3. Verify the notification appears correctly

**Test message format:**
```
Title: 🔔 Borg UI Test Notification
Body: This is a test notification from Borg Web UI.
      If you received this, your notification service is configured correctly!
```

---

## Troubleshooting

### Gmail Notifications Not Sending

**Error:** "SMTP AUTH extension not supported by server"

**Solution:** Add `mode=starttls` to the URL:
```
mailto://user:app_password@gmail.com?smtp=smtp.gmail.com&mode=starttls
```

**Error:** "Failed to send test notification"

**Common causes:**
1. **App Password incorrect** - App Passwords are 16 characters without spaces
2. **2-Step Verification not enabled** - Required for App Passwords
3. **Wrong Gmail account** - Ensure you're using the correct account
4. **Network/firewall issues** - Check that port 587 is accessible

**To generate Gmail App Password:**
1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Enable 2-Step Verification if not already enabled
3. Go to [App Passwords](https://myaccount.google.com/apppasswords)
4. Generate a new App Password for "Mail"
5. Copy the 16-character password (spaces are ignored)

### Slack Notifications Not Sending

**Error:** "Invalid service URL format"

**Solution:** Verify your webhook URL structure. You can extract tokens from a Slack webhook URL:

Slack webhook: `https://hooks.slack.com/services/T00000000/B00000000/XXXX`

Apprise URL: `slack://T00000000/B00000000/XXXX/`

### Discord Notifications Not Sending

**Solution:** Ensure you copied the complete webhook URL from Discord:
1. Go to Discord channel settings > Integrations > Webhooks
2. Copy the webhook URL (should be long, ~120 characters)
3. Extract the webhook ID and token from the URL
4. Format: `discord://webhook_id/webhook_token`

### Notification Service Shows "Last Used: Never"

This means notifications haven't been triggered yet. This is normal for new services or if configured events haven't occurred.

**To verify it works:**
- Click the **Test** button to send a test notification
- Trigger a backup manually to test success/failure notifications

---

## Notification Enhancements

### Include Job Name in Title

When enabled, notification titles include the job or schedule name for easier identification:

**Without job name:**
```
✅ Backup Successful
```

**With job name:**
```
✅ Backup Successful - Daily Backup
```

This helps when:
- Managing multiple scheduled backups
- Filtering notifications in chat services
- Quickly identifying which backup succeeded/failed

**To enable:**
1. Edit a notification service
2. Check **"Include job/schedule name in title"**
3. Save

### JSON Data for Automation

Get structured JSON data in notifications for monitoring tools, automation scripts, and log aggregation.

**✨ How It Works:**

Use **`json://` or `jsons://`** URLs to automatically receive pure JSON data - no checkbox needed!

```
jsons://webhook.site/your-id       ← Secure HTTPS
json://myserver.com:8080/webhook   ← HTTP
```

When you use these URL formats, the notification message body contains **pure JSON string** (compact format):

```json
{"event_type":"backup_success","timestamp":"2026-01-30T12:26:46.986552","repository_name":"/backups/my-repo","archive_name":"backup-2026-01-30","job_name":"Daily Backup","stats":{"original_size":4011450946,"compressed_size":3723854484,"deduplicated_size":0},"completed_at":"2026-01-30T12:30:15.123456"}
```

Other service types (Slack, Discord, email, etc.) receive human-readable notifications **without** JSON data.

#### JSON Data Structure

Different events include different fields:

**backup_success / backup_start / backup_failure:**
```json
{
  "event_type": "backup_success",
  "timestamp": "2026-01-30T12:00:00",
  "repository_name": "my-repo",
  "repository_path": "/backups/my-repo",
  "archive_name": "backup-2026-01-30",
  "job_name": "Daily Backup",
  "source_directories": ["/data", "/home"],
  "stats": {
    "original_size": 1073741824,
    "compressed_size": 536870912,
    "deduplicated_size": 268435456
  },
  "completed_at": "2026-01-30T12:05:00"
}
```

**restore_success / restore_failure:**
```json
{
  "event_type": "restore_success",
  "timestamp": "2026-01-30T12:00:00",
  "repository_name": "my-repo",
  "repository_path": "/backups/my-repo",
  "archive_name": "backup-2026-01-30",
  "job_name": null,
  "target_path": "/restore/destination",
  "completed_at": "2026-01-30T12:15:00"
}
```

**schedule_failure:**
```json
{
  "event_type": "schedule_failure",
  "timestamp": "2026-01-30T12:00:00",
  "schedule_name": "Daily Backup",
  "repository_name": "my-repo",
  "repository_path": "/backups/my-repo",
  "error_message": "Connection timeout",
  "failed_at": "2026-01-30T12:00:30"
}
```

#### Using JSON Webhooks

**Correct URL Format:**

For secure webhooks (HTTPS):
```
jsons://webhook.site/your-unique-id
jsons://myserver.com/api/webhooks/backup-alerts
```

For HTTP webhooks:
```
json://myserver.com:8080/webhooks
```

**❌ Common Mistake:**
```
json://https://webhook.site/abc123  ← WRONG! (double protocol)
```

**✅ Correct:**
```
jsons://webhook.site/abc123  ← Use jsons:// for HTTPS
```

#### Webhook Payload Structure

When using `json://` or `jsons://`, Apprise sends:

```json
{
  "version": "1.0",
  "title": "✅ Backup Successful - Daily Backup",
  "message": "{\"event_type\":\"backup_success\",\"timestamp\":\"2026-01-30T12:00:00\",\"repository_name\":\"my-repo\",\"archive_name\":\"backup-2026-01-30\",\"job_name\":\"Daily Backup\",\"stats\":{\"original_size\":1073741824,\"compressed_size\":536870912}}",
  "attachments": [],
  "type": "success"
}
```

**Fields:**
- `version` - Apprise protocol version (always "1.0")
- `title` - Notification title (includes job name if enabled)
- `message` - **Pure JSON string** (when using `json://` or `jsons://`) OR formatted notification body (for other services)
- `type` - Event severity: `info`, `success`, `warning`, `failure`
- `attachments` - Always empty array (reserved for future use)

#### Parsing JSON Webhooks

> **💡 TIP:** When using JSON webhooks (`json://` or `jsons://`), the `message` field contains **pure JSON string** - just use `JSON.parse(payload.message)` or `json.loads(payload['message'])`. No regex extraction needed!

**Python Example:**
```python
import json

# For JSON webhooks (json:// or jsons://)
def handle_json_webhook(webhook_payload):
    """Parse JSON webhook - message field contains pure JSON."""
    message = webhook_payload.get('message', '')

    # Simple JSON parse - no regex needed!
    backup_data = json.loads(message)

    print(f"Event: {backup_data['event_type']}")
    print(f"Repository: {backup_data['repository_name']}")
    print(f"Archive: {backup_data['archive_name']}")

    if 'stats' in backup_data:
        original_gb = backup_data['stats']['original_size'] / (1024**3)
        print(f"Size: {original_gb:.2f} GB")

    return backup_data

# Example usage
webhook_data = {
    "title": "✅ Backup Successful - Daily Backup",
    "message": '{"event_type":"backup_success","timestamp":"2026-01-30T12:00:00","repository_name":"my-repo","archive_name":"backup-2026-01-30","stats":{"original_size":1073741824}}',
    "type": "success"
}

backup_data = handle_json_webhook(webhook_data)
```

**Node.js Example:**
```javascript
// For JSON webhooks (json:// or jsons://)
function handleJsonWebhook(webhookPayload) {
    const message = webhookPayload.message || '';

    // Simple JSON parse - no regex needed!
    const backupData = JSON.parse(message);

    console.log(`Event: ${backupData.event_type}`);
    console.log(`Repository: ${backupData.repository_name}`);
    console.log(`Archive: ${backupData.archive_name}`);

    if (backupData.stats) {
        const originalGB = backupData.stats.original_size / (1024**3);
        console.log(`Size: ${originalGB.toFixed(2)} GB`);
    }

    return backupData;
}

// Example usage
const webhookData = {
    title: "✅ Backup Successful - Daily Backup",
    message: '{"event_type":"backup_success","timestamp":"2026-01-30T12:00:00","repository_name":"my-repo","archive_name":"backup-2026-01-30","stats":{"original_size":1073741824}}',
    type: "success"
};

const backupData = handleJsonWebhook(webhookData);
```

**Bash/jq Example:**
```bash
#!/bin/bash
# Parse JSON webhook POST request (for json:// or jsons:// URLs)

# Assuming webhook payload is in $1
# For JSON webhooks, message field contains pure JSON - no extraction needed!
EVENT_TYPE=$(echo "$1" | jq -r '.message | fromjson | .event_type')
REPO=$(echo "$1" | jq -r '.message | fromjson | .repository_name')
ARCHIVE=$(echo "$1" | jq -r '.message | fromjson | .archive_name')
ORIGINAL_SIZE=$(echo "$1" | jq -r '.message | fromjson | .stats.original_size')

echo "Event: $EVENT_TYPE"
echo "Repository: $REPO"
echo "Archive: $ARCHIVE"
echo "Size: $(($ORIGINAL_SIZE / 1024 / 1024 / 1024)) GB"

# Or parse message once and reuse:
BACKUP_DATA=$(echo "$1" | jq -r '.message | fromjson')
echo "Full data: $BACKUP_DATA"
```

#### Service-Specific JSON Formatting

**For JSON Webhooks (`json://` or `jsons://`):**
- The `message` field contains **pure JSON string** (compact, no markdown)
- Simple to parse: `JSON.parse(payload.message)` in JavaScript, `json.loads(payload['message'])` in Python
- Optimized for automation and monitoring tools

**For Other Services (Email, Slack, Discord, etc.):**
- The `message` field contains **formatted notification body** with embedded JSON in markdown code blocks
- JSON appears as collapsible `<details>` in email, or code blocks in chat
- Human-readable with pretty-printed JSON (indented)
- Automation tools need regex extraction (see examples for `https://` webhooks below)

#### Extracting JSON from Non-JSON Webhooks

If you're using regular webhooks (`https://`, `form://`, etc.) instead of JSON webhooks, the JSON is embedded in markdown:

**Python Example (for https:// webhooks):**
```python
import re
import json

def extract_json_from_markdown(webhook_payload):
    """Extract JSON from markdown code block in message."""
    message = webhook_payload.get('message', '')

    # Find JSON code block in markdown
    match = re.search(r'```json\n(.*?)\n```', message, re.DOTALL)
    if match:
        return json.loads(match[1])
    return None

backup_data = extract_json_from_markdown(webhook_payload)
```

**Why Two Formats?**

1. **JSON Webhooks** - Optimized for automation (compact JSON, easy parsing)
2. **Other Services** - Optimized for humans (formatted notifications with pretty-printed JSON)

#### Testing JSON Webhooks

**Quick Test Setup:**

1. Go to [webhook.site](https://webhook.site)
2. Copy your unique URL (e.g., `https://webhook.site/abc-123`)
3. In Borg UI → Settings → Notifications → Add Service:
   ```
   Name: JSON Test
   URL: jsons://webhook.site/abc-123
   ✅ Enable notifications
   ✅ Include job/schedule name in title
   ✅ Include JSON data in message body
   ✅ Notify on: Backup Success
   ```
4. Click **Test** or run a backup
5. Check webhook.site to see the full payload

**What You'll See:**
```json
{
  "version": "1.0",
  "title": "🚀 Backup Started - My Backup",
  "message": "**Archive:** backup-2026-01-30...\n\n**📊 JSON Data (for automation)**\n```json\n{\"event_type\": \"backup_start\", ...}\n```",
  "type": "info"
}
```

#### Use Cases

**1. Prometheus/Grafana Monitoring:**
Extract metrics from backup stats:
```python
stats = backup_data.get('stats', {})
prometheus_metrics = f"""
backup_original_size_bytes{{repo="{repo}"}} {stats['original_size']}
backup_compressed_size_bytes{{repo="{repo}"}} {stats['compressed_size']}
backup_deduplicated_size_bytes{{repo="{repo}"}} {stats['deduplicated_size']}
"""
```

**2. Log Aggregation (ELK, Splunk):**
Forward structured events to centralized logging:
```python
import logging
logger.info("Backup completed", extra=backup_data)
```

**3. Alerting Rules:**
Implement custom alert logic:
```python
if backup_data['event_type'] == 'backup_failure':
    if 'lock' in backup_data['error_message'].lower():
        send_page_to_oncall("Backup locked - manual intervention needed")
```

**4. Backup Reporting:**
Generate daily/weekly backup reports:
```python
daily_backups.append({
    'time': backup_data['completed_at'],
    'repo': backup_data['repository_name'],
    'size_gb': backup_data['stats']['original_size'] / (1024**3)
})
```

---

## Best Practices

1. **Test Before Relying** - Always send a test notification before depending on alerts

2. **Enable Failure Notifications** - At minimum, enable backup and schedule failure notifications

3. **Disable Success for Frequent Backups** - If you backup hourly, success notifications create noise

4. **Use Multiple Services** - Configure backup notifications to email AND Slack for redundancy

5. **Set Title Prefixes** - Distinguish notifications from different systems

6. **Monitor "Last Used"** - Check the "Last Used" timestamp periodically to ensure notifications are working

7. **Secure Service URLs** - Notification URLs contain credentials. Keep them secure.

8. **Test After Updates** - Re-test notifications after updating Borg Web UI

---

## Security Considerations

- **Service URLs contain credentials** - Store them securely, don't share publicly
- **Database encryption** - Service URLs are stored in the database; secure the `/data` volume
- **Access controls** - Only admins can configure notifications
- **HTTPS in production** - Use HTTPS/reverse proxy to protect the web interface
- **Webhook authentication** - Use authenticated webhooks when possible (e.g., Discord, Slack)

---

## Advanced Configuration

### Multiple Notification Services

You can add multiple notification services for different purposes:

**Example setup:**
1. **Gmail** - Critical alerts only (backup failures, schedule failures)
2. **Slack** - All events for team visibility
3. **Pushover** - Mobile notifications for urgent issues

### Per-Repository Notifications

Currently, notifications are global for all repositories. To achieve per-repository notifications:

1. Create multiple notification services with descriptive names
2. Use title prefixes to identify the source
3. Manually enable/disable services based on needs

**Future enhancement:** Per-repository notification configuration is planned.

---

## Need Help?

- **Full Apprise Documentation**: [Apprise Wiki](https://github.com/caronc/apprise/wiki)
- **Service-Specific Guides**: [Apprise Notifications](https://github.com/caronc/apprise/wiki#notification-services)
- **GitHub Issues**: [Report problems](https://github.com/karanhudia/borg-ui/issues)
- **GitHub Discussions**: [Ask questions](https://github.com/karanhudia/borg-ui/discussions)

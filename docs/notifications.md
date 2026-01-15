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

### Custom Webhook

**URL Format:**
```
json://hostname/path/to/endpoint
xml://hostname/path/to/endpoint
```

**Example:**
```
json://myserver.com:8080/api/notifications
```

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

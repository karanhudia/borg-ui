# Beta Features

Beta features allow gradual rollout of new functionality while maintaining stability. Admin users can enable beta features via the Settings UI to test new capabilities.

## Available Features

### MQTT & Home Assistant Integration (Beta)

> - Publish backup status and repository metrics to MQTT brokers.
> 
> - Monitor your backups directly in Home Assistant with automatic sensor discovery and real-time status updates.


**Status:** Beta
**Default:** Disabled
**Added:** ~

**Features:**
- Publish backup status, progress, and ETA to MQTT topics
- Automatic Home Assistant MQTT discovery for sensors
- Per-repository sensors for status, size, archive count, and last backup time
- Server-wide sensors for overall backup state
- TLS support for secure MQTT connections
- Authentication support (username/password)
- Configurable QoS and base topic

**Home Assistant Sensors:**

**Server Sensors:**
- `sensor.borg_last_backup` - Timestamp of last completed backup
- `binary_sensor.borg_backup_success` - Success/failure state of last backup

**Per-Repository Sensors:**
- `sensor.borg_repo_{id}_status` - Repository health status (healthy, warning, stale, failed, no_backup)
- `sensor.borg_repo_{id}_size` - Repository size in bytes
- `sensor.borg_repo_{id}_archives` - Number of archives
- `sensor.borg_repo_{id}_last_backup` - Timestamp of last backup
- `sensor.borg_repo_{id}_backup_status` - Current backup status (idle, initializing, processing files, finalizing)
- `sensor.borg_repo_{id}_backup_progress` - Backup progress percentage (0-100)
- `sensor.borg_repo_{id}_backup_eta` - Estimated time of arrival for current backup

**Setup Instructions:**

1. **Enable MQTT in Settings:**
   - Navigate to **Settings** > **System** tab
   - Scroll to **MQTT Configuration** section
   - Toggle "MQTT Enabled"

2. **Configure MQTT Broker:**
   - Enter your MQTT broker URL (e.g., `localhost`, `192.168.1.100`, `mqtt.example.com`)
     Note: **don't** enter the scheme (e.g., `mqtt://`)
   - Set the broker port (default: `1883` for plaintext, `8883` for TLS)
   - If your broker requires authentication, enter username and password
   - Configure TLS settings if using encrypted connections

3. **Configure Home Assistant:**
   - Ensure Home Assistant is running and can reach your MQTT broker
   - Home Assistant will automatically discover Borg UI sensors
   - Sensors will appear in **Settings** > **Devices & Services** > **MQTT**
   - Add the discovered devices to your dashboard

4. **Verify Integration:**
   - View MQTT messages in your broker (e.g., using MQTT Explorer)
   - Verify sensors appear in Home Assistant with current data

**MQTT Topics:**

All MQTT messages are published under the base topic (default: `borg-ui`):

- `{base_topic}/status` - Server connection status (online/offline)
- `{base_topic}/backup/status` - Current backup status
- `{base_topic}/backup/progress` - Backup progress and ETA
- `{base_topic}/backup/last` - Last backup information
- `{base_topic}/backup/success` - Success/failure state
- `{base_topic}/repositories/{id}/status` - Repository health status
- `{base_topic}/repositories/{id}/size` - Repository size metrics
- `{base_topic}/repositories/{id}/archives` - Archive count
- `{base_topic}/repositories/{id}/last_backup` - Last backup timestamp
- `{base_topic}/repositories/{id}/backup/status` - Backup status
- `{base_topic}/repositories/{id}/backup/progress` - Backup progress

**TLS Configuration:**

For secure MQTT connections (recommended for production):

- **TLS Enabled**: Check this box to enable TLS
- **TLS CA Cert**: Path to CA certificate file (e.g., `/local/ca.crt`)
- **TLS Client Cert**: Path to client certificate file (e.g., `/local/client.crt`)
- **TLS Client Key**: Path to client private key file (e.g., `/local/client.key`)

**Note:** Certificate files must be accessible from within the container. Use paths starting with `/local/` to access files on your host filesystem.

**Troubleshooting:**

- **Connection Failed**: Verify broker URL and port are correct
- **Authentication Failed**: Check username and password
- **TLS Errors**: Verify certificate paths and permissions
- **No Data**: Verify MQTT is enabled in Borg UI and broker is reachable

**Security Considerations:**

- Use TLS for all production deployments
- Use strong authentication (username/password)
- Restrict broker access to trusted networks

### New Repository Wizard (Beta)

A redesigned step-based repository wizard with improved UX, validation, and mobile support.

**Status:** Beta
**Default:** Disabled
**Added:** v1.46.0

**Features:**
- Step-based workflow with progress tracking
- Card-based UI for location selection
- Improved validation and error messages
- Responsive mobile design
- Live command preview
- Better SSH connection management

## Enabling Beta Features

**For Admin Users:**

1. Navigate to **Settings** > **Appearance** tab
2. Scroll to the **Beta Features** section
3. Toggle "Use New Repository Wizard" to enable/disable
4. Changes take effect immediately (no rebuild required)

**Note:** Only admin users can access beta feature toggles.

## Beta Testing

To help test beta features:

1. Enable the feature via Settings UI
2. Report issues at https://github.com/karanhudia/borg-ui/issues
3. Test thoroughly before using in production
4. You can switch back to stable anytime via Settings

## Feature Lifecycle

Beta features follow this progression:

1. **Beta** (current) - Default disabled, admin opt-in testing
2. **General Availability** - Default enabled for all users
3. **Deprecated** - Legacy code scheduled for removal
4. **Removed** - Only new version remains

Current timeline:
- New Repository Wizard: Beta → GA in v1.47.0 → Legacy removed in v1.48.0

## Notes

- Beta features are runtime settings (no rebuild required)
- Stored in database, persists across restarts
- No data loss when switching between versions
- Both versions use the same database
- Can switch back anytime via Settings UI

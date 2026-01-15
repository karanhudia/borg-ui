# Beta Features

Beta features allow gradual rollout of new functionality while maintaining stability. Admin users can enable beta features via the Settings UI to test new capabilities.

## Available Features

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

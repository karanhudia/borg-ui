# Borgmatic UI - System Design

## Overview
Borgmatic UI is a web-based interface for managing Borg backup operations. The design follows a guided workflow that helps users understand and complete each step of the backup process.

## Core Design Principles

1. **Guided Workflow**: Users are guided through a logical sequence of steps
2. **Progressive Disclosure**: Features unlock as prerequisites are met
3. **Configuration-First**: All functionality depends on having a valid configuration
4. **Single SSH Key**: One SSH key per system to reduce complexity
5. **Clear Error Messages**: Show actual errors without interpretation
6. **Real-time Feedback**: Live logging for backup operations

## User Flow & Tab Order

### 1. Dashboard (Always Enabled)
- System overview and metrics
- Shows current status of backups
- Quick access to recent operations

### 2. Configuration (Always Enabled)
**Purpose**: Define what to backup, where to backup, retention rules, and schedules

**Features**:
- User can create and manage multiple configuration files
- **One configuration must be selected as default**
- Only when a default config is selected, other tabs become enabled
- Configuration selector dropdown at the top
- YAML editor with validation
- Templates for common configurations

**Requirements**:
- Valid configuration required to enable other tabs
- Configuration includes:
  - `sources`: Directories to backup
  - `repositories`: Where to store backups (defined later in Repositories tab)
  - `retention`: How long to keep backups
  - `hooks`: Pre/post backup scripts

**State Management**:
```
NO_CONFIG → CONFIG_INVALID → CONFIG_VALID (enables other tabs)
```

### 3. SSH Keys (Enabled after valid config)
**Purpose**: One-time SSH key setup for remote repositories

**Design Decisions**:
- **Only ONE SSH key per system** - Simplifies management
- Once created, this key is used for all remote connections
- No option to create multiple keys
- If key exists, show key details (read-only)
- If no key exists, show "Create SSH Key" button

**Features**:
- Generate ed25519 SSH key (one-time operation)
- Display public key for copying
- Show key fingerprint
- Test key connectivity (optional)
- **No delete/recreate** - Key persists for all remote operations

**UI States**:
```
NO_KEY → Show "Create SSH Key" button
KEY_EXISTS → Show key info (public key, fingerprint) - Read Only
```

### 4. SSH Connections (Enabled after valid config)
**Purpose**: Define remote machines that can be used for repositories

**Features**:
- Add new SSH connections (hostname, username, port)
- Uses the single SSH key created in step 3
- **No SSH key selection** - Automatically uses the system's SSH key
- Test connection before saving
- Display connection status (Connected, Failed, Unknown)
- List all configured connections

**Connection Form**:
- Hostname/IP (required)
- Username (required)
- Port (default: 22)
- Test Connection button (validates before save)

**UI Flow**:
```
If NO_SSH_KEY:
  Show warning: "Please create an SSH key first in the SSH Keys tab"
  Disable "Add Connection" button

If SSH_KEY_EXISTS:
  Allow adding connections
  All connections use the single SSH key
```

### 5. Repositories (Enabled after valid config)
**Purpose**: Define where backups will be stored

**Context for Users**:
- Display explanation: "A repository is where your backed-up data will be stored. Think of it as a secure storage location for all your backup archives."
- Show what will be backed up (from config sources)

**Two Repository Types**:

#### A. Local Repository
- Path on the current machine
- Simple validation: Check if path exists or can be created
- Example: `/srv/borg_backup`
- Command: `borg init -e repokey /srv/borg_backup`

#### B. Remote Repository (SSH-based)
- **Requires valid SSH connection** (from SSH Connections tab)
- Dropdown to select existing SSH connection
- Path on remote machine
- Validation: Check if SSH connection is active
- Example: `ssh://karanhudia@192.168.1.250/mnt/mydisk/data/immich-backup`
- Command: `borg init --encryption=repokey ssh://karanhudia@192.168.1.250/mnt/mydisk/data/immich-backup`

**Repository Creation Form**:
```
Repository Type: [Local] [Remote]

IF Local:
  - Path: [text input]
  - Encryption: repokey (default)

IF Remote:
  - SSH Connection: [dropdown - populated from SSH Connections]
  - Remote Path: [text input]
  - Encryption: repokey (default)

Validations:
  - Local: Path must be valid or creatable
  - Remote: SSH connection must exist and be active

[Initialize Repository] button
```

**Post-Creation**:
- Repository is added to the configuration
- Show success message with repository path
- User can now proceed to backups

### 6. Backups (Enabled after valid config + repository exists)
**Purpose**: Execute and monitor backup operations

**Features**:
- Start new backup (uses default config + selected repository)
- **Verbose mode logging** - Run with `--verbosity 1`
- Real-time log streaming
- Progress indicators
- Backup history

**Backup Execution**:
```
Command: borgmatic --verbosity 1 --files

Backend Process:
1. Execute borgmatic command
2. Stream output to log file
3. Frontend polls log file every 2-3 seconds
4. Display logs in real-time in UI
5. Show completion status
```

**Log Display**:
- Terminal-style output
- Auto-scroll to latest
- Plain error messages (no interpretation)
- Timestamp for each log entry
- Copy log functionality

### 7. Archives (Enabled after first backup)
**Purpose**: Browse and manage backup archives

**Features**:
- List all backup archives
- Browse files within archives
- View archive metadata
- Delete old archives (with confirmation)

### 8. Restore (Enabled after archives exist)
**Purpose**: Restore data from backups

**Features**:
- Select archive to restore from
- Browse and select specific files/directories
- Choose restore destination
- Execute restore with logging

### 9. Schedule (Enabled after valid config)
**Purpose**: Automate backups with cron jobs

**Features**:
- Create scheduled backup jobs
- Cron expression builder
- Enable/disable schedules
- View upcoming scheduled runs

### 10. Settings (Always Enabled)
**Purpose**: System configuration and user management

**Features**:
- System settings (timeouts, retention, etc.)
- User management (for admins)
- View system information

## State Management & Tab Enablement

```typescript
interface AppState {
  hasValidConfig: boolean        // Enables SSH, Connections, Repos, Backups, Schedule
  hasSSHKey: boolean             // Required for SSH Connections
  hasRepositories: boolean       // Required for Backups
  hasArchives: boolean           // Enables Restore
}

// Tab Enablement Logic
Dashboard: Always enabled
Configuration: Always enabled
SSH Keys: hasValidConfig
SSH Connections: hasValidConfig
Repositories: hasValidConfig
Backups: hasValidConfig && hasRepositories
Archives: hasValidConfig && hasRepositories
Restore: hasValidConfig && hasArchives
Schedule: hasValidConfig
Settings: Always enabled
```

## Key Commands Reference

```bash
# Check versions
borg --version
borgmatic --version

# Validate configuration
borgmatic config validate

# Edit configuration
nano /etc/borgmatic/config.yaml

# Create SSH key (one-time)
sudo ssh-keygen -t ed25519 -C "root@odroidm1"

# Copy SSH key to remote
ssh-copy-id karanhudia@192.168.1.250

# Initialize local repository
borg init -e repokey /srv/borg_backup

# Initialize remote repository
borg init --encryption=repokey ssh://karanhudia@192.168.1.250/mnt/mydisk/data/immich-backup

# Run backup with verbose logging
borgmatic --verbosity 1 --files
```

## Error Handling Philosophy

**DO**:
- Show exact error messages from borgmatic/borg
- Display full command output
- Log all operations

**DON'T**:
- Add "user-friendly" interpretations of errors
- Guess what might have caused the error
- Hide technical details

**Example**:
```
❌ Bad: "Failed to connect. Check if the remote server is running."
✅ Good: "Error: Connection refused (ssh: connect to host 192.168.1.250 port 22: Connection refused)"
```

## Implementation Priorities

### Phase 1: Core Workflow (High Priority)
1. Configuration management with default selection
2. Tab enablement based on state
3. SSH key creation (single key)
4. SSH connections management
5. Repository creation (local + remote)
6. Basic backup execution with logging

### Phase 2: Enhanced Features (Medium Priority)
1. Real-time log streaming
2. Backup history and archives
3. Restore functionality
4. Schedule management

### Phase 3: Polish (Low Priority)
1. Better UI/UX refinements
2. Advanced configuration options
3. Performance optimizations

## Technical Implementation Notes

### Backend Requirements
1. **Configuration API**:
   - CRUD for configuration files
   - Set/get default configuration
   - Validate configuration

2. **SSH Key API**:
   - Generate SSH key (one-time)
   - Get public key
   - Check if key exists

3. **SSH Connections API**:
   - CRUD for connections
   - Test connection
   - Automatically use system SSH key

4. **Repository API**:
   - Initialize local repository
   - Initialize remote repository (requires SSH connection)
   - List repositories
   - Validate repository

5. **Backup API**:
   - Start backup (verbose mode)
   - Stream logs to file
   - Get backup status
   - List backup history

6. **Log Streaming**:
   - Append borgmatic output to log file
   - Provide endpoint to fetch new log entries
   - Frontend polls every 2-3 seconds

### Frontend Requirements
1. **State Management**:
   - Track configuration state
   - Track SSH key existence
   - Track repository availability
   - Enable/disable tabs based on state

2. **Tab Navigation**:
   - Visual indicators for disabled tabs
   - Tooltips explaining why tabs are disabled
   - Progress indicator showing workflow completion

3. **Real-time Updates**:
   - Poll log endpoint during backups
   - Auto-scroll log display
   - Show connection status
   - Update backup progress

## User Experience Enhancements

### Onboarding Flow
1. First-time user sees Dashboard with welcome message
2. "Get Started" button guides to Configuration
3. After config saved, show success + "Next: Create Repository"
4. After repository created, show "Ready to Backup!"
5. Highlight enabled tabs as user progresses

### Visual Feedback
- Disabled tabs: Gray out with lock icon
- Enabled tabs: Normal colors
- Active workflow step: Highlight/pulse
- Completion badges: Checkmarks for completed steps

### Help Text
- Each tab shows contextual help at the top
- Explain what the step is for
- Show prerequisites if tab is disabled
- Link to documentation

## Repository Structure

```
/Users/karanhudia/Documents/Projects/borg-ui/
├── SYSTEM_DESIGN.md (this file)
├── README.md (reference to this design)
├── app/
│   ├── api/
│   │   ├── config.py (configuration management)
│   │   ├── ssh_keys.py (single SSH key operations)
│   │   ├── ssh_connections.py (connection management)
│   │   ├── repositories.py (repository operations)
│   │   ├── backups.py (backup execution & logging)
│   │   └── logs.py (log streaming)
│   └── models/ (database models)
└── frontend/
    └── src/
        ├── pages/ (all tab pages)
        ├── components/ (reusable components)
        ├── hooks/ (state management)
        └── services/ (API calls)
```

## Next Steps

1. Review and approve this design document
2. Update README.md to reference this design
3. Create implementation task list
4. Begin Phase 1 implementation
5. Delete temporary documents after completion
6. Keep this SYSTEM_DESIGN.md as permanent reference

---

**Document Status**: Draft for Review
**Last Updated**: 2025-01-15
**Version**: 1.0

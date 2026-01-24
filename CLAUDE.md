- **NEVER commit or push without asking first**
- Always run test suite before pushing to github
- Always add a new test or update existing when a new feature is added or a bug is fixed
- Ask every time you push if a release is required, if i answer yes, you decide if minor, major or patch and do it

## Release Process
- Creating a git tag automatically triggers a GitHub release
- Use `git tag vX.Y.Z` to create the tag
- Tag format: semantic versioning (vMAJOR.MINOR.PATCH)
  - MAJOR: Breaking changes or major new features
  - MINOR: New features, backward compatible
  - PATCH: Bug fixes and small improvements
- Push tags with `git push --tags`

## Repository Wizard (New Implementation)

### Overview
Implemented a new step-based wizard for repository creation/import/editing with card-based visual UI.

### Key Components Created
1. **CompressionSettings.tsx** - Reusable compression configuration component
   - Handles all compression algorithms (lz4, zstd, zlib, lzma, auto, obfuscate, none)
   - Compression levels, auto-detect, obfuscate spec
   - Shows final compression string preview

2. **CommandPreview.tsx** - Shows Borg commands that will run
   - Init command for create mode
   - Create command preview
   - Uses existing `generateBorgCreateCommand` utility

3. **SourceDirectoriesInput.tsx** - Manages source directories
   - Add/remove directories with validation
   - FileExplorerDialog integration
   - Warning when no directories configured

4. **ExcludePatternInput.tsx** - Manages exclude patterns
   - Add/remove patterns
   - FileExplorerDialog integration

### Wizard Structure (RepositoryWizard.tsx)

**Step 1: Repository Location**
- Name and mode (Full/Observe Only)
- Visual cards: Borg UI Server (local) vs SSH Remote Storage
- SSH connections dropdown (no manual host/port entry)
- Path input with file browser

**Step 2: Data Source** (only for full mode, not import/observe)
- Visual cards: Borg UI Server (local) vs Remote Machine
- For local: Shows SourceDirectoriesInput
- For remote: SSH connections dropdown + note about remote execution

**Step 3: Security**
- Encryption (create mode)
- Passphrase (required for encrypted)
- Keyfile upload (import mode)
- Remote path (optional borg executable path)

**Step 4: Backup Configuration** (only for local data source)
- CompressionSettings component
- ExcludePatternInput component
- Custom Borg flags

**Step 5: Review**
- CommandPreview component (local source only)
- Summary card with all settings
- Success/info alerts

### Important Decisions
- **NON-NEGOTIABLE**: Must reuse existing components (FileExplorerDialog, compression logic, command generation)
- **SSH connections dropdown**: Use for both repository location AND data source
- **Card-based UI**: Visual clarity preferred over text-heavy forms
- **Step adaptation**: Steps dynamically adjust based on mode (full/observe/import)
- **Validation**: Array.isArray() checks on sshConnections before .map() calls
- **Client-to-client limitation**: If repository is on a remote client, data source can ONLY be:
  - Local (Borg UI Server), OR
  - The SAME remote client (same-machine backup)
  - Backing up from one remote client to another is NOT supported (too much overhead)

### Integration
- Buttons in Repositories.tsx: "Create Repository (New)", "Import Existing (New)", "Create (Old)"
- Old form still exists for comparison/fallback
- Uses existing FileExplorerDialog, sshKeysAPI.getSSHConnections()

### Data Flow
- Repository location: Where backups are stored (local/SSH)
- Data source: Where data comes from (local/remote machine)
- Remote source submits `source_connection_id` to backend
- Local source submits `source_directories` array

### Current Status
- Frontend complete and deployed
- Backend needs implementation for remote source orchestration (future work)
- Wizard handles create/import/edit modes
- All original features from old form are included
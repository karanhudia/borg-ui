import { useEffect, useMemo, useState } from 'react'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  ButtonBase,
  Checkbox,
  Chip,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Radio,
  RadioGroup,
  Select,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import {
  ChevronRight,
  Container as ContainerIcon,
  Database as DatabaseIcon,
  FileText,
  HardDrive,
  Info,
  Laptop,
  Lock,
  Plus,
  Search,
  Server,
  Trash2,
  X,
} from 'lucide-react'
import type { TFunction } from 'i18next'

import CodeEditor from '../../../components/shared/CodeEditor'
import DestinationSelect, {
  type DestinationOption,
} from '../../../components/shared/DestinationSelect'
import ManagedAgentSelect from '../../../components/shared/ManagedAgentSelect'
import PathSelectorField from '../../../components/shared/PathSelectorField'
import ResponsiveDialog from '../../../components/shared/ResponsiveDialog'
import SshConnectionSelect from '../../../components/shared/SshConnectionSelect'
import {
  type AgentMachineResponse,
  type FilesystemSnapshotCapabilitiesResponse,
  sourceDiscoveryAPI,
  type SourceDiscoveryDatabase,
  type SourceDiscoveryResponse,
  type SourceDiscoveryScriptDraft,
} from '../../../services/api'
import type {
  DatabaseCaptureMode,
  Repository,
  SourceContainerSelection,
  SourceDatabaseSelection,
  SourceLocation,
  SourceSnapshotConfig,
  SourceType,
} from '../../../types'
import type { ScriptOption, SSHConnection, WizardState } from '../types'
import type { SourceScriptCreateInput } from './types'
import { DatabaseBrandTile } from './DatabaseBrandTile'
import {
  DatabaseScanDialog,
  type DatabaseScanChoice,
  type ScanTargetState,
} from './DatabaseScanDialog'

type SourceChoiceView = 'paths' | 'database' | 'database-detail' | 'container'
type ScriptMode = 'create' | 'reuse' | 'skip'
type SourceKey = 'local' | `remote:${number}` | `agent:${number}`
type SnapshotProviderDraft = 'none' | 'btrfs' | 'zfs'

interface QueuedDatabaseScriptDraft {
  databaseName: string
  database: SourceDatabaseSelection
  preBackup: SourceDiscoveryScriptDraft
  postBackup: SourceDiscoveryScriptDraft
  preScriptName: string
  postScriptName: string
  preScriptContent: string
  postScriptContent: string
}

interface DatabaseScriptAssignment {
  preBackupScriptId: number | null
  postBackupScriptId: number | null
  preBackupScriptParameters?: Record<string, string> | null
  postBackupScriptParameters?: Record<string, string> | null
}

interface QueuedContainerScriptDraft {
  container: SourceContainerSelection
  preBackup: SourceDiscoveryScriptDraft
  postBackup: SourceDiscoveryScriptDraft
  preScriptName: string
  postScriptName: string
}

interface ContainerScriptAssignment {
  preBackupScriptId: number | null
  postBackupScriptId: number | null
  preBackupScriptParameters?: Record<string, string> | null
  postBackupScriptParameters?: Record<string, string> | null
}

const DEFAULT_SNAPSHOT_STAGING_PATH = '/var/tmp/borg-ui/snapshots'
const DEFAULT_CONTAINER_EXPORT_ROOT = '/var/tmp/borg-ui/container-exports'

interface SnapshotDraft {
  provider: SnapshotProviderDraft
  stagingPath: string
  dataset: string
  mountpoint: string
  recursive: boolean
}

const emptySnapshotDraft = (): SnapshotDraft => ({
  provider: 'none',
  stagingPath: DEFAULT_SNAPSHOT_STAGING_PATH,
  dataset: '',
  mountpoint: '',
  recursive: false,
})

function snapshotDraftFromLocation(location?: SourceLocation | null): SnapshotDraft {
  if (!location?.snapshot) return emptySnapshotDraft()
  if (location.snapshot.provider === 'btrfs') {
    return {
      provider: 'btrfs',
      stagingPath: location.snapshot.staging_path || DEFAULT_SNAPSHOT_STAGING_PATH,
      dataset: '',
      mountpoint: '',
      recursive: Boolean(location.snapshot.recursive),
    }
  }
  return {
    provider: 'zfs',
    stagingPath: DEFAULT_SNAPSHOT_STAGING_PATH,
    dataset: location.snapshot.dataset || '',
    mountpoint: location.snapshot.mountpoint || '',
    recursive: Boolean(location.snapshot.recursive),
  }
}

function snapshotFromDraft(
  draft: SnapshotDraft,
  previousSnapshot?: SourceSnapshotConfig
): SourceSnapshotConfig | undefined {
  if (draft.provider === 'none') return undefined
  if (draft.provider === 'btrfs') {
    return {
      provider: 'btrfs',
      staging_path: draft.stagingPath.trim() || DEFAULT_SNAPSHOT_STAGING_PATH,
      recursive: draft.recursive,
    }
  }
  const dataset = draft.dataset.trim()
  const mountpoint = draft.mountpoint.trim()
  if (!dataset || !mountpoint) {
    return previousSnapshot?.provider === 'zfs' ? previousSnapshot : undefined
  }
  return {
    provider: 'zfs',
    dataset,
    mountpoint,
    recursive: draft.recursive,
  }
}

function isSnapshotDraftValid(draft: SnapshotDraft, sourceKey: SourceKey): boolean {
  if (sourceKey !== 'local' || draft.provider !== 'zfs') return true
  return Boolean(draft.dataset.trim() && draft.mountpoint.trim())
}

interface SourceSelectionDialogProps {
  open: boolean
  wizardState: WizardState
  sshConnections: SSHConnection[]
  agentMachines: AgentMachineResponse[]
  fullRepositories: Repository[]
  scripts: ScriptOption[]
  loadingScripts: boolean
  onClose: () => void
  updateState: (updates: Partial<WizardState>) => void
  onCreateScript: (input: SourceScriptCreateInput) => Promise<{ id: number }>
  t: TFunction
  /** Override the initial view. Defaults to 'paths'. Used by Storybook to deep-link into specific views. */
  initialView?: SourceChoiceView
  /** Override the initial database scan target. Defaults to local. Used by Storybook for specific states. */
  initialScanTarget?: ScanTargetState
  /** Open the local capture-mode accordion initially. Used by Storybook for specific states. */
  initialCaptureModeExpanded?: boolean
  /** Open directly on a database detail state. Used by Storybook for specific states. */
  initialSelectedDatabase?: SourceDiscoveryDatabase
  /** Open the scan sub-dialog on mount. Used by Storybook to capture stacked states. */
  initialScanDialogOpen?: boolean
  canUseManagedAgents?: boolean
  canUseMixedSourceTypes?: boolean
}

function scriptPayload(draft: SourceDiscoveryScriptDraft, name: string): SourceScriptCreateInput {
  return {
    name,
    description: draft.description,
    content: draft.content,
    timeout: draft.timeout,
    run_on: 'always',
    category: 'template',
  }
}

function cleanOptionalScriptId(value?: number | null | ''): number | null {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

function cleanScriptParameters(parameters?: Record<string, string> | null): Record<string, string> {
  return Object.fromEntries(
    Object.entries(parameters || {})
      .map(([key, value]) => [key.trim(), String(value).trim()] as const)
      .filter(([key, value]) => key.length > 0 && value.length > 0)
  )
}

function databaseDefaultDumpRoot(database: SourceDiscoveryDatabase): string {
  return (
    database.source_directories[0]?.replace(/\/+$/, '') ||
    `/var/tmp/borg-ui/database-dumps/${database.id}`
  )
}

function databaseDetectedPath(database: SourceDiscoveryDatabase): string | null {
  const path = database.detection_source?.trim()
  return path?.startsWith('/') ? path : null
}

function databaseDisplayTitle(
  database: SourceDiscoveryDatabase | null | undefined,
  t: TFunction
): string {
  return (
    database?.display_name?.trim() ||
    database?.engine?.trim() ||
    t('backupPlans.sourceChooser.databaseTitle')
  )
}

function sqliteDumpSlug(detectedSourcePath: string): string {
  const filename = detectedSourcePath.trim().replace(/\/+$/, '').split('/').filter(Boolean).pop()
  const withoutExtension = (filename || 'database').replace(/\.(db|sqlite|sqlite3)$/i, '')
  const slug = withoutExtension
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return slug || 'database'
}

function usedDatabasePaths(
  locations: SourceLocation[],
  selectedDatabase: SourceDiscoveryDatabase
): Set<string> {
  const paths = new Set<string>()
  locations.forEach((location) => {
    if (
      location.database?.template_id === selectedDatabase.id &&
      location.database.detected_source_path === selectedDatabase.detection_source
    ) {
      return
    }

    location.paths.forEach((path) => paths.add(path))
    const database = location.database
    if (!database) return
    if (database.dump_path) paths.add(database.dump_path)
    database.backup_paths?.forEach((path) => paths.add(path))
  })
  return paths
}

function uniqueDatabaseDumpPath(
  candidate: string,
  locations: SourceLocation[],
  selectedDatabase: SourceDiscoveryDatabase
): string {
  const usedPaths = usedDatabasePaths(locations, selectedDatabase)
  if (!usedPaths.has(candidate)) return candidate

  for (let suffix = 2; suffix < 1000; suffix += 1) {
    const nextCandidate = `${candidate}-${suffix}`
    if (!usedPaths.has(nextCandidate)) return nextCandidate
  }

  return `${candidate}-1000`
}

function defaultDatabaseDumpPath(
  database: SourceDiscoveryDatabase,
  existingLocations: SourceLocation[]
): string {
  const dumpRoot = databaseDefaultDumpRoot(database)
  const detectedSourcePath = databaseDetectedPath(database)

  if (database.id !== 'sqlite' || !detectedSourcePath) {
    return dumpRoot
  }

  return uniqueDatabaseDumpPath(
    `${dumpRoot}/${sqliteDumpSlug(detectedSourcePath)}`,
    existingLocations,
    database
  )
}

function defaultDatabaseScriptParameters(
  database: SourceDatabaseSelection,
  hook: 'pre' | 'post'
): Record<string, string> {
  if (hook !== 'pre') return {}
  if (database.template_id !== 'sqlite' || !database.detected_source_path) return {}
  return { SQLITE_DATABASE_PATH: database.detected_source_path }
}

function databaseWithScriptAssignment(
  database: SourceDatabaseSelection,
  assignment: DatabaseScriptAssignment,
  scriptExecutionOrder: number
): SourceDatabaseSelection {
  const preScriptId = cleanOptionalScriptId(assignment.preBackupScriptId)
  const postScriptId = cleanOptionalScriptId(assignment.postBackupScriptId)
  return {
    ...database,
    ...(preScriptId ? { pre_backup_script_id: preScriptId } : {}),
    ...(postScriptId ? { post_backup_script_id: postScriptId } : {}),
    pre_backup_script_parameters: cleanScriptParameters({
      ...defaultDatabaseScriptParameters(database, 'pre'),
      ...(assignment.preBackupScriptParameters || {}),
    }),
    post_backup_script_parameters: cleanScriptParameters({
      ...defaultDatabaseScriptParameters(database, 'post'),
      ...(assignment.postBackupScriptParameters || {}),
    }),
    script_execution_order: scriptExecutionOrder,
  }
}

function containerExportSlug(containerName: string): string {
  const slug = containerName
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_.-]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return slug || 'container'
}

function defaultContainerExportPath(containerName: string): string {
  return `${DEFAULT_CONTAINER_EXPORT_ROOT}/${containerExportSlug(containerName)}`
}

function containerScriptDrafts(
  containerName: string,
  exportPath: string
): { preBackup: SourceDiscoveryScriptDraft; postBackup: SourceDiscoveryScriptDraft } {
  const displayName = containerName.trim() || 'container'
  return {
    preBackup: {
      name: `Export Docker container: ${displayName}`,
      description: 'Export a Docker container filesystem into a Borg-readable staging path.',
      content: [
        '#!/usr/bin/env bash',
        'set -euo pipefail',
        'CONTAINER_NAME="${BORG_UI_CONTAINER_NAME:?Set BORG_UI_CONTAINER_NAME}"',
        'EXPORT_DIR="${BORG_UI_CONTAINER_EXPORT_DIR:?Set BORG_UI_CONTAINER_EXPORT_DIR}"',
        'rm -rf "$EXPORT_DIR"',
        'mkdir -p "$EXPORT_DIR"',
        'docker inspect "$CONTAINER_NAME" > "$EXPORT_DIR/inspect.json"',
        'docker export "$CONTAINER_NAME" -o "$EXPORT_DIR/filesystem.tar"',
        '',
      ].join('\n'),
      timeout: 900,
    },
    postBackup: {
      name: `Clean Docker export: ${displayName}`,
      description: `Remove the transient Docker export staged at ${exportPath}.`,
      content: [
        '#!/usr/bin/env bash',
        'set -euo pipefail',
        'EXPORT_DIR="${BORG_UI_CONTAINER_EXPORT_DIR:?Set BORG_UI_CONTAINER_EXPORT_DIR}"',
        'rm -rf "$EXPORT_DIR"',
        '',
      ].join('\n'),
      timeout: 120,
    },
  }
}

function defaultContainerScriptParameters(
  container: SourceContainerSelection,
  hook: 'pre' | 'post'
): Record<string, string> {
  if (hook === 'post') {
    return { BORG_UI_CONTAINER_EXPORT_DIR: container.export_path }
  }
  return {
    BORG_UI_CONTAINER_NAME: container.container_name,
    BORG_UI_CONTAINER_EXPORT_DIR: container.export_path,
  }
}

function containerWithScriptAssignment(
  container: SourceContainerSelection,
  assignment: ContainerScriptAssignment,
  scriptExecutionOrder: number
): SourceContainerSelection {
  const preScriptId = cleanOptionalScriptId(assignment.preBackupScriptId)
  const postScriptId = cleanOptionalScriptId(assignment.postBackupScriptId)
  return {
    ...container,
    ...(preScriptId ? { pre_backup_script_id: preScriptId } : {}),
    ...(postScriptId ? { post_backup_script_id: postScriptId } : {}),
    pre_backup_script_parameters: cleanScriptParameters({
      ...defaultContainerScriptParameters(container, 'pre'),
      ...(assignment.preBackupScriptParameters || {}),
    }),
    post_backup_script_parameters: cleanScriptParameters({
      ...defaultContainerScriptParameters(container, 'post'),
      ...(assignment.postBackupScriptParameters || {}),
    }),
    script_execution_order: scriptExecutionOrder,
  }
}

function cleanDatabaseSelection(
  database: SourceDatabaseSelection | undefined,
  paths: string[]
): SourceDatabaseSelection | undefined {
  if (!database) return undefined
  const backupPaths = (database.backup_paths || paths).map((path) => path.trim()).filter(Boolean)
  if (backupPaths.length === 0) return undefined
  const captureMode: DatabaseCaptureMode =
    database.capture_mode === 'original' ? 'original' : 'dump'
  const cleaned: SourceDatabaseSelection = {
    template_id: database.template_id?.trim() || 'database',
    engine: database.engine?.trim() || 'Database',
    display_name: database.display_name?.trim() || database.engine?.trim() || 'Database',
    backup_strategy: database.backup_strategy?.trim() || 'logical_dump',
    detected_source_path: database.detected_source_path?.trim() || null,
    detection_label: database.detection_label?.trim() || null,
    capture_mode: captureMode,
    dump_path: captureMode === 'dump' ? database.dump_path?.trim() || backupPaths[0] : null,
    backup_paths: backupPaths,
    script_execution_target: database.script_execution_target || 'source',
  }
  const preScriptId = cleanOptionalScriptId(database.pre_backup_script_id)
  const postScriptId = cleanOptionalScriptId(database.post_backup_script_id)
  if (preScriptId) cleaned.pre_backup_script_id = preScriptId
  if (postScriptId) cleaned.post_backup_script_id = postScriptId
  if (preScriptId || database.pre_backup_script_parameters) {
    cleaned.pre_backup_script_parameters = cleanScriptParameters(
      database.pre_backup_script_parameters
    )
  }
  if (postScriptId || database.post_backup_script_parameters) {
    cleaned.post_backup_script_parameters = cleanScriptParameters(
      database.post_backup_script_parameters
    )
  }
  const scriptExecutionOrder = cleanOptionalScriptId(database.script_execution_order)
  if (scriptExecutionOrder) cleaned.script_execution_order = scriptExecutionOrder
  return cleaned
}

function cleanContainerSelection(
  container: SourceContainerSelection | undefined,
  paths: string[]
): SourceContainerSelection | undefined {
  if (!container) return undefined
  const containerName = container.container_name?.trim()
  const exportPath = container.export_path?.trim() || paths[0]
  if (!containerName || !exportPath) return undefined
  const cleaned: SourceContainerSelection = {
    container_name: containerName,
    display_name: container.display_name?.trim() || containerName,
    image: container.image?.trim() || null,
    backup_mode: 'export',
    export_path: exportPath,
    script_execution_target: container.script_execution_target || 'source',
  }
  const preScriptId = cleanOptionalScriptId(container.pre_backup_script_id)
  const postScriptId = cleanOptionalScriptId(container.post_backup_script_id)
  if (preScriptId) cleaned.pre_backup_script_id = preScriptId
  if (postScriptId) cleaned.post_backup_script_id = postScriptId
  if (preScriptId || container.pre_backup_script_parameters) {
    cleaned.pre_backup_script_parameters = cleanScriptParameters(
      container.pre_backup_script_parameters
    )
  }
  if (postScriptId || container.post_backup_script_parameters) {
    cleaned.post_backup_script_parameters = cleanScriptParameters(
      container.post_backup_script_parameters
    )
  }
  const scriptExecutionOrder = cleanOptionalScriptId(container.script_execution_order)
  if (scriptExecutionOrder) cleaned.script_execution_order = scriptExecutionOrder
  return cleaned
}

function cleanLocations(locations: SourceLocation[]): SourceLocation[] {
  return locations
    .map((location) => {
      const paths = location.paths.map((path) => path.trim()).filter(Boolean)
      const cleaned: SourceLocation = {
        source_type: location.source_type,
        source_ssh_connection_id:
          location.source_type === 'remote' ? location.source_ssh_connection_id : null,
        agent_machine_id: location.source_type === 'agent' ? location.agent_machine_id : null,
        paths,
      }
      if (location.source_type === 'local' && location.snapshot) {
        cleaned.snapshot = location.snapshot
      }
      const database = cleanDatabaseSelection(location.database, paths)
      if (database) {
        cleaned.database = database
      }
      const container = cleanContainerSelection(location.container, paths)
      if (container) {
        cleaned.container = container
      }
      return cleaned
    })
    .filter((location) => location.paths.length > 0)
}

function hasMixedSourceTypes(locations: SourceLocation[]): boolean {
  return new Set(locations.map((location) => location.source_type)).size > 1
}

function locationsFromWizardState(wizardState: WizardState): SourceLocation[] {
  const existing = cleanLocations(wizardState.sourceLocations || [])
  if (existing.length > 0) return existing
  if (wizardState.sourceDirectories.length === 0) return []
  if (wizardState.sourceType === 'remote' && wizardState.sourceSshConnectionId) {
    return [
      {
        source_type: 'remote',
        source_ssh_connection_id: Number(wizardState.sourceSshConnectionId),
        agent_machine_id: null,
        paths: wizardState.sourceDirectories,
      },
    ]
  }
  return [
    {
      source_type: 'local',
      source_ssh_connection_id: null,
      agent_machine_id: null,
      paths: wizardState.sourceDirectories,
    },
  ]
}

function locationKey(location: SourceLocation): SourceKey {
  if (location.source_type === 'remote' && location.source_ssh_connection_id) {
    return `remote:${location.source_ssh_connection_id}`
  }
  if (location.source_type === 'agent' && location.agent_machine_id) {
    return `agent:${location.agent_machine_id}`
  }
  return 'local'
}

function draftLocationKey(location: SourceLocation) {
  const baseKey = locationKey(location)
  if (location.container) {
    return `${baseKey}:container:${JSON.stringify([
      location.container.container_name,
      location.container.export_path,
    ])}`
  }
  if (!location.database) return `${baseKey}:files`
  return `${baseKey}:database:${JSON.stringify([
    location.database.template_id,
    location.database.detected_source_path || '',
    location.database.dump_path || '',
    location.database.backup_paths,
  ])}`
}

function locationForKey(
  sourceKey: SourceKey
): Pick<SourceLocation, 'source_type' | 'source_ssh_connection_id' | 'agent_machine_id'> {
  if (sourceKey === 'local') {
    return { source_type: 'local', source_ssh_connection_id: null, agent_machine_id: null }
  }
  if (sourceKey.startsWith('agent:')) {
    return {
      source_type: 'agent',
      source_ssh_connection_id: null,
      agent_machine_id: Number(sourceKey.split(':')[1]),
    }
  }
  return {
    source_type: 'remote',
    source_ssh_connection_id: Number(sourceKey.split(':')[1]),
    agent_machine_id: null,
  }
}

function snapshotDraftsFromLocations(locations: SourceLocation[]): Record<string, SnapshotDraft> {
  return Object.fromEntries(
    locations.map((location) => [locationKey(location), snapshotDraftFromLocation(location)])
  )
}

function draftForLocation(
  location: SourceLocation,
  draftsBySourceKey: Record<string, SnapshotDraft>,
  selectedSourceKey: SourceKey,
  selectedDraft: SnapshotDraft
): SnapshotDraft {
  const key = locationKey(location)
  if (key === selectedSourceKey) return selectedDraft
  return draftsBySourceKey[key] || snapshotDraftFromLocation(location)
}

function areSnapshotDraftsValid(
  locations: SourceLocation[],
  draftsBySourceKey: Record<string, SnapshotDraft>,
  selectedSourceKey: SourceKey,
  selectedDraft: SnapshotDraft
): boolean {
  return locations.every((location) =>
    isSnapshotDraftValid(
      draftForLocation(location, draftsBySourceKey, selectedSourceKey, selectedDraft),
      locationKey(location)
    )
  )
}

function sourceTypeFromLocations(locations: SourceLocation[]): SourceType {
  if (locations.length === 0) return 'local'
  if (locations.length > 1) return 'mixed'
  return locations[0].source_type
}

function sourceConnectionFromLocations(locations: SourceLocation[]): number | '' {
  if (locations.length !== 1 || locations[0].source_type !== 'remote') return ''
  return locations[0].source_ssh_connection_id ? Number(locations[0].source_ssh_connection_id) : ''
}

function sourceLocationLabel(
  location: SourceLocation,
  sshConnections: SSHConnection[],
  agentMachines: AgentMachineResponse[],
  t: TFunction
) {
  if (location.source_type === 'local') return t('backupPlans.sourceChooser.borgUiServer')
  if (location.source_type === 'agent') {
    const agent = agentMachines.find((item) => item.id === location.agent_machine_id)
    return (
      agent?.hostname ||
      agent?.name ||
      t('backupPlans.sourceChooser.agentFallback', {
        id: location.agent_machine_id,
      })
    )
  }
  const connection = sshConnections.find((item) => item.id === location.source_ssh_connection_id)
  return connection
    ? `${connection.username}@${connection.host}`
    : t('backupPlans.wizard.review.connectionFallback', {
        id: location.source_ssh_connection_id,
      })
}

function selectedAgentRepositoryKey(
  wizardState: WizardState,
  fullRepositories: Repository[]
): SourceKey | null {
  const constraint = getAgentRepoConstraint(wizardState, fullRepositories, [])
  return constraint ? `agent:${constraint.agentId}` : null
}

// When the plan targets a single agent-backed repository, the backend (see
// _agent_source_paths in app/services/repository_executor.py) only accepts
// sources of source_type=local or source_type=agent with the same
// agent_machine_id. We surface that constraint in the UI by disabling the
// Remote card and locking the Managed Agent picker to the repo's agent.
function getAgentRepoConstraint(
  wizardState: WizardState,
  fullRepositories: Repository[],
  agentMachines: AgentMachineResponse[]
): { agentId: number; agentName: string } | null {
  const selectedRepositories = wizardState.repositoryIds
    .map((id) => fullRepositories.find((repository) => repository.id === id))
    .filter((repository): repository is Repository => Boolean(repository))
  if (selectedRepositories.length !== 1) return null
  const repository = selectedRepositories[0]
  if (repository.executor_type !== 'agent' || !repository.agent_machine_id) return null
  const agent = agentMachines.find((item) => item.id === repository.agent_machine_id)
  return {
    agentId: repository.agent_machine_id,
    agentName: agent ? agentDisplayName(agent) : `Agent #${repository.agent_machine_id}`,
  }
}

function agentDisplayName(agent?: AgentMachineResponse | null) {
  if (!agent) return ''
  return agent.hostname || agent.name || `Agent #${agent.id}`
}

export function SourceSelectionDialog({
  open,
  wizardState,
  sshConnections,
  agentMachines,
  fullRepositories,
  scripts,
  loadingScripts,
  onClose,
  updateState,
  onCreateScript,
  t,
  initialView = 'paths',
  initialScanTarget,
  initialCaptureModeExpanded = false,
  initialSelectedDatabase,
  initialScanDialogOpen = false,
  canUseManagedAgents = true,
  canUseMixedSourceTypes = true,
}: SourceSelectionDialogProps) {
  const [view, setView] = useState<SourceChoiceView>(initialView)
  const [scanDialogOpen, setScanDialogOpen] = useState(initialScanDialogOpen)
  // Carries the scan target (and, when known, its display label) over from
  // the DatabaseScanDialog so applyDatabase places the chosen database on the
  // right source machine. Updated when the sub-modal returns a choice; reset
  // to local when the parent dialog opens.
  const [lastScanContext, setLastScanContext] = useState<{
    scanTarget: ScanTargetState
    label: string | null
  }>(() => ({
    scanTarget: { type: 'local', sshId: '' },
    label: null,
  }))
  const [fallbackTemplates, setFallbackTemplates] = useState<SourceDiscoveryDatabase[]>([])
  const [snapshotCapabilities, setSnapshotCapabilities] =
    useState<FilesystemSnapshotCapabilitiesResponse | null>(null)
  const [selectedDatabase, setSelectedDatabase] = useState<SourceDiscoveryDatabase | null>(null)
  const [scriptMode, setScriptMode] = useState<ScriptMode>('create')
  const [preScriptName, setPreScriptName] = useState('')
  const [postScriptName, setPostScriptName] = useState('')
  const [preScriptContent, setPreScriptContent] = useState('')
  const [postScriptContent, setPostScriptContent] = useState('')
  const [preExistingScriptId, setPreExistingScriptId] = useState<number | ''>('')
  const [postExistingScriptId, setPostExistingScriptId] = useState<number | ''>('')
  const [databaseCaptureMode, setDatabaseCaptureMode] = useState<DatabaseCaptureMode>('dump')
  const [databaseDumpPath, setDatabaseDumpPath] = useState('')
  const [queuedDatabaseScriptDrafts, setQueuedDatabaseScriptDrafts] = useState<
    Record<string, QueuedDatabaseScriptDraft>
  >({})
  const [containerName, setContainerName] = useState('')
  const [containerImage, setContainerImage] = useState('')
  const [containerExportPath, setContainerExportPath] = useState(DEFAULT_CONTAINER_EXPORT_ROOT)
  const [containerExportPathTouched, setContainerExportPathTouched] = useState(false)
  const [queuedContainerScriptDrafts, setQueuedContainerScriptDrafts] = useState<
    Record<string, QueuedContainerScriptDraft>
  >({})
  const [applying, setApplying] = useState(false)
  const [selectedSourceKey, setSelectedSourceKey] = useState<SourceKey>('local')
  const [sourcePath, setSourcePath] = useState('')
  const [draftSourceLocations, setDraftSourceLocations] = useState<SourceLocation[]>([])
  const [snapshotDraftsBySourceKey, setSnapshotDraftsBySourceKey] = useState<
    Record<string, SnapshotDraft>
  >({})
  const [snapshotDraft, setSnapshotDraft] = useState<SnapshotDraft>(() => emptySnapshotDraft())
  const [captureModeExpanded, setCaptureModeExpanded] = useState(initialCaptureModeExpanded)
  const wizardSourceLocations = wizardState.sourceLocations
  const hydratedDatabaseLocation = useMemo(
    () => cleanLocations(wizardSourceLocations || []).find((location) => location.database),
    [wizardSourceLocations]
  )

  useEffect(() => {
    if (!open) return
    const nextLocations = locationsFromWizardState(wizardState)
    const databaseLocation = nextLocations.find((location) => location.database)
    const containerLocation = nextLocations.find((location) => location.container)
    const hydratedTemplateId =
      wizardState.databaseTemplateId ?? databaseLocation?.database?.template_id ?? null
    const initialDetailDatabase =
      initialView === 'database-detail' ? initialSelectedDatabase || null : null
    const initialViewWithDb: SourceChoiceView = initialDetailDatabase
      ? 'database-detail'
      : hydratedTemplateId
        ? 'database'
        : initialView
    setView(initialViewWithDb)
    const nextSnapshotDrafts = snapshotDraftsFromLocations(nextLocations)
    const defaultAgentKey = selectedAgentRepositoryKey(wizardState, fullRepositories)
    setDraftSourceLocations(nextLocations)
    setSnapshotDraftsBySourceKey(nextSnapshotDrafts)
    const nextSourceKey = nextLocations[0]
      ? locationKey(nextLocations[0])
      : defaultAgentKey || 'local'
    setSelectedSourceKey(nextSourceKey)
    setSnapshotDraft(
      nextSnapshotDrafts[nextSourceKey] ||
        snapshotDraftFromLocation(
          nextLocations.find((location) => locationKey(location) === nextSourceKey)
        )
    )
    setCaptureModeExpanded(initialCaptureModeExpanded)
    setSourcePath('')
    setSelectedDatabase(initialDetailDatabase)
    setScriptMode('create')
    setPreScriptName(initialDetailDatabase?.script_drafts.pre_backup.name || '')
    setPostScriptName(initialDetailDatabase?.script_drafts.post_backup.name || '')
    setPreScriptContent(initialDetailDatabase?.script_drafts.pre_backup.content || '')
    setPostScriptContent(initialDetailDatabase?.script_drafts.post_backup.content || '')
    setPreExistingScriptId(databaseLocation?.database?.pre_backup_script_id || '')
    setPostExistingScriptId(databaseLocation?.database?.post_backup_script_id || '')
    setQueuedDatabaseScriptDrafts({})
    setContainerName(containerLocation?.container?.container_name || '')
    setContainerImage(containerLocation?.container?.image || '')
    setContainerExportPath(
      containerLocation?.container?.export_path || DEFAULT_CONTAINER_EXPORT_ROOT
    )
    setContainerExportPathTouched(Boolean(containerLocation?.container?.export_path))
    setQueuedContainerScriptDrafts({})
    setDatabaseCaptureMode(databaseLocation?.database?.capture_mode || 'dump')
    setDatabaseDumpPath(
      databaseLocation?.database?.dump_path ||
        databaseLocation?.database?.backup_paths?.[0] ||
        (initialDetailDatabase
          ? defaultDatabaseDumpPath(initialDetailDatabase, nextLocations)
          : '') ||
        ''
    )
    setScanDialogOpen(initialScanDialogOpen)
    setLastScanContext({
      scanTarget: initialScanTarget ?? { type: 'local', sshId: '' },
      label: null,
    })
    setFallbackTemplates([])
  }, [
    open,
    wizardState,
    initialView,
    initialScanTarget,
    initialCaptureModeExpanded,
    initialSelectedDatabase,
    initialScanDialogOpen,
    sshConnections,
    fullRepositories,
  ])

  useEffect(() => {
    if (!open) return
    let active = true
    sourceDiscoveryAPI
      .databases()
      .then((response: { data: SourceDiscoveryResponse }) => {
        if (active) setFallbackTemplates(response.data.templates)
      })
      .catch(() => {
        // Legacy endpoint may also be unavailable; silent.
      })
    return () => {
      active = false
    }
  }, [open])

  // When a story or direct entry opens the dialog on a database detail, enrich
  // the initial selection from the fetched template list as soon as it lands.
  // Do not run this for normal edit sessions: a plan-level databaseTemplateId
  // can belong to an already queued database, and must not overwrite a new
  // scan/template choice the user is actively configuring.
  useEffect(() => {
    if (!open) return
    if (initialView !== 'database-detail') return
    const hydratedTemplateId = wizardState.databaseTemplateId ?? null
    if (!hydratedTemplateId || hydratedTemplateId === 'sqlite') return
    if (!selectedDatabase || selectedDatabase.id !== hydratedTemplateId) return
    if (databaseDetectedPath(selectedDatabase)) return
    const match = fallbackTemplates.find((tpl) => tpl.id === hydratedTemplateId)
    if (!match) return
    setSelectedDatabase(match)
    setPreScriptName(match.script_drafts.pre_backup.name)
    setPostScriptName(match.script_drafts.post_backup.name)
    setPreScriptContent(match.script_drafts.pre_backup.content)
    setPostScriptContent(match.script_drafts.post_backup.content)
    setScriptMode(hydratedDatabaseLocation?.database?.pre_backup_script_id ? 'reuse' : 'create')
  }, [
    open,
    initialView,
    wizardState.databaseTemplateId,
    hydratedDatabaseLocation,
    fallbackTemplates,
    selectedDatabase,
  ])

  useEffect(() => {
    if (!open) return
    let active = true
    sourceDiscoveryAPI
      .filesystemSnapshots()
      .then((response) => {
        if (active) {
          setSnapshotCapabilities(response.data)
          setSnapshotDraft((current) =>
            current.provider === 'btrfs' && current.stagingPath === DEFAULT_SNAPSHOT_STAGING_PATH
              ? { ...current, stagingPath: response.data.default_staging_path }
              : current
          )
        }
      })
      .catch(() => {
        if (active) setSnapshotCapabilities(null)
      })
    return () => {
      active = false
    }
  }, [open])

  const selectSourceKey = (sourceKey: SourceKey) => {
    setSelectedSourceKey(sourceKey)
    const existing = draftSourceLocations.find((location) => locationKey(location) === sourceKey)
    setSnapshotDraft(snapshotDraftsBySourceKey[sourceKey] || snapshotDraftFromLocation(existing))
  }

  const updateSnapshotDraft = (updates: Partial<SnapshotDraft>) => {
    setSnapshotDraft((current) => {
      const next = { ...current, ...updates }
      setSnapshotDraftsBySourceKey((drafts) => ({
        ...drafts,
        [selectedSourceKey]: next,
      }))
      if (selectedSourceKey === 'local') {
        setDraftSourceLocations((locations) =>
          locations.map((location) => {
            if (locationKey(location) !== selectedSourceKey) return location
            const snapshot = snapshotFromDraft(next, location.snapshot)
            return {
              ...location,
              ...(snapshot ? { snapshot } : { snapshot: undefined }),
            }
          })
        )
      }
      return next
    })
  }

  const chooseDatabase = (database: SourceDiscoveryDatabase) => {
    setSelectedDatabase(database)
    setPreScriptName(database.script_drafts.pre_backup.name)
    setPostScriptName(database.script_drafts.post_backup.name)
    setPreScriptContent(database.script_drafts.pre_backup.content)
    setPostScriptContent(database.script_drafts.post_backup.content)
    setDatabaseCaptureMode('dump')
    setDatabaseDumpPath(defaultDatabaseDumpPath(database, draftSourceLocations))
    setView('database-detail')
  }

  const handleScanChoice = (choice: DatabaseScanChoice) => {
    setLastScanContext({ scanTarget: choice.scanTarget, label: choice.scanTargetLabel })
    setScanDialogOpen(false)
    chooseDatabase(choice.database)
  }

  const applyDatabase = async () => {
    if (!selectedDatabase) return

    setApplying(true)
    try {
      const contextTarget = lastScanContext.scanTarget
      const targetKey: SourceKey =
        contextTarget.type === 'remote' && contextTarget.sshId
          ? `remote:${contextTarget.sshId}`
          : 'local'
      const locationBase = locationForKey(targetKey)
      const detectedSourcePath = databaseDetectedPath(selectedDatabase)
      const requestedCaptureMode: DatabaseCaptureMode =
        databaseCaptureMode === 'original' && detectedSourcePath ? 'original' : 'dump'
      const dumpPath =
        databaseDumpPath.trim() || defaultDatabaseDumpPath(selectedDatabase, draftSourceLocations)
      const backupPaths =
        requestedCaptureMode === 'original' && detectedSourcePath
          ? [detectedSourcePath]
          : [dumpPath]
      let database: SourceDatabaseSelection = {
        template_id: selectedDatabase.id,
        engine: selectedDatabase.engine,
        display_name: selectedDatabase.display_name,
        backup_strategy: selectedDatabase.backup_strategy,
        detected_source_path: detectedSourcePath,
        detection_label:
          lastScanContext.label ||
          (contextTarget.type === 'remote'
            ? t('backupPlans.sourceChooser.remoteMachine')
            : t('backupPlans.sourceChooser.borgUiServer')),
        capture_mode: requestedCaptureMode,
        dump_path: requestedCaptureMode === 'dump' ? dumpPath : null,
        backup_paths: backupPaths,
        script_execution_target: 'source',
      }
      if (scriptMode === 'reuse') {
        database = databaseWithScriptAssignment(
          database,
          {
            preBackupScriptId: preExistingScriptId ? Number(preExistingScriptId) : null,
            postBackupScriptId: postExistingScriptId ? Number(postExistingScriptId) : null,
          },
          draftSourceLocations.filter((location) => location.database).length + 1
        )
      }
      const nextLocation: SourceLocation = {
        ...locationBase,
        paths: backupPaths,
        database,
      }
      const nextLocationKey = draftLocationKey(nextLocation)

      setDraftSourceLocations((current) => [
        ...current.filter((location) => draftLocationKey(location) !== nextLocationKey),
        nextLocation,
      ])
      setQueuedDatabaseScriptDrafts((current) => {
        if (scriptMode !== 'create') {
          const remaining = { ...current }
          delete remaining[nextLocationKey]
          return remaining
        }
        return {
          ...current,
          [nextLocationKey]: {
            databaseName: selectedDatabase.display_name,
            database,
            preBackup: selectedDatabase.script_drafts.pre_backup,
            postBackup: selectedDatabase.script_drafts.post_backup,
            preScriptName: preScriptName.trim() || selectedDatabase.script_drafts.pre_backup.name,
            postScriptName:
              postScriptName.trim() || selectedDatabase.script_drafts.post_backup.name,
            preScriptContent,
            postScriptContent,
          },
        }
      })
      setSelectedSourceKey(targetKey)
      setView('database')
    } finally {
      setApplying(false)
    }
  }

  const handleFooterCancel = () => {
    if (view === 'database-detail') {
      setSelectedDatabase(null)
      setView('database')
      return
    }
    onClose()
  }

  const addPathsToSourceKey = (sourceKey: SourceKey, paths: string[]) => {
    const nextPaths = paths.map((path) => path.trim()).filter(Boolean)
    if (nextPaths.length === 0) return
    const locationBase = locationForKey(sourceKey)

    setDraftSourceLocations((current) => {
      const existingIndex = current.findIndex(
        (location) =>
          locationKey(location) === sourceKey && !location.database && !location.container
      )
      if (existingIndex === -1) {
        const snapshot = sourceKey === 'local' ? snapshotFromDraft(snapshotDraft) : undefined
        return [
          ...current,
          {
            ...locationBase,
            paths: Array.from(new Set(nextPaths)),
            ...(snapshot ? { snapshot } : {}),
          },
        ]
      }

      return current.map((location, index) => {
        if (index !== existingIndex) return location
        const snapshot =
          sourceKey === 'local' ? snapshotFromDraft(snapshotDraft, location.snapshot) : undefined
        return {
          ...location,
          paths: Array.from(new Set([...location.paths, ...nextPaths])),
          ...(snapshot ? { snapshot } : { snapshot: undefined }),
        }
      })
    })
  }

  const addPathsToSelectedSource = (paths: string[]) =>
    addPathsToSourceKey(selectedSourceKey, paths)

  const addSourcePath = () => {
    addPathsToSelectedSource([sourcePath])
    setSourcePath('')
  }

  const handleContainerNameChange = (value: string) => {
    setContainerName(value)
    if (!containerExportPathTouched) {
      setContainerExportPath(
        value.trim() ? defaultContainerExportPath(value) : DEFAULT_CONTAINER_EXPORT_ROOT
      )
    }
  }

  const handleContainerExportPathChange = (value: string) => {
    setContainerExportPath(value)
    setContainerExportPathTouched(true)
  }

  const queueContainerSource = () => {
    const nextContainerName = containerName.trim()
    const nextExportPath =
      containerExportPath.trim() || defaultContainerExportPath(nextContainerName)
    if (!nextContainerName || !nextExportPath) return

    const locationBase = locationForKey(selectedSourceKey)
    const container: SourceContainerSelection = {
      container_name: nextContainerName,
      display_name: nextContainerName,
      image: containerImage.trim() || null,
      backup_mode: 'export',
      export_path: nextExportPath,
      script_execution_target: 'source',
    }
    const nextLocation: SourceLocation = {
      ...locationBase,
      paths: [nextExportPath],
      container,
    }
    const nextLocationKey = draftLocationKey(nextLocation)
    const scriptDrafts = containerScriptDrafts(nextContainerName, nextExportPath)

    setDraftSourceLocations((current) => [
      ...current.filter((location) => draftLocationKey(location) !== nextLocationKey),
      nextLocation,
    ])
    setQueuedContainerScriptDrafts((current) => ({
      ...current,
      [nextLocationKey]: {
        container,
        preBackup: scriptDrafts.preBackup,
        postBackup: scriptDrafts.postBackup,
        preScriptName: scriptDrafts.preBackup.name,
        postScriptName: scriptDrafts.postBackup.name,
      },
    }))
    setContainerName('')
    setContainerImage('')
    setContainerExportPath(DEFAULT_CONTAINER_EXPORT_ROOT)
    setContainerExportPathTouched(false)
  }

  const removeSourcePath = (sourceKey: string, path: string) => {
    setDraftSourceLocations((current) =>
      current
        .map((location) =>
          draftLocationKey(location) === sourceKey
            ? { ...location, paths: location.paths.filter((item) => item !== path) }
            : location
        )
        .filter((location) => location.paths.length > 0)
    )
  }

  const removeSourceLocation = (sourceKey: string) => {
    setDraftSourceLocations((current) =>
      current.filter((location) => draftLocationKey(location) !== sourceKey)
    )
  }

  const resolveSourceScripts = async (
    sourceLocations: SourceLocation[]
  ): Promise<SourceLocation[]> => {
    const createdScripts = new Map<string, Promise<number>>()
    let sourceScriptOrder = 0

    const createReusableScript = async (
      scopeKey: string,
      hook: 'pre' | 'post',
      payload: SourceScriptCreateInput
    ) => {
      const cacheKey = JSON.stringify([
        scopeKey,
        hook,
        payload.name,
        payload.content,
        payload.timeout,
      ])
      if (!createdScripts.has(cacheKey)) {
        createdScripts.set(
          cacheKey,
          onCreateScript(payload).then((script) => script.id)
        )
      }
      return createdScripts.get(cacheKey)!
    }

    const resolvedLocations: SourceLocation[] = []
    for (const location of sourceLocations) {
      if (location.database) {
        sourceScriptOrder += 1

        const draft = queuedDatabaseScriptDrafts[draftLocationKey(location)]
        if (draft) {
          const preBackupScriptId = await createReusableScript(
            `database:${location.database.template_id}`,
            'pre',
            scriptPayload(
              { ...draft.preBackup, content: draft.preScriptContent },
              draft.preScriptName
            )
          )
          const postBackupScriptId = await createReusableScript(
            `database:${location.database.template_id}`,
            'post',
            scriptPayload(
              { ...draft.postBackup, content: draft.postScriptContent },
              draft.postScriptName
            )
          )
          resolvedLocations.push({
            ...location,
            database: databaseWithScriptAssignment(
              location.database,
              {
                preBackupScriptId,
                postBackupScriptId,
              },
              sourceScriptOrder
            ),
          })
          continue
        }

        if (location.database.pre_backup_script_id || location.database.post_backup_script_id) {
          resolvedLocations.push({
            ...location,
            database: databaseWithScriptAssignment(
              location.database,
              {
                preBackupScriptId: location.database.pre_backup_script_id ?? null,
                postBackupScriptId: location.database.post_backup_script_id ?? null,
                preBackupScriptParameters: location.database.pre_backup_script_parameters,
                postBackupScriptParameters: location.database.post_backup_script_parameters,
              },
              sourceScriptOrder
            ),
          })
          continue
        }

        resolvedLocations.push(location)
        continue
      }

      if (location.container) {
        sourceScriptOrder += 1

        const draft = queuedContainerScriptDrafts[draftLocationKey(location)]
        if (draft) {
          const preBackupScriptId = await createReusableScript(
            `container:${location.container.container_name}`,
            'pre',
            scriptPayload(draft.preBackup, draft.preScriptName)
          )
          const postBackupScriptId = await createReusableScript(
            `container:${location.container.container_name}`,
            'post',
            scriptPayload(draft.postBackup, draft.postScriptName)
          )
          resolvedLocations.push({
            ...location,
            container: containerWithScriptAssignment(
              location.container,
              {
                preBackupScriptId,
                postBackupScriptId,
              },
              sourceScriptOrder
            ),
          })
          continue
        }

        if (location.container.pre_backup_script_id || location.container.post_backup_script_id) {
          resolvedLocations.push({
            ...location,
            container: containerWithScriptAssignment(
              location.container,
              {
                preBackupScriptId: location.container.pre_backup_script_id ?? null,
                postBackupScriptId: location.container.post_backup_script_id ?? null,
                preBackupScriptParameters: location.container.pre_backup_script_parameters,
                postBackupScriptParameters: location.container.post_backup_script_parameters,
              },
              sourceScriptOrder
            ),
          })
          continue
        }

        resolvedLocations.push(location)
        continue
      }

      resolvedLocations.push(location)
    }

    return resolvedLocations
  }

  const applyPaths = async () => {
    const sourceLocations = cleanLocations(
      draftSourceLocations.map((location) => {
        if (location.source_type !== 'local') return location
        const draft = draftForLocation(
          location,
          snapshotDraftsBySourceKey,
          selectedSourceKey,
          snapshotDraft
        )
        const snapshot = snapshotFromDraft(draft, location.snapshot)
        return {
          ...location,
          ...(snapshot ? { snapshot } : { snapshot: undefined }),
        }
      })
    )
    if (!canUseMixedSourceTypes && hasMixedSourceTypes(sourceLocations)) return
    setApplying(true)
    try {
      const sourceLocationsWithScripts = await resolveSourceScripts(sourceLocations)
      const databaseLocation = sourceLocationsWithScripts.find((location) => location.database)
      updateState({
        sourceType: sourceTypeFromLocations(sourceLocationsWithScripts),
        sourceSshConnectionId: sourceConnectionFromLocations(sourceLocationsWithScripts),
        sourceDirectories: sourceLocationsWithScripts.flatMap((location) => location.paths),
        sourceLocations: sourceLocationsWithScripts,
        databaseTemplateId: databaseLocation?.database?.template_id ?? null,
      })
      onClose()
    } finally {
      setApplying(false)
    }
  }

  const selectedSourceConnection = !selectedSourceKey.startsWith('remote:')
    ? null
    : sshConnections.find((connection) => selectedSourceKey === `remote:${connection.id}`) || null
  const selectedAgent = selectedSourceKey.startsWith('agent:')
    ? agentMachines.find((agent) => selectedSourceKey === `agent:${agent.id}`) || null
    : null
  // Only real source groups should affect Apply state and mixed-source gating.
  const cleanedDraftSourceLocations = cleanLocations(draftSourceLocations)
  const mixedSourceTypesBlocked =
    !canUseMixedSourceTypes && hasMixedSourceTypes(cleanedDraftSourceLocations)

  const selectedSourceSshConfig = selectedSourceConnection
    ? {
        ssh_key_id: selectedSourceConnection.ssh_key_id,
        host: selectedSourceConnection.host,
        username: selectedSourceConnection.username,
        port: selectedSourceConnection.port,
      }
    : undefined

  const renderPaths = () => {
    const sourceKind: 'local' | 'remote' | 'agent' = selectedSourceKey.startsWith('remote:')
      ? 'remote'
      : selectedSourceKey.startsWith('agent:')
        ? 'agent'
        : 'local'
    const selectedRemoteIdNum = selectedSourceKey.startsWith('remote:')
      ? Number(selectedSourceKey.split(':')[1])
      : 0
    const selectedAgentIdNum = selectedSourceKey.startsWith('agent:')
      ? Number(selectedSourceKey.split(':')[1])
      : 0
    const agentRepoConstraint = getAgentRepoConstraint(wizardState, fullRepositories, agentMachines)
    const hasRemoteOptions = sshConnections.length > 0
    const hasAgentOptions = agentMachines.length > 0
    const remoteDisabled = sourceKind === 'remote' && !hasRemoteOptions
    const agentDisabled = sourceKind === 'agent' && (!canUseManagedAgents || !hasAgentOptions)
    const selectedSnapshotCapability =
      snapshotDraft.provider === 'none'
        ? null
        : snapshotCapabilities?.providers.find((provider) => provider.id === snapshotDraft.provider)
    const zfsDatasetMissing =
      sourceKind === 'local' && snapshotDraft.provider === 'zfs' && !snapshotDraft.dataset.trim()
    const zfsMountpointMissing =
      sourceKind === 'local' && snapshotDraft.provider === 'zfs' && !snapshotDraft.mountpoint.trim()
    const fileDraftSourceLocations = draftSourceLocations.filter((location) => !location.database)

    const lockedByAgentRepo = !!agentRepoConstraint
    const localCardDisabled = lockedByAgentRepo
    const remoteCardDisabled = !hasRemoteOptions || lockedByAgentRepo

    const handleSourceKindChange = (key: string) => {
      if (key === 'local') {
        selectSourceKey('local')
        return
      }
      if (key === 'remote') {
        if (!hasRemoteOptions) return
        const targetId =
          selectedRemoteIdNum &&
          sshConnections.some((connection) => connection.id === selectedRemoteIdNum)
            ? selectedRemoteIdNum
            : sshConnections[0].id
        selectSourceKey(`remote:${targetId}`)
        return
      }
      if (key === 'agent') {
        if (!canUseManagedAgents || !hasAgentOptions) return
        if (agentRepoConstraint) {
          selectSourceKey(`agent:${agentRepoConstraint.agentId}`)
          return
        }
        const targetId =
          selectedAgentIdNum && agentMachines.some((agent) => agent.id === selectedAgentIdNum)
            ? selectedAgentIdNum
            : agentMachines[0].id
        selectSourceKey(`agent:${targetId}`)
      }
    }

    const sourceKindDestinations: DestinationOption[] = [
      {
        key: 'local',
        icon: lockedByAgentRepo ? <Lock size={16} /> : <HardDrive size={16} />,
        label: t('backupPlans.sourceChooser.borgUiServer'),
        description: lockedByAgentRepo
          ? t('backupPlans.sourceChooser.agentRepoLockedLocal', {
              agent: agentRepoConstraint.agentName,
            })
          : t('backupPlans.sourceChooser.localSourceDescription'),
        disabled: localCardDisabled,
      },
      {
        key: 'remote',
        icon: lockedByAgentRepo ? <Lock size={16} /> : <Server size={16} />,
        label: t('backupPlans.sourceChooser.remoteMachine'),
        description: lockedByAgentRepo
          ? t('backupPlans.sourceChooser.agentRepoLockedRemote', {
              agent: agentRepoConstraint.agentName,
            })
          : hasRemoteOptions
            ? t('backupPlans.sourceChooser.remoteMachineDescription')
            : t('backupPlans.sourceChooser.noRemoteMachines'),
        disabled: remoteCardDisabled,
      },
      {
        key: 'agent',
        icon: !canUseManagedAgents ? <Lock size={16} /> : <Laptop size={16} />,
        label: t('backupPlans.sourceChooser.managedAgent'),
        description: !canUseManagedAgents
          ? t('backupPlans.sourceChooser.managedAgentRequiresPro')
          : hasAgentOptions
            ? t('backupPlans.sourceChooser.managedAgentDescription')
            : t('backupPlans.sourceChooser.noManagedAgents'),
        disabled: !canUseManagedAgents || !hasAgentOptions,
      },
    ]

    return (
      <Stack spacing={2}>
        {agentRepoConstraint && (
          <Alert
            severity="info"
            icon={<Info size={18} />}
            sx={{ py: 0.5, '& .MuiAlert-message': { py: 0.5 } }}
          >
            {t('backupPlans.sourceChooser.agentRepoConstraintBanner', {
              agent: agentRepoConstraint.agentName,
            })}
          </Alert>
        )}

        <DestinationSelect
          value={sourceKind}
          onChange={handleSourceKindChange}
          destinations={sourceKindDestinations}
          label={t('backupPlans.sourceChooser.where')}
        />

        {sourceKind === 'remote' && hasRemoteOptions ? (
          <SshConnectionSelect
            value={selectedRemoteIdNum || ''}
            onChange={(id) => selectSourceKey(`remote:${id}`)}
            connections={sshConnections}
            label={t('backupPlans.sourceChooser.selectRemoteMachine')}
            emptyMessage={t('backupPlans.sourceChooser.noRemoteMachines')}
            hideEmptyAlert
          />
        ) : sourceKind === 'agent' &&
          canUseManagedAgents &&
          hasAgentOptions &&
          agentRepoConstraint ? (
          <Box
            sx={{
              border: 1,
              borderColor: 'divider',
              borderRadius: 1,
              bgcolor: 'action.hover',
              color: 'text.secondary',
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              px: 1.5,
              height: 56,
            }}
          >
            <Lock size={14} />
            <Typography variant="body2" color="text.secondary">
              {t('backupPlans.sourceChooser.agentRepoLockedAgentPicker', {
                agent: agentRepoConstraint.agentName,
              })}
            </Typography>
          </Box>
        ) : sourceKind === 'agent' && canUseManagedAgents && hasAgentOptions ? (
          <ManagedAgentSelect
            value={selectedAgentIdNum || ''}
            onChange={(id) => selectSourceKey(`agent:${id}`)}
            agents={agentMachines}
            label={t('backupPlans.sourceChooser.selectManagedAgent')}
            emptyMessage={t('backupPlans.sourceChooser.noManagedAgents')}
            labelId="source-agent-machine-label"
            hideEmptyAlert
          />
        ) : (
          <Box
            sx={{
              border: 1,
              borderColor: 'divider',
              borderRadius: 1,
              bgcolor: 'action.hover',
              color: 'text.secondary',
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              px: 1.5,
              height: 56,
            }}
          >
            {sourceKind === 'agent' ? <Laptop size={14} /> : <HardDrive size={14} />}
            <Typography variant="body2" color="text.secondary">
              {agentDisabled
                ? t(
                    canUseManagedAgents
                      ? 'backupPlans.sourceChooser.noManagedAgents'
                      : 'backupPlans.sourceChooser.managedAgentRequiresPro'
                  )
                : remoteDisabled
                  ? t('backupPlans.sourceChooser.noRemoteMachines')
                  : t('backupPlans.sourceChooser.readingFromLocal')}
            </Typography>
          </Box>
        )}

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems="flex-start">
          <PathSelectorField
            label={t('backupPlans.sourceChooser.sourcePath')}
            value={sourcePath}
            onChange={setSourcePath}
            size="small"
            fullWidth
            disabled={remoteDisabled || agentDisabled}
            initialPath={
              selectedSourceConnection ? selectedSourceConnection.default_path || '/' : '/'
            }
            multiSelect
            selectMode="both"
            connectionType={
              sourceKind === 'agent' ? 'agent' : selectedSourceConnection ? 'ssh' : 'local'
            }
            agentId={selectedAgent?.id}
            agentName={selectedAgent?.name}
            agentDefaultPath={selectedAgent?.default_path}
            sshConfig={selectedSourceSshConfig}
            showSshMountPoints={false}
            onSelectPaths={(paths) => {
              addPathsToSelectedSource(paths)
              setSourcePath('')
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                addSourcePath()
              }
            }}
          />
          <Button
            variant="contained"
            startIcon={<Plus size={16} />}
            onClick={addSourcePath}
            disabled={!sourcePath.trim() || remoteDisabled || agentDisabled}
            sx={{ flexShrink: 0 }}
          >
            {t('backupPlans.sourceChooser.addPath')}
          </Button>
        </Stack>

        {sourceKind === 'local' && (
          <Accordion
            disableGutters
            elevation={0}
            expanded={captureModeExpanded}
            onChange={(_, expanded) => setCaptureModeExpanded(expanded)}
            sx={{
              border: '1px solid',
              borderColor: 'divider',
              borderRadius: 1,
              bgcolor: 'background.paper',
              '&:before': { display: 'none' },
              '&.Mui-expanded': { mt: 2, mb: 0 },
            }}
          >
            <AccordionSummary
              expandIcon={<ChevronRight size={18} />}
              sx={{
                px: 1.75,
                minHeight: 48,
                '& .MuiAccordionSummary-content': {
                  alignItems: 'center',
                  gap: 1,
                  my: 0,
                },
                '& .MuiAccordionSummary-expandIconWrapper': {
                  transform: 'rotate(0deg)',
                  '&.Mui-expanded': { transform: 'rotate(90deg)' },
                },
              }}
            >
              <Typography variant="body2" fontWeight={500} color="text.secondary">
                {t('backupPlans.sourceChooser.advancedCaptureMode')}
              </Typography>
              <Typography
                variant="body2"
                color="text.primary"
                sx={{ ml: 'auto', mr: 0.5, fontWeight: 500 }}
              >
                {snapshotDraft.provider === 'none'
                  ? t('backupPlans.sourceChooser.captureModeDirect')
                  : snapshotDraft.provider === 'btrfs'
                    ? t('backupPlans.sourceChooser.snapshotModeBtrfs')
                    : t('backupPlans.sourceChooser.snapshotModeZfs')}
              </Typography>
            </AccordionSummary>
            <AccordionDetails sx={{ px: 1.75, pt: 2, pb: 1.75 }}>
              <Stack spacing={1.25}>
                <FormControl fullWidth size="small">
                  <InputLabel id="snapshot-mode-label">
                    {t('backupPlans.sourceChooser.snapshotMode')}
                  </InputLabel>
                  <Select
                    labelId="snapshot-mode-label"
                    value={snapshotDraft.provider}
                    label={t('backupPlans.sourceChooser.snapshotMode')}
                    onChange={(event) =>
                      updateSnapshotDraft({
                        provider: event.target.value as SnapshotProviderDraft,
                      })
                    }
                  >
                    <MenuItem value="none">
                      {t('backupPlans.sourceChooser.snapshotModeNone')}
                    </MenuItem>
                    <MenuItem value="btrfs">
                      {t('backupPlans.sourceChooser.snapshotModeBtrfs')}
                    </MenuItem>
                    <MenuItem value="zfs">
                      {t('backupPlans.sourceChooser.snapshotModeZfs')}
                    </MenuItem>
                  </Select>
                </FormControl>

                {snapshotDraft.provider !== 'none' && (
                  <Alert severity={selectedSnapshotCapability?.available ? 'info' : 'warning'}>
                    <Stack spacing={0.75}>
                      <Stack
                        direction="row"
                        spacing={0.75}
                        alignItems="center"
                        useFlexGap
                        flexWrap="wrap"
                      >
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {t('backupPlans.sourceChooser.snapshotRequirementsTitle')}
                        </Typography>
                        {selectedSnapshotCapability && (
                          <Chip
                            size="small"
                            variant="outlined"
                            label={t(
                              selectedSnapshotCapability.available
                                ? 'backupPlans.sourceChooser.snapshotToolAvailable'
                                : 'backupPlans.sourceChooser.snapshotToolMissing',
                              { command: selectedSnapshotCapability.command }
                            )}
                          />
                        )}
                      </Stack>
                      {(selectedSnapshotCapability?.requirements || []).map((requirement) => (
                        <Typography key={requirement} variant="caption">
                          {requirement}
                        </Typography>
                      ))}
                    </Stack>
                  </Alert>
                )}

                {snapshotDraft.provider === 'btrfs' && (
                  <TextField
                    label={t('backupPlans.sourceChooser.snapshotBtrfsStagingPath')}
                    value={snapshotDraft.stagingPath}
                    onChange={(event) => updateSnapshotDraft({ stagingPath: event.target.value })}
                    size="small"
                    fullWidth
                  />
                )}

                {snapshotDraft.provider === 'zfs' && (
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                    <TextField
                      label={t('backupPlans.sourceChooser.snapshotZfsDataset')}
                      value={snapshotDraft.dataset}
                      onChange={(event) => updateSnapshotDraft({ dataset: event.target.value })}
                      size="small"
                      fullWidth
                      error={zfsDatasetMissing}
                      helperText={
                        zfsDatasetMissing
                          ? t('backupPlans.sourceChooser.snapshotZfsRequired')
                          : undefined
                      }
                    />
                    <TextField
                      label={t('backupPlans.sourceChooser.snapshotZfsMountpoint')}
                      value={snapshotDraft.mountpoint}
                      onChange={(event) => updateSnapshotDraft({ mountpoint: event.target.value })}
                      size="small"
                      fullWidth
                      error={zfsMountpointMissing}
                      helperText={
                        zfsMountpointMissing
                          ? t('backupPlans.sourceChooser.snapshotZfsRequired')
                          : undefined
                      }
                    />
                  </Stack>
                )}

                {snapshotDraft.provider !== 'none' && (
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={snapshotDraft.recursive}
                        onChange={(event) =>
                          updateSnapshotDraft({ recursive: event.target.checked })
                        }
                        size="small"
                      />
                    }
                    label={t('backupPlans.sourceChooser.snapshotRecursive')}
                  />
                )}
              </Stack>
            </AccordionDetails>
          </Accordion>
        )}

        {mixedSourceTypesBlocked && (
          <Alert
            severity="info"
            icon={<Lock size={18} />}
            sx={{ py: 0.5, '& .MuiAlert-message': { py: 0.5 } }}
          >
            {t('backupPlans.sourceChooser.mixedSourceTypesRequiresPro')}
          </Alert>
        )}

        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            {t('backupPlans.sourceChooser.selectedSourceGroups')}
          </Typography>
          {fileDraftSourceLocations.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              {t('backupPlans.sourceChooser.summaryEmpty')}
            </Typography>
          ) : (
            <Stack spacing={1}>
              {fileDraftSourceLocations.map((location) => {
                const key = draftLocationKey(location)
                const isSinglePath = location.paths.length === 1
                const monospacePathSx = {
                  fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
                  fontSize: '0.8125rem',
                  color: 'text.primary',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  minWidth: 0,
                  flex: 1,
                } as const

                return (
                  <Paper
                    key={key}
                    variant="outlined"
                    sx={{
                      p: 1.25,
                      borderRadius: 1,
                      bgcolor: 'background.default',
                    }}
                  >
                    {isSinglePath ? (
                      <Stack
                        direction="row"
                        spacing={1.25}
                        alignItems="center"
                        sx={{ minWidth: 0 }}
                      >
                        <Box
                          sx={{
                            alignItems: 'center',
                            bgcolor: 'action.hover',
                            borderRadius: 1,
                            color: 'text.secondary',
                            display: 'flex',
                            height: 28,
                            justifyContent: 'center',
                            width: 28,
                            flexShrink: 0,
                          }}
                        >
                          {location.source_type === 'remote' ? (
                            <Server size={14} />
                          ) : location.source_type === 'agent' ? (
                            <Laptop size={14} />
                          ) : (
                            <HardDrive size={14} />
                          )}
                        </Box>
                        <Typography variant="subtitle2" noWrap sx={{ flexShrink: 0 }}>
                          {sourceLocationLabel(location, sshConnections, agentMachines, t)}
                        </Typography>
                        {location.snapshot && (
                          <Chip
                            size="small"
                            variant="outlined"
                            label={t('backupPlans.sourceChooser.snapshotChip', {
                              provider: location.snapshot.provider,
                            })}
                          />
                        )}
                        <Typography variant="caption" sx={{ flexShrink: 0, opacity: 0.6 }}>
                          ·
                        </Typography>
                        <Typography variant="body2" title={location.paths[0]} sx={monospacePathSx}>
                          {location.paths[0]}
                        </Typography>
                        <Tooltip title={t('backupPlans.sourceChooser.removePath')}>
                          <IconButton
                            aria-label={t('backupPlans.sourceChooser.removePath')}
                            onClick={() => removeSourcePath(key, location.paths[0])}
                            size="small"
                            sx={{ p: 0.25, flexShrink: 0 }}
                          >
                            <X size={13} />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title={t('backupPlans.sourceChooser.removeSourceGroup')}>
                          <IconButton
                            aria-label={t('backupPlans.sourceChooser.removeSourceGroup')}
                            onClick={() => removeSourceLocation(key)}
                            size="small"
                            sx={{ flexShrink: 0 }}
                          >
                            <Trash2 size={14} />
                          </IconButton>
                        </Tooltip>
                      </Stack>
                    ) : (
                      <Stack spacing={0.75}>
                        <Stack
                          direction="row"
                          spacing={1.25}
                          alignItems="center"
                          justifyContent="space-between"
                        >
                          <Stack
                            direction="row"
                            spacing={1.25}
                            alignItems="center"
                            sx={{ minWidth: 0 }}
                          >
                            <Box
                              sx={{
                                alignItems: 'center',
                                bgcolor: 'action.hover',
                                borderRadius: 1,
                                color: 'text.secondary',
                                display: 'flex',
                                height: 28,
                                justifyContent: 'center',
                                width: 28,
                                flexShrink: 0,
                              }}
                            >
                              {location.source_type === 'remote' ? (
                                <Server size={14} />
                              ) : location.source_type === 'agent' ? (
                                <Laptop size={14} />
                              ) : (
                                <HardDrive size={14} />
                              )}
                            </Box>
                            <Typography variant="subtitle2" noWrap>
                              {sourceLocationLabel(location, sshConnections, agentMachines, t)}
                            </Typography>
                            <Chip
                              size="small"
                              variant="outlined"
                              label={t('backupPlans.sourceChooser.pathCount', {
                                count: location.paths.length,
                              })}
                            />
                            {location.snapshot && (
                              <Chip
                                size="small"
                                variant="outlined"
                                label={t('backupPlans.sourceChooser.snapshotChip', {
                                  provider: location.snapshot.provider,
                                })}
                              />
                            )}
                          </Stack>
                          <Tooltip title={t('backupPlans.sourceChooser.removeSourceGroup')}>
                            <IconButton
                              aria-label={t('backupPlans.sourceChooser.removeSourceGroup')}
                              onClick={() => removeSourceLocation(key)}
                              size="small"
                            >
                              <Trash2 size={14} />
                            </IconButton>
                          </Tooltip>
                        </Stack>
                        <Stack spacing={0.25} sx={{ pl: 4.5 }}>
                          {location.paths.map((path) => (
                            <Stack
                              key={path}
                              direction="row"
                              spacing={0.5}
                              alignItems="center"
                              sx={{ minWidth: 0 }}
                            >
                              <Typography variant="body2" title={path} sx={monospacePathSx}>
                                {path}
                              </Typography>
                              <Tooltip title={t('backupPlans.sourceChooser.removePath')}>
                                <IconButton
                                  aria-label={t('backupPlans.sourceChooser.removePath')}
                                  onClick={() => removeSourcePath(key, path)}
                                  size="small"
                                  sx={{ p: 0.25, flexShrink: 0 }}
                                >
                                  <X size={13} />
                                </IconButton>
                              </Tooltip>
                            </Stack>
                          ))}
                        </Stack>
                      </Stack>
                    )}
                  </Paper>
                )
              })}
            </Stack>
          )}
        </Box>
      </Stack>
    )
  }

  const renderDatabaseList = () => {
    const queuedDatabaseLocations = draftSourceLocations.filter((location) => location.database)
    // Tab-level target picker: governs both "Scan for databases" (passed in as
    // initialScanTarget below) and template-tile clicks (chooseDatabase ->
    // applyDatabase reads lastScanContext.scanTarget). Mirrors the modal's
    // DestinationSelect + SshConnectionSelect pattern so the same control reads
    // as the same control across surfaces. Only local + remote here (matching
    // the scan modal); managed agents are not a scan target for databases yet.
    const databaseTarget = lastScanContext.scanTarget
    const hasRemoteOptions = sshConnections.length > 0
    const databaseTargetDestinations: DestinationOption[] = [
      {
        key: 'local',
        icon: <HardDrive size={16} />,
        label: t('backupPlans.sourceChooser.borgUiServer'),
        description: t('backupPlans.sourceChooser.localSourceDescription'),
      },
      {
        key: 'remote',
        icon: <Server size={16} />,
        label: t('backupPlans.sourceChooser.remoteMachine'),
        description: hasRemoteOptions
          ? t('backupPlans.sourceChooser.remoteMachineDescription')
          : t('backupPlans.sourceChooser.noRemoteMachines'),
        disabled: !hasRemoteOptions,
      },
    ]
    const handleDatabaseTargetChange = (key: string) => {
      if (key === 'local') {
        setLastScanContext({ scanTarget: { type: 'local', sshId: '' }, label: null })
        return
      }
      if (key === 'remote') {
        if (!hasRemoteOptions) return
        const fallbackId =
          databaseTarget.sshId &&
          sshConnections.some((connection) => connection.id === databaseTarget.sshId)
            ? databaseTarget.sshId
            : sshConnections[0].id
        setLastScanContext({ scanTarget: { type: 'remote', sshId: fallbackId }, label: null })
      }
    }
    const databaseRemoteDisabled = databaseTarget.type === 'remote' && !hasRemoteOptions

    return (
      <Stack spacing={2.5}>
        <Stack spacing={2}>
          <DestinationSelect
            value={databaseTarget.type}
            onChange={handleDatabaseTargetChange}
            destinations={databaseTargetDestinations}
            label={t('backupPlans.sourceChooser.scanTarget')}
          />
          {databaseTarget.type === 'remote' && hasRemoteOptions ? (
            <SshConnectionSelect
              value={databaseTarget.sshId || ''}
              onChange={(id) =>
                setLastScanContext({
                  scanTarget: { type: 'remote', sshId: id },
                  label: null,
                })
              }
              connections={sshConnections}
              label={t('backupPlans.sourceChooser.selectRemoteMachine')}
              emptyMessage={t('backupPlans.sourceChooser.noRemoteMachines')}
            />
          ) : (
            <Box
              sx={{
                border: 1,
                borderColor: 'divider',
                borderRadius: 1,
                bgcolor: 'action.hover',
                color: 'text.secondary',
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                px: 1.5,
                height: 56,
              }}
            >
              <HardDrive size={14} />
              <Typography variant="body2" color="text.secondary">
                {databaseRemoteDisabled
                  ? t('backupPlans.sourceChooser.noRemoteMachines')
                  : t('backupPlans.sourceChooser.readingFromLocal')}
              </Typography>
            </Box>
          )}
        </Stack>

        {queuedDatabaseLocations.length > 0 && (
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              {t('backupPlans.sourceChooser.selectedDatabases')}
            </Typography>
            <Stack spacing={1}>
              {queuedDatabaseLocations.map((location) => {
                const key = draftLocationKey(location)
                const database = location.database
                if (!database) return null
                const hasSourceScript =
                  Boolean(database.pre_backup_script_id || database.post_backup_script_id) ||
                  Boolean(queuedDatabaseScriptDrafts[key])
                const livePath = database.detected_source_path?.trim()
                const backupPaths =
                  database.backup_paths?.filter((path) => path.trim().length > 0) || []
                const backupPathLabel = (
                  backupPaths.length > 0 ? backupPaths : location.paths
                ).join(', ')
                return (
                  <Paper
                    key={key}
                    variant="outlined"
                    sx={{ p: 1.25, borderRadius: 1, bgcolor: 'background.default' }}
                  >
                    <Stack
                      direction={{ xs: 'column', sm: 'row' }}
                      spacing={1.25}
                      alignItems={{ xs: 'stretch', sm: 'center' }}
                      sx={{ minWidth: 0 }}
                    >
                      <Stack
                        direction="row"
                        spacing={1.25}
                        alignItems="center"
                        sx={{ minWidth: 0, flex: 1 }}
                      >
                        <DatabaseIcon size={16} />
                        <Stack spacing={0.2} sx={{ minWidth: 0, flex: 1 }}>
                          <Typography variant="subtitle2" noWrap>
                            {database.display_name}
                          </Typography>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{
                              fontFamily:
                                'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {sourceLocationLabel(location, sshConnections, agentMachines, t)}
                          </Typography>
                          {livePath && (
                            <Typography
                              variant="caption"
                              color="text.secondary"
                              title={livePath}
                              sx={{
                                fontFamily:
                                  'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                              }}
                            >
                              {t('backupPlans.sourceChooser.databaseLivePath')}: {livePath}
                            </Typography>
                          )}
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            title={backupPathLabel}
                            sx={{
                              fontFamily:
                                'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {t('backupPlans.sourceChooser.databaseBackupPaths')}: {backupPathLabel}
                          </Typography>
                        </Stack>
                      </Stack>
                      <Stack
                        direction="row"
                        spacing={0.75}
                        useFlexGap
                        flexWrap="wrap"
                        justifyContent={{ xs: 'flex-start', sm: 'flex-end' }}
                        alignItems="center"
                      >
                        <Chip
                          size="small"
                          variant={hasSourceScript ? 'filled' : 'outlined'}
                          color={hasSourceScript ? 'primary' : 'default'}
                          label={
                            hasSourceScript
                              ? t('backupPlans.sourceChooser.databaseScriptsAssigned')
                              : t('backupPlans.sourceChooser.databaseScriptsSkipped')
                          }
                        />
                        <Chip
                          size="small"
                          variant="outlined"
                          label={
                            database.capture_mode === 'original'
                              ? t('backupPlans.sourceChooser.captureModeOriginal')
                              : t('backupPlans.sourceChooser.captureModeDump')
                          }
                        />
                        <Tooltip title={t('backupPlans.sourceChooser.removeSourceGroup')}>
                          <IconButton
                            aria-label={t('backupPlans.sourceChooser.removeSourceGroup')}
                            onClick={() => removeSourceLocation(key)}
                            size="small"
                          >
                            <Trash2 size={14} />
                          </IconButton>
                        </Tooltip>
                      </Stack>
                    </Stack>
                  </Paper>
                )
              })}
            </Stack>
          </Box>
        )}

        <Button
          variant="contained"
          size="large"
          startIcon={<Search size={18} />}
          onClick={() => setScanDialogOpen(true)}
          sx={{ alignSelf: 'flex-start' }}
        >
          {t('backupPlans.sourceChooser.scanForDatabases')}
        </Button>

        {fallbackTemplates.length > 0 && (
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              {t('backupPlans.sourceChooser.pickTemplateManually')}
            </Typography>
            <Box
              sx={{
                display: 'grid',
                gap: 1.25,
                p: 0.75,
                mx: -0.75,
                gridTemplateColumns: {
                  xs: 'repeat(2, minmax(0, 1fr))',
                  sm: 'repeat(3, minmax(0, 1fr))',
                  md: 'repeat(4, minmax(0, 1fr))',
                },
              }}
            >
              {fallbackTemplates.map((database) => (
                <DatabaseBrandTile
                  key={database.id}
                  database={database}
                  detectedLabel={t('backupPlans.sourceChooser.detectedBadge')}
                  onClick={() => chooseDatabase(database)}
                />
              ))}
            </Box>
          </Box>
        )}
      </Stack>
    )
  }

  const renderExistingScriptSelect = (
    label: string,
    value: number | '',
    onChange: (value: number | '') => void
  ) => (
    <FormControl fullWidth size="small" disabled={loadingScripts}>
      <InputLabel>{label}</InputLabel>
      <Select
        value={value}
        label={label}
        onChange={(event) => {
          const nextValue = event.target.value
          onChange(nextValue ? Number(nextValue) : '')
        }}
      >
        <MenuItem value="">
          <em>{t('scriptSelector.none')}</em>
        </MenuItem>
        {scripts.map((script) => (
          <MenuItem key={script.id} value={script.id} title={script.name}>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="body2" sx={{ overflowWrap: 'anywhere', whiteSpace: 'normal' }}>
                {script.name}
              </Typography>
            </Box>
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  )

  const renderDatabaseDetail = () => {
    if (!selectedDatabase) return null

    const databaseNotes = selectedDatabase.notes.map((note) => note.trim()).filter(Boolean)

    // detection_source can be either a real filesystem path (when the scan
    // located a data dir) or a string like "pg_dump available on PATH" (when
    // only the client CLI was found). Show and use the discovered path only
    // when it looks like a real path, since that is the case where naming the
    // instance is useful.
    const detectedPath = databaseDetectedPath(selectedDatabase)

    // Per-engine clarification of how the pre-backup script targets the
    // discovered instance. logical_dump engines (PG / MySQL / Mongo) talk
    // to the daemon, not the filesystem, so the discovered path is purely
    // contextual; tell the user how to retarget. rdb_snapshot (Redis) also
    // uses the daemon but the dump file lands in the discovered dir. SQLite
    // never reaches this view (Task 10 routes it to file-source mode).
    const strategyHint = ((): string => {
      const engineId = selectedDatabase.id
      const strategy = selectedDatabase.backup_strategy
      if (strategy === 'logical_dump' && engineId === 'postgresql') {
        return t('backupPlans.sourceChooser.strategyHint.postgresql', {
          defaultValue:
            'The script runs pg_dump against the local PostgreSQL daemon. Set PGHOST, PGPORT, PGUSER, or PGDATABASE in the script to target a non-default instance.',
        })
      }
      if (strategy === 'logical_dump' && engineId === 'mysql') {
        return t('backupPlans.sourceChooser.strategyHint.mysql', {
          defaultValue:
            'The script runs mysqldump against the local MySQL/MariaDB daemon (default --host=localhost). Set MYSQL_HOST or MYSQL_DATABASE in the script to target a non-default instance.',
        })
      }
      if (strategy === 'logical_dump' && engineId === 'mongodb') {
        return t('backupPlans.sourceChooser.strategyHint.mongodb', {
          defaultValue:
            'The script runs mongodump against the local MongoDB daemon (default --uri=mongodb://localhost). Adjust --uri in the script to target a non-default instance.',
        })
      }
      if (strategy === 'rdb_snapshot' && engineId === 'redis') {
        return t('backupPlans.sourceChooser.strategyHint.redis', {
          defaultValue:
            'The script triggers a SAVE on the local Redis daemon and copies the resulting dump.rdb into the staging dir below.',
        })
      }
      return t('backupPlans.sourceChooser.discoveredAtHint', {
        defaultValue:
          'Live data directory. The pre-backup script targets this instance; Borg does not read these files directly.',
      })
    })()
    const detailScanTarget = lastScanContext.scanTarget
    const detailScanConnection =
      detailScanTarget.type === 'remote' && detailScanTarget.sshId
        ? sshConnections.find((connection) => connection.id === detailScanTarget.sshId)
        : null
    const sourceMachineLabel =
      lastScanContext.label ||
      (detailScanConnection
        ? `${detailScanConnection.username}@${detailScanConnection.host}`
        : detailScanTarget.type === 'remote'
          ? t('backupPlans.sourceChooser.remoteMachine')
          : t('backupPlans.sourceChooser.borgUiServer'))
    const canUseOriginalPath = Boolean(detectedPath)
    const effectiveCaptureMode: DatabaseCaptureMode =
      databaseCaptureMode === 'original' && canUseOriginalPath ? 'original' : 'dump'
    const effectiveDumpPath =
      databaseDumpPath.trim() || defaultDatabaseDumpPath(selectedDatabase, draftSourceLocations)
    const effectiveBackupPaths =
      effectiveCaptureMode === 'original' && detectedPath ? [detectedPath] : [effectiveDumpPath]

    return (
      <Stack spacing={2}>
        {databaseNotes.length > 0 && (
          <Box
            sx={{
              border: 1,
              borderColor: 'divider',
              borderRadius: 1,
              p: 1.25,
              bgcolor: 'action.hover',
            }}
          >
            <Stack spacing={0.75}>
              <Stack direction="row" spacing={0.75} alignItems="center">
                <Info size={14} />
                <Typography variant="caption" color="text.secondary" fontWeight={600}>
                  {t('backupPlans.sourceChooser.notesLabel')}
                </Typography>
              </Stack>
              <Stack component="ul" spacing={0.5} sx={{ m: 0, pl: 2.5 }}>
                {databaseNotes.map((note) => (
                  <Typography key={note} component="li" variant="body2">
                    {note}
                  </Typography>
                ))}
              </Stack>
            </Stack>
          </Box>
        )}
        {/* Single info block that explicitly names two distinct things:
            the live DB instance the pre-backup script targets, and the dump
            directory Borg actually captures. Previously these sat in two
            unconnected sections and users assumed they should match. */}
        <Box
          sx={{
            border: 1,
            borderColor: 'divider',
            borderRadius: 1,
            p: 1.5,
            bgcolor: 'background.default',
          }}
        >
          <Stack spacing={1.5}>
            <Stack spacing={0.25}>
              <Stack direction="row" spacing={0.75} alignItems="center">
                <Server size={14} />
                <Typography variant="caption" color="text.secondary" fontWeight={600}>
                  {t('backupPlans.sourceChooser.databaseSourceMachine')}
                </Typography>
              </Stack>
              <Typography variant="body2" sx={{ pl: 2.5 }}>
                {sourceMachineLabel}
              </Typography>
            </Stack>
            {detectedPath && (
              <Stack spacing={0.25}>
                <Stack direction="row" spacing={0.75} alignItems="center">
                  <DatabaseIcon size={14} />
                  <Typography variant="caption" color="text.secondary" fontWeight={600}>
                    {t('backupPlans.sourceChooser.databaseLivePath')}
                  </Typography>
                </Stack>
                <Typography
                  sx={{
                    fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace',
                    fontSize: '0.8125rem',
                    wordBreak: 'break-all',
                    pl: 2.5,
                  }}
                >
                  {detectedPath}
                </Typography>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ pl: 2.5, fontStyle: 'italic' }}
                >
                  {strategyHint}
                </Typography>
              </Stack>
            )}
            <Stack spacing={0.25}>
              <Stack direction="row" spacing={0.75} alignItems="center">
                <HardDrive size={14} />
                <Typography variant="caption" color="text.secondary" fontWeight={600}>
                  {t('backupPlans.sourceChooser.databaseBackupPaths')}
                </Typography>
              </Stack>
              <Typography
                sx={{
                  fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace',
                  fontSize: '0.8125rem',
                  wordBreak: 'break-all',
                  pl: 2.5,
                }}
              >
                {effectiveBackupPaths.join(', ')}
              </Typography>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ pl: 2.5, fontStyle: 'italic' }}
              >
                {t('backupPlans.sourceChooser.borgWillBackUpHint', {
                  defaultValue:
                    'Dump output staging directory. The pre-backup script writes the dump here; Borg captures it.',
                })}
              </Typography>
            </Stack>
          </Stack>
        </Box>
        <Accordion
          disableGutters
          elevation={0}
          expanded={captureModeExpanded}
          onChange={(_, expanded) => setCaptureModeExpanded(expanded)}
          sx={{
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 1,
            bgcolor: 'background.paper',
            '&:before': { display: 'none' },
          }}
        >
          <AccordionSummary
            expandIcon={<ChevronRight size={18} />}
            sx={{
              px: 1.75,
              minHeight: 48,
              '& .MuiAccordionSummary-content': { alignItems: 'center', gap: 1, my: 0 },
              '& .MuiAccordionSummary-expandIconWrapper': {
                transform: 'rotate(0deg)',
                '&.Mui-expanded': { transform: 'rotate(90deg)' },
              },
            }}
          >
            <Typography variant="body2" fontWeight={500} color="text.secondary">
              {t('backupPlans.sourceChooser.captureModeDatabase')}
            </Typography>
            <Typography
              variant="body2"
              color="text.primary"
              sx={{ ml: 'auto', mr: 0.5, fontWeight: 500 }}
            >
              {effectiveCaptureMode === 'original'
                ? t('backupPlans.sourceChooser.captureModeOriginal')
                : t('backupPlans.sourceChooser.captureModeDump')}
            </Typography>
          </AccordionSummary>
          <AccordionDetails sx={{ px: 1.75, pt: 2, pb: 1.75 }}>
            <Stack spacing={1.5}>
              <RadioGroup
                value={databaseCaptureMode}
                onChange={(event) =>
                  setDatabaseCaptureMode(event.target.value as DatabaseCaptureMode)
                }
              >
                <FormControlLabel
                  value="dump"
                  control={<Radio size="small" />}
                  label={t('backupPlans.sourceChooser.captureModeDump')}
                />
                <FormControlLabel
                  value="original"
                  control={<Radio size="small" />}
                  disabled={!canUseOriginalPath}
                  label={t('backupPlans.sourceChooser.captureModeOriginal')}
                />
              </RadioGroup>
              {databaseCaptureMode === 'dump' ? (
                <TextField
                  label={t('backupPlans.sourceChooser.databaseDumpPath')}
                  value={databaseDumpPath}
                  onChange={(event) => setDatabaseDumpPath(event.target.value)}
                  size="small"
                  fullWidth
                />
              ) : (
                <Alert severity="warning" icon={<Info size={16} />}>
                  <Typography variant="body2">
                    {canUseOriginalPath
                      ? t('backupPlans.sourceChooser.captureModeOriginalWarning', {
                          defaultValue:
                            'Borg will read the live database files directly. Use this only when the database is stopped or you have another consistency mechanism.',
                        })
                      : t('backupPlans.sourceChooser.captureModeOriginalUnavailable', {
                          defaultValue: 'Original path mode requires a detected filesystem path.',
                        })}
                  </Typography>
                </Alert>
              )}
            </Stack>
          </AccordionDetails>
        </Accordion>
        <Divider />
        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            {t('backupPlans.sourceChooser.scriptDrafts')}
          </Typography>
          <RadioGroup
            row
            value={scriptMode}
            onChange={(event) => setScriptMode(event.target.value as ScriptMode)}
          >
            <FormControlLabel
              value="create"
              control={<Radio size="small" />}
              label={t('backupPlans.sourceChooser.createScripts')}
            />
            <FormControlLabel
              value="reuse"
              control={<Radio size="small" />}
              label={t('backupPlans.sourceChooser.reuseScripts')}
            />
            <FormControlLabel
              value="skip"
              control={<Radio size="small" />}
              label={t('backupPlans.sourceChooser.skipScripts')}
            />
          </RadioGroup>
        </Box>
        {scriptMode === 'skip' && (
          // Without a pre-backup script the staging dir is never populated,
          // so Borg captures an empty (or stale) archive. Loud, inline
          // warning so an operator who knows what they are doing can pick
          // skip deliberately, but a casual user does not silently end up
          // with a useless backup.
          <Alert severity="warning" icon={<Info size={16} />}>
            <Typography variant="body2" sx={{ mb: 0.5 }}>
              {t('backupPlans.sourceChooser.skipScriptsWarningTitle', {
                defaultValue: 'No script will populate the dump.',
              })}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t('backupPlans.sourceChooser.skipScriptsWarningBody', {
                defaultValue:
                  'Borg will only capture what is already in {{path}}. If you do not have an external job populating this directory, the backup will be empty. Pick "Create new scripts" to have Borg UI generate the dump for you.',
                path: selectedDatabase.source_directories.join(', '),
              })}
            </Typography>
          </Alert>
        )}
        {scriptMode === 'create' && (
          <Stack spacing={1.5}>
            <TextField
              label={t('backupPlans.sourceChooser.preScriptName')}
              value={preScriptName}
              onChange={(event) => setPreScriptName(event.target.value)}
              size="small"
              fullWidth
            />
            <CodeEditor
              label={t('backupPlans.sourceChooser.preScriptDraft')}
              value={preScriptContent}
              onChange={setPreScriptContent}
              height="180px"
              language="shell"
            />
            <TextField
              label={t('backupPlans.sourceChooser.postScriptName')}
              value={postScriptName}
              onChange={(event) => setPostScriptName(event.target.value)}
              size="small"
              fullWidth
            />
            <CodeEditor
              label={t('backupPlans.sourceChooser.postScriptDraft')}
              value={postScriptContent}
              onChange={setPostScriptContent}
              height="160px"
              language="shell"
            />
          </Stack>
        )}
        {scriptMode === 'reuse' && (
          <Stack spacing={1.5}>
            {renderExistingScriptSelect(
              t('backupPlans.sourceChooser.preExistingScript'),
              preExistingScriptId,
              setPreExistingScriptId
            )}
            {renderExistingScriptSelect(
              t('backupPlans.sourceChooser.postExistingScript'),
              postExistingScriptId,
              setPostExistingScriptId
            )}
          </Stack>
        )}
      </Stack>
    )
  }

  const renderContainer = () => {
    const sourceKind: 'local' | 'remote' | 'agent' = selectedSourceKey.startsWith('remote:')
      ? 'remote'
      : selectedSourceKey.startsWith('agent:')
        ? 'agent'
        : 'local'
    const selectedRemoteIdNum = selectedSourceKey.startsWith('remote:')
      ? Number(selectedSourceKey.split(':')[1])
      : 0
    const selectedAgentIdNum = selectedSourceKey.startsWith('agent:')
      ? Number(selectedSourceKey.split(':')[1])
      : 0
    const agentRepoConstraint = getAgentRepoConstraint(wizardState, fullRepositories, agentMachines)
    const hasRemoteOptions = sshConnections.length > 0
    const hasAgentOptions = agentMachines.length > 0
    const remoteDisabled = sourceKind === 'remote' && !hasRemoteOptions
    const agentDisabled = sourceKind === 'agent' && (!canUseManagedAgents || !hasAgentOptions)
    const lockedByAgentRepo = !!agentRepoConstraint
    const queuedContainerLocations = draftSourceLocations.filter((location) => location.container)
    const effectiveExportPath =
      containerExportPath.trim() ||
      (containerName.trim()
        ? defaultContainerExportPath(containerName)
        : DEFAULT_CONTAINER_EXPORT_ROOT)

    const handleSourceKindChange = (key: string) => {
      if (key === 'local') {
        selectSourceKey('local')
        return
      }
      if (key === 'remote') {
        if (!hasRemoteOptions) return
        const targetId =
          selectedRemoteIdNum &&
          sshConnections.some((connection) => connection.id === selectedRemoteIdNum)
            ? selectedRemoteIdNum
            : sshConnections[0].id
        selectSourceKey(`remote:${targetId}`)
        return
      }
      if (key === 'agent') {
        if (!canUseManagedAgents || !hasAgentOptions) return
        if (agentRepoConstraint) {
          selectSourceKey(`agent:${agentRepoConstraint.agentId}`)
          return
        }
        const targetId =
          selectedAgentIdNum && agentMachines.some((agent) => agent.id === selectedAgentIdNum)
            ? selectedAgentIdNum
            : agentMachines[0].id
        selectSourceKey(`agent:${targetId}`)
      }
    }

    const sourceKindDestinations: DestinationOption[] = [
      {
        key: 'local',
        icon: lockedByAgentRepo ? <Lock size={16} /> : <HardDrive size={16} />,
        label: t('backupPlans.sourceChooser.borgUiServer'),
        description: lockedByAgentRepo
          ? t('backupPlans.sourceChooser.agentRepoLockedLocal', {
              agent: agentRepoConstraint.agentName,
            })
          : t('backupPlans.sourceChooser.localSourceDescription'),
        disabled: lockedByAgentRepo,
      },
      {
        key: 'remote',
        icon: lockedByAgentRepo ? <Lock size={16} /> : <Server size={16} />,
        label: t('backupPlans.sourceChooser.remoteMachine'),
        description: lockedByAgentRepo
          ? t('backupPlans.sourceChooser.agentRepoLockedRemote', {
              agent: agentRepoConstraint.agentName,
            })
          : hasRemoteOptions
            ? t('backupPlans.sourceChooser.remoteMachineDescription')
            : t('backupPlans.sourceChooser.noRemoteMachines'),
        disabled: !hasRemoteOptions || lockedByAgentRepo,
      },
      {
        key: 'agent',
        icon: !canUseManagedAgents ? <Lock size={16} /> : <Laptop size={16} />,
        label: t('backupPlans.sourceChooser.managedAgent'),
        description: !canUseManagedAgents
          ? t('backupPlans.sourceChooser.managedAgentRequiresPro')
          : hasAgentOptions
            ? t('backupPlans.sourceChooser.managedAgentDescription')
            : t('backupPlans.sourceChooser.noManagedAgents'),
        disabled: !canUseManagedAgents || !hasAgentOptions,
      },
    ]

    return (
      <Stack spacing={2.5}>
        {agentRepoConstraint && (
          <Alert
            severity="info"
            icon={<Info size={18} />}
            sx={{ py: 0.5, '& .MuiAlert-message': { py: 0.5 } }}
          >
            {t('backupPlans.sourceChooser.agentRepoConstraintBanner', {
              agent: agentRepoConstraint.agentName,
            })}
          </Alert>
        )}

        <Stack spacing={2}>
          <DestinationSelect
            value={sourceKind}
            onChange={handleSourceKindChange}
            destinations={sourceKindDestinations}
            label={t('backupPlans.sourceChooser.containerSourceMachine')}
          />
          {sourceKind === 'remote' && hasRemoteOptions ? (
            <SshConnectionSelect
              value={selectedRemoteIdNum || ''}
              onChange={(id) => selectSourceKey(`remote:${id}`)}
              connections={sshConnections}
              label={t('backupPlans.sourceChooser.selectRemoteMachine')}
              emptyMessage={t('backupPlans.sourceChooser.noRemoteMachines')}
              hideEmptyAlert
            />
          ) : sourceKind === 'agent' &&
            canUseManagedAgents &&
            hasAgentOptions &&
            agentRepoConstraint ? (
            <Box
              sx={{
                border: 1,
                borderColor: 'divider',
                borderRadius: 1,
                bgcolor: 'action.hover',
                color: 'text.secondary',
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                px: 1.5,
                height: 56,
              }}
            >
              <Lock size={14} />
              <Typography variant="body2" color="text.secondary">
                {t('backupPlans.sourceChooser.agentRepoLockedAgentPicker', {
                  agent: agentRepoConstraint.agentName,
                })}
              </Typography>
            </Box>
          ) : sourceKind === 'agent' && canUseManagedAgents && hasAgentOptions ? (
            <ManagedAgentSelect
              value={selectedAgentIdNum || ''}
              onChange={(id) => selectSourceKey(`agent:${id}`)}
              agents={agentMachines}
              label={t('backupPlans.sourceChooser.selectManagedAgent')}
              emptyMessage={t('backupPlans.sourceChooser.noManagedAgents')}
              labelId="container-agent-machine-label"
              hideEmptyAlert
            />
          ) : (
            <Box
              sx={{
                border: 1,
                borderColor: 'divider',
                borderRadius: 1,
                bgcolor: 'action.hover',
                color: 'text.secondary',
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                px: 1.5,
                height: 56,
              }}
            >
              {sourceKind === 'agent' ? <Laptop size={14} /> : <HardDrive size={14} />}
              <Typography variant="body2" color="text.secondary">
                {agentDisabled
                  ? t(
                      canUseManagedAgents
                        ? 'backupPlans.sourceChooser.noManagedAgents'
                        : 'backupPlans.sourceChooser.managedAgentRequiresPro'
                    )
                  : remoteDisabled
                    ? t('backupPlans.sourceChooser.noRemoteMachines')
                    : t('backupPlans.sourceChooser.readingFromLocal')}
              </Typography>
            </Box>
          )}
        </Stack>

        <Alert
          severity="info"
          icon={<Info size={18} />}
          sx={{ '& .MuiAlert-message': { width: '100%' } }}
        >
          <Typography variant="body2">
            {t('backupPlans.sourceChooser.containerExportHint')}
          </Typography>
        </Alert>

        <Stack spacing={1.5}>
          <TextField
            label={t('backupPlans.sourceChooser.containerName')}
            value={containerName}
            onChange={(event) => handleContainerNameChange(event.target.value)}
            size="small"
            fullWidth
            disabled={remoteDisabled || agentDisabled}
          />
          <TextField
            label={t('backupPlans.sourceChooser.containerImage')}
            value={containerImage}
            onChange={(event) => setContainerImage(event.target.value)}
            size="small"
            fullWidth
            disabled={remoteDisabled || agentDisabled}
          />
          <TextField
            label={t('backupPlans.sourceChooser.containerExportPath')}
            value={containerExportPath}
            onChange={(event) => handleContainerExportPathChange(event.target.value)}
            size="small"
            fullWidth
            disabled={remoteDisabled || agentDisabled}
          />
          <Button
            variant="contained"
            startIcon={<Plus size={16} />}
            onClick={queueContainerSource}
            disabled={
              !containerName.trim() ||
              !effectiveExportPath.trim() ||
              remoteDisabled ||
              agentDisabled
            }
            sx={{ alignSelf: 'flex-start' }}
          >
            {t('backupPlans.sourceChooser.addContainer')}
          </Button>
        </Stack>

        {queuedContainerLocations.length > 0 && (
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              {t('backupPlans.sourceChooser.selectedContainers')}
            </Typography>
            <Stack spacing={1}>
              {queuedContainerLocations.map((location) => {
                const key = draftLocationKey(location)
                const container = location.container
                if (!container) return null
                const hasSourceScript =
                  Boolean(container.pre_backup_script_id || container.post_backup_script_id) ||
                  Boolean(queuedContainerScriptDrafts[key])
                return (
                  <Paper
                    key={key}
                    variant="outlined"
                    sx={{ p: 1.25, borderRadius: 1, bgcolor: 'background.default' }}
                  >
                    <Stack
                      direction={{ xs: 'column', sm: 'row' }}
                      spacing={1.25}
                      alignItems={{ xs: 'stretch', sm: 'center' }}
                      sx={{ minWidth: 0 }}
                    >
                      <Stack
                        direction="row"
                        spacing={1.25}
                        alignItems="center"
                        sx={{ minWidth: 0, flex: 1 }}
                      >
                        <ContainerIcon size={16} />
                        <Stack spacing={0.2} sx={{ minWidth: 0, flex: 1 }}>
                          <Typography variant="subtitle2" noWrap>
                            {container.display_name}
                          </Typography>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{
                              fontFamily:
                                'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {sourceLocationLabel(location, sshConnections, agentMachines, t)}
                          </Typography>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            title={container.export_path}
                            sx={{
                              fontFamily:
                                'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {container.export_path}
                          </Typography>
                        </Stack>
                      </Stack>
                      <Stack
                        direction="row"
                        spacing={0.75}
                        useFlexGap
                        flexWrap="wrap"
                        justifyContent={{ xs: 'flex-start', sm: 'flex-end' }}
                        alignItems="center"
                      >
                        {container.image && (
                          <Chip size="small" variant="outlined" label={container.image} />
                        )}
                        <Chip
                          size="small"
                          variant={hasSourceScript ? 'filled' : 'outlined'}
                          color={hasSourceScript ? 'primary' : 'default'}
                          label={t('backupPlans.sourceChooser.containerScriptsAssigned')}
                        />
                        <Chip
                          size="small"
                          variant="outlined"
                          label={t('backupPlans.sourceChooser.containerModeExport')}
                        />
                        <Tooltip title={t('backupPlans.sourceChooser.removeSourceGroup')}>
                          <IconButton
                            aria-label={t('backupPlans.sourceChooser.removeSourceGroup')}
                            onClick={() => removeSourceLocation(key)}
                            size="small"
                          >
                            <Trash2 size={14} />
                          </IconButton>
                        </Tooltip>
                      </Stack>
                    </Stack>
                  </Paper>
                )
              })}
            </Stack>
          </Box>
        )}
      </Stack>
    )
  }

  const content = (() => {
    if (view === 'database') return renderDatabaseList()
    if (view === 'database-detail') return renderDatabaseDetail()
    if (view === 'container') return renderContainer()
    return renderPaths()
  })()

  return (
    <ResponsiveDialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      PaperProps={{
        sx: {
          height: { xs: 'auto', md: 'min(860px, calc(100vh - 64px))' },
          display: 'flex',
          flexDirection: 'column',
        },
      }}
      footer={
        <DialogActions>
          <Button onClick={handleFooterCancel}>{t('common.buttons.cancel')}</Button>
          {/* Apply works the same on the file-paths view and the database
              scan list: commit whatever sources are queued in drafts. We
              surface the same button on both so the user can quick-add a
              detected SQLite from the database tab and apply without
              bouncing to the files tab. */}
          {(view === 'paths' || view === 'database' || view === 'container') && (
            <Button
              variant="contained"
              onClick={applyPaths}
              disabled={
                applying ||
                cleanedDraftSourceLocations.length === 0 ||
                mixedSourceTypesBlocked ||
                !areSnapshotDraftsValid(
                  draftSourceLocations,
                  snapshotDraftsBySourceKey,
                  selectedSourceKey,
                  snapshotDraft
                )
              }
            >
              {t('backupPlans.sourceChooser.applyPaths')}
            </Button>
          )}
          {view === 'database-detail' && (
            <Button
              variant="contained"
              onClick={applyDatabase}
              disabled={
                applying ||
                (databaseCaptureMode === 'original' &&
                  !(selectedDatabase && databaseDetectedPath(selectedDatabase))) ||
                (databaseCaptureMode === 'dump' &&
                  !(
                    databaseDumpPath.trim() ||
                    (selectedDatabase
                      ? defaultDatabaseDumpPath(selectedDatabase, draftSourceLocations)
                      : '')
                  ))
              }
            >
              {t('backupPlans.sourceChooser.applyDatabase')}
            </Button>
          )}
        </DialogActions>
      }
    >
      <DialogTitle sx={{ pb: 1.5 }}>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
          <Typography component="span" variant="h6" sx={{ fontWeight: 600 }} noWrap>
            {view === 'database' && t('backupPlans.sourceChooser.databaseBackupTitle')}
            {view === 'database-detail' && databaseDisplayTitle(selectedDatabase, t)}
            {view === 'container' && t('backupPlans.sourceChooser.containerBackupTitle')}
            {view === 'paths' && t('backupPlans.sourceChooser.title')}
          </Typography>
        </Stack>
      </DialogTitle>
      <DialogContent sx={{ pt: 1.5, flex: 1, overflowY: 'auto' }}>
        <Stack spacing={2.5}>
          {view !== 'database-detail' && (
            <SourceKindPivot
              view={view}
              onChange={(next) => setView(next)}
              counts={{
                files: draftSourceLocations
                  .filter((location) => !location.database && !location.container)
                  .reduce((sum, location) => sum + location.paths.length, 0),
                database: draftSourceLocations.filter((location) => location.database).length,
                container: draftSourceLocations.filter((location) => location.container).length,
              }}
              t={t}
            />
          )}
          {content}
        </Stack>
      </DialogContent>
      <DatabaseScanDialog
        open={scanDialogOpen}
        onClose={() => setScanDialogOpen(false)}
        onChoose={handleScanChoice}
        sshConnections={sshConnections}
        t={t}
        // Seed the scan modal with the tab-level picker's current target so
        // the user sees the machine they just chose. handleScanChoice writes
        // the modal's final target back to lastScanContext on commit.
        initialScanTarget={lastScanContext.scanTarget}
      />
    </ResponsiveDialog>
  )
}

type SourceKindCounts = { files: number; database: number; container: number }

interface SourceKindPivotProps {
  view: SourceChoiceView
  onChange: (next: SourceChoiceView) => void
  counts: SourceKindCounts
  t: TFunction
}

function SourceKindPivot({ view, onChange, counts, t }: SourceKindPivotProps) {
  const segments: {
    key: 'files' | 'database' | 'container'
    target: SourceChoiceView
    labelKey: string
    Icon: typeof FileText
  }[] = [
    {
      key: 'files',
      target: 'paths',
      labelKey: 'backupPlans.sourceChooser.kindFiles',
      Icon: FileText,
    },
    {
      key: 'database',
      target: 'database',
      labelKey: 'backupPlans.sourceChooser.kindDatabase',
      Icon: DatabaseIcon,
    },
    {
      key: 'container',
      target: 'container',
      labelKey: 'backupPlans.sourceChooser.kindContainer',
      Icon: ContainerIcon,
    },
  ]

  const activeKey: 'files' | 'database' | 'container' =
    view === 'database' || view === 'database-detail'
      ? 'database'
      : view === 'container'
        ? 'container'
        : 'files'

  return (
    <Box
      role="tablist"
      aria-label={t('backupPlans.sourceChooser.chooseSource')}
      sx={{
        display: 'inline-flex',
        alignSelf: 'flex-start',
        p: 0.5,
        gap: 0.5,
        bgcolor: 'action.hover',
        borderRadius: '10px',
      }}
    >
      {segments.map((segment) => {
        const selected = activeKey === segment.key
        return (
          <ButtonBase
            key={segment.key}
            role="tab"
            aria-selected={selected}
            onClick={() => {
              if (segment.target !== view) onChange(segment.target)
            }}
            sx={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 1,
              minHeight: 38,
              px: 1.75,
              py: 1,
              borderRadius: '8px',
              bgcolor: selected ? 'background.paper' : 'transparent',
              boxShadow: selected ? 1 : 0,
              fontWeight: selected ? 600 : 500,
              fontSize: '0.8125rem',
              color: selected ? 'text.primary' : 'text.secondary',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
              '&:hover': selected ? undefined : { color: 'text.primary' },
            }}
          >
            <segment.Icon size={14} />
            {t(segment.labelKey)}
            {/* Count chip surfaces "this tab has N items queued" so the user
                knows where things landed without switching tabs to check. */}
            {counts[segment.key] > 0 && (
              <Chip
                label={counts[segment.key]}
                size="small"
                color="success"
                sx={{
                  height: 18,
                  minWidth: 18,
                  fontSize: '0.6875rem',
                  fontWeight: 700,
                  '& .MuiChip-label': { px: 0.625 },
                }}
              />
            )}
          </ButtonBase>
        )
      })}
    </Box>
  )
}

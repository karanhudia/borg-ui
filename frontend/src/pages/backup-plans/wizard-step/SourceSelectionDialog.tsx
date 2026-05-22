import { type ReactNode, useEffect, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Checkbox,
  Chip,
  CircularProgress,
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
  Skeleton,
  Stack,
  TextField,
  Tooltip,
  Typography,
  alpha,
} from '@mui/material'
import {
  ArrowLeft,
  Database as DatabaseIcon,
  HardDrive,
  Info,
  Laptop,
  Plus,
  RefreshCw,
  Server,
  Trash2,
  X,
} from 'lucide-react'
import { SiMariadb, SiMongodb, SiMysql, SiPostgresql, SiRedis, SiSqlite } from 'react-icons/si'
import type { IconType } from 'react-icons'
import type { TFunction } from 'i18next'

import CodeEditor from '../../../components/CodeEditor'
import PathSelectorField from '../../../components/PathSelectorField'
import ResponsiveDialog from '../../../components/ResponsiveDialog'
import {
  type AgentMachineResponse,
  type FilesystemSnapshotCapabilitiesResponse,
  sourceDiscoveryAPI,
  type DatabaseScanResponse,
  type SourceDiscoveryDatabase,
  type SourceDiscoveryResponse,
  type SourceDiscoveryScriptDraft,
} from '../../../services/api'
import type { Repository, SourceLocation, SourceSnapshotConfig, SourceType } from '../../../types'
import type { ScriptOption, SSHConnection, WizardState } from '../types'
import type { SourceScriptCreateInput } from './types'

type SourceChoiceView = 'paths' | 'database' | 'database-detail'
type ScriptMode = 'create' | 'reuse' | 'skip'
type SourceKey = 'local' | `remote:${number}` | `agent:${number}`
type SnapshotProviderDraft = 'none' | 'btrfs' | 'zfs'

const DEFAULT_SNAPSHOT_STAGING_PATH = '/var/tmp/borg-ui/snapshots'

const DEFAULT_DB_SCAN_PATHS = [
  '/var/lib/postgresql',
  '/var/lib/mysql',
  '/var/lib/mongodb',
  '/var/lib/redis',
]

type ScanErrorKind = 'ENDPOINT_MISSING' | 'OTHER'

interface ScanErrorState {
  kind: ScanErrorKind
  detail: string | null
}

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

function snapshotFromDraft(draft: SnapshotDraft): SourceSnapshotConfig | undefined {
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
  if (!dataset || !mountpoint) return undefined
  return {
    provider: 'zfs',
    dataset,
    mountpoint,
    recursive: draft.recursive,
  }
}

function classifyScanError(err: unknown): ScanErrorState {
  if (err && typeof err === 'object' && 'response' in err) {
    const response = (err as { response?: { status?: number; data?: { detail?: string } } })
      .response
    if (response?.status === 404 || response?.status === 405) {
      return { kind: 'ENDPOINT_MISSING', detail: null }
    }
    if (response?.data?.detail) {
      return { kind: 'OTHER', detail: String(response.data.detail) }
    }
  }
  return { kind: 'OTHER', detail: null }
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
}

interface DatabaseBrand {
  Icon: IconType
  color: string
}

const DATABASE_BRANDS: Record<string, DatabaseBrand> = {
  postgresql: { Icon: SiPostgresql, color: '#336791' },
  mysql: { Icon: SiMysql, color: '#00758F' },
  mariadb: { Icon: SiMariadb, color: '#003545' },
  'mysql / mariadb': { Icon: SiMysql, color: '#00758F' },
  mongodb: { Icon: SiMongodb, color: '#00684A' },
  redis: { Icon: SiRedis, color: '#FF4438' },
  sqlite: { Icon: SiSqlite, color: '#003B57' },
}

function brandFor(engine: string): DatabaseBrand {
  const normalised = engine.trim().toLowerCase()
  if (DATABASE_BRANDS[normalised]) return DATABASE_BRANDS[normalised]
  const key = Object.keys(DATABASE_BRANDS).find((name) => normalised.includes(name))
  if (key) return DATABASE_BRANDS[key]
  return { Icon: SiPostgresql, color: '#5C6B7A' }
}

interface DatabaseBrandTileProps {
  database: SourceDiscoveryDatabase
  detectedLabel: string
  onClick: () => void
}

function DatabaseBrandTile({ database, detectedLabel, onClick }: DatabaseBrandTileProps) {
  const brand = brandFor(database.engine)
  const BrandIcon = brand.Icon

  return (
    <Card
      variant="outlined"
      sx={{
        borderRadius: 1,
        transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
        '&:hover': {
          transform: 'translateY(-2px)',
          boxShadow: (theme) => `0 2px 6px ${alpha(theme.palette.text.primary, 0.08)}`,
          borderColor: 'text.primary',
        },
      }}
    >
      <CardActionArea
        component="button"
        onClick={onClick}
        sx={{ height: '100%', p: 1.25, display: 'flex', justifyContent: 'flex-start' }}
      >
        <Stack
          direction="row"
          spacing={1.25}
          alignItems="center"
          sx={{ width: '100%', minWidth: 0 }}
        >
          <Box
            sx={{
              alignItems: 'center',
              bgcolor: brand.color,
              borderRadius: 1.5,
              boxShadow: `0 4px 12px ${alpha(brand.color, 0.35)}`,
              color: 'common.white',
              display: 'flex',
              height: 36,
              justifyContent: 'center',
              width: 36,
              flexShrink: 0,
            }}
            aria-hidden
          >
            <BrandIcon size={20} />
          </Box>
          <Stack spacing={0.25} sx={{ minWidth: 0, textAlign: 'left' }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, lineHeight: 1.2 }} noWrap>
              {database.engine}
            </Typography>
            {database.detected && (
              <Stack direction="row" spacing={0.5} alignItems="center">
                <Box
                  sx={{
                    width: 6,
                    height: 6,
                    borderRadius: '50%',
                    bgcolor: 'success.main',
                    flexShrink: 0,
                  }}
                />
                <Typography variant="caption" color="success.main" sx={{ fontWeight: 500 }} noWrap>
                  {detectedLabel}
                </Typography>
              </Stack>
            )}
          </Stack>
        </Stack>
      </CardActionArea>
    </Card>
  )
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
      return cleaned
    })
    .filter((location) => location.paths.length > 0)
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
  const selectedRepositories = wizardState.repositoryIds
    .map((id) => fullRepositories.find((repository) => repository.id === id))
    .filter((repository): repository is Repository => Boolean(repository))
  if (selectedRepositories.length !== 1) return null
  const repository = selectedRepositories[0]
  if (repository.executor_type !== 'agent' || !repository.agent_machine_id) return null
  return `agent:${repository.agent_machine_id}`
}

function agentDisplayName(agent?: AgentMachineResponse | null) {
  if (!agent) return ''
  return agent.hostname || agent.name || `Agent #${agent.id}`
}

interface RepoStyleSourceCardProps {
  selected: boolean
  disabled?: boolean
  icon: ReactNode
  title: string
  description: string
  onClick: () => void
}

function RepoStyleSourceCard({
  selected,
  disabled = false,
  icon,
  title,
  description,
  onClick,
}: RepoStyleSourceCardProps) {
  return (
    <Card
      variant="outlined"
      sx={{
        flex: 1,
        border: 1,
        borderColor: selected ? 'primary.main' : 'divider',
        boxShadow: selected
          ? (theme) =>
              `inset 0 0 0 1px ${theme.palette.primary.main}, 0 4px 12px ${alpha(theme.palette.primary.main, 0.2)}`
          : 'none',
        bgcolor: selected ? (theme) => alpha(theme.palette.primary.main, 0.08) : 'background.paper',
        opacity: disabled ? 0.5 : 1,
        display: 'flex',
        transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        transform: selected ? 'translateY(-2px)' : 'none',
        '&:hover': !disabled
          ? {
              transform: 'translateY(-2px)',
              boxShadow: selected
                ? (theme) =>
                    `inset 0 0 0 1px ${theme.palette.primary.main}, 0 4px 12px ${alpha(theme.palette.primary.main, 0.2)}`
                : (theme) => `0 4px 12px ${alpha(theme.palette.text.primary, 0.08)}`,
              borderColor: selected ? 'primary.main' : 'text.primary',
            }
          : {},
      }}
    >
      <CardActionArea
        component="button"
        aria-pressed={selected}
        onClick={onClick}
        disabled={disabled}
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'stretch',
          height: '100%',
          p: 1,
        }}
      >
        <CardContent sx={{ flex: 1 }}>
          <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 1 }}>
            <Box
              sx={{
                alignItems: 'center',
                bgcolor: selected ? 'primary.main' : 'action.hover',
                borderRadius: 3,
                color: selected ? 'white' : 'text.secondary',
                display: 'flex',
                height: 48,
                justifyContent: 'center',
                width: 48,
                transition: 'all 0.3s ease',
                boxShadow: selected
                  ? (theme) => `0 4px 12px ${alpha(theme.palette.primary.main, 0.4)}`
                  : 'none',
              }}
            >
              {icon}
            </Box>
            <Typography variant="h6" sx={{ fontSize: '1rem', fontWeight: 600 }}>
              {title}
            </Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.8125rem' }}>
            {description}
          </Typography>
        </CardContent>
      </CardActionArea>
    </Card>
  )
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
}: SourceSelectionDialogProps) {
  const [view, setView] = useState<SourceChoiceView>(initialView)
  const [scanResult, setScanResult] = useState<DatabaseScanResponse | null>(null)
  const [scanLoading, setScanLoading] = useState(false)
  const [scanError, setScanError] = useState<ScanErrorState | null>(null)
  const [scanTarget, setScanTarget] = useState<{ type: 'local' | 'remote'; sshId: number | '' }>({
    type: 'local',
    sshId: '',
  })
  const [scanPaths, setScanPaths] = useState<string[]>(DEFAULT_DB_SCAN_PATHS)
  const [scanPathDraft, setScanPathDraft] = useState('')
  const [fallbackTemplates, setFallbackTemplates] = useState<SourceDiscoveryDatabase[]>([])
  const [snapshotCapabilities, setSnapshotCapabilities] =
    useState<FilesystemSnapshotCapabilitiesResponse | null>(null)
  const scanRequestId = useRef(0)
  const [selectedDatabase, setSelectedDatabase] = useState<SourceDiscoveryDatabase | null>(null)
  const [scriptMode, setScriptMode] = useState<ScriptMode>('create')
  const [preScriptName, setPreScriptName] = useState('')
  const [postScriptName, setPostScriptName] = useState('')
  const [preScriptContent, setPreScriptContent] = useState('')
  const [postScriptContent, setPostScriptContent] = useState('')
  const [preExistingScriptId, setPreExistingScriptId] = useState<number | ''>('')
  const [postExistingScriptId, setPostExistingScriptId] = useState<number | ''>('')
  const [applying, setApplying] = useState(false)
  const [selectedSourceKey, setSelectedSourceKey] = useState<SourceKey>('local')
  const [sourcePath, setSourcePath] = useState('')
  const [draftSourceLocations, setDraftSourceLocations] = useState<SourceLocation[]>([])
  const [snapshotDraft, setSnapshotDraft] = useState<SnapshotDraft>(() => emptySnapshotDraft())

  useEffect(() => {
    if (!open) return
    setView(initialView)
    const nextLocations = locationsFromWizardState(wizardState)
    const defaultAgentKey = selectedAgentRepositoryKey(wizardState, fullRepositories)
    setDraftSourceLocations(nextLocations)
    const nextSourceKey = nextLocations[0] ? locationKey(nextLocations[0]) : defaultAgentKey || 'local'
    setSelectedSourceKey(nextSourceKey)
    setSnapshotDraft(snapshotDraftFromLocation(nextLocations.find((location) => locationKey(location) === nextSourceKey)))
    setSourcePath('')
    setSelectedDatabase(null)
    setScriptMode('create')
    setPreExistingScriptId(wizardState.preBackupScriptId || '')
    setPostExistingScriptId(wizardState.postBackupScriptId || '')
    setScanTarget({ type: 'local', sshId: '' })
    setScanPaths(DEFAULT_DB_SCAN_PATHS)
    setScanPathDraft('')
    setScanResult(null)
    setScanError(null)
    setFallbackTemplates([])
  }, [open, wizardState, initialView, fullRepositories])

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
    setSnapshotDraft(snapshotDraftFromLocation(existing))
  }

  const updateSnapshotDraft = (updates: Partial<SnapshotDraft>) => {
    setSnapshotDraft((current) => {
      const next = { ...current, ...updates }
      if (selectedSourceKey === 'local') {
        const snapshot = snapshotFromDraft(next)
        setDraftSourceLocations((locations) =>
          locations.map((location) =>
            locationKey(location) === selectedSourceKey
              ? {
                  ...location,
                  ...(snapshot ? { snapshot } : { snapshot: undefined }),
                }
              : location
          )
        )
      }
      return next
    })
  }

  const runDatabaseScan = (immediate = false) => {
    if (!open) return
    if (scanTarget.type === 'remote' && !scanTarget.sshId) return
    if (scanPaths.length === 0) return

    const requestId = scanRequestId.current + 1
    scanRequestId.current = requestId
    const delay = immediate ? 0 : 300

    const handle = setTimeout(() => {
      setScanLoading(true)
      setScanError(null)
      sourceDiscoveryAPI
        .scanDatabases({
          source_type: scanTarget.type,
          source_ssh_connection_id: scanTarget.type === 'remote' ? Number(scanTarget.sshId) : null,
          paths: scanPaths,
        })
        .then((response) => {
          if (scanRequestId.current !== requestId) return
          setScanResult(response.data)
        })
        .catch((err) => {
          if (scanRequestId.current !== requestId) return
          setScanError(classifyScanError(err))
        })
        .finally(() => {
          if (scanRequestId.current !== requestId) return
          setScanLoading(false)
        })
    }, delay)

    return () => clearTimeout(handle)
  }

  useEffect(() => {
    const cleanup = runDatabaseScan()
    return cleanup
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, scanTarget.type, scanTarget.sshId, scanPaths.join('|')])

  const chooseDatabase = (database: SourceDiscoveryDatabase) => {
    setSelectedDatabase(database)
    setPreScriptName(database.script_drafts.pre_backup.name)
    setPostScriptName(database.script_drafts.post_backup.name)
    setPreScriptContent(database.script_drafts.pre_backup.content)
    setPostScriptContent(database.script_drafts.post_backup.content)
    setView('database-detail')
  }

  const applyDatabase = async () => {
    if (!selectedDatabase) return

    setApplying(true)
    try {
      let preBackupScriptId: number | null = null
      let postBackupScriptId: number | null = null

      if (scriptMode === 'create') {
        const preScript = await onCreateScript(
          scriptPayload(
            { ...selectedDatabase.script_drafts.pre_backup, content: preScriptContent },
            preScriptName.trim() || selectedDatabase.script_drafts.pre_backup.name
          )
        )
        const postScript = await onCreateScript(
          scriptPayload(
            { ...selectedDatabase.script_drafts.post_backup, content: postScriptContent },
            postScriptName.trim() || selectedDatabase.script_drafts.post_backup.name
          )
        )
        preBackupScriptId = preScript.id
        postBackupScriptId = postScript.id
      } else if (scriptMode === 'reuse') {
        preBackupScriptId = preExistingScriptId ? Number(preExistingScriptId) : null
        postBackupScriptId = postExistingScriptId ? Number(postExistingScriptId) : null
      }

      updateState({
        sourceType: 'local',
        sourceSshConnectionId: '',
        sourceDirectories: selectedDatabase.source_directories,
        sourceLocations: [
          {
            source_type: 'local',
            source_ssh_connection_id: null,
            paths: selectedDatabase.source_directories,
          },
        ],
        preBackupScriptId,
        postBackupScriptId,
        preBackupScriptParameters: {},
        postBackupScriptParameters: {},
      })
      onClose()
    } finally {
      setApplying(false)
    }
  }

  const addPathsToSelectedSource = (paths: string[]) => {
    const nextPaths = paths.map((path) => path.trim()).filter(Boolean)
    if (nextPaths.length === 0) return
    const locationBase = locationForKey(selectedSourceKey)
    const snapshot =
      selectedSourceKey === 'local' ? snapshotFromDraft(snapshotDraft) : undefined

    setDraftSourceLocations((current) => {
      const existingIndex = current.findIndex(
        (location) => locationKey(location) === selectedSourceKey
      )
      if (existingIndex === -1) {
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
        return {
          ...location,
          paths: Array.from(new Set([...location.paths, ...nextPaths])),
          ...(snapshot ? { snapshot } : { snapshot: undefined }),
        }
      })
    })
  }

  const addSourcePath = () => {
    addPathsToSelectedSource([sourcePath])
    setSourcePath('')
  }

  const removeSourcePath = (sourceKey: SourceKey, path: string) => {
    setDraftSourceLocations((current) =>
      current
        .map((location) =>
          locationKey(location) === sourceKey
            ? { ...location, paths: location.paths.filter((item) => item !== path) }
            : location
        )
        .filter((location) => location.paths.length > 0)
    )
  }

  const removeSourceLocation = (sourceKey: SourceKey) => {
    setDraftSourceLocations((current) =>
      current.filter((location) => locationKey(location) !== sourceKey)
    )
  }

  const applyPaths = () => {
    const sourceLocations = cleanLocations(draftSourceLocations)
    updateState({
      sourceType: sourceTypeFromLocations(sourceLocations),
      sourceSshConnectionId: sourceConnectionFromLocations(sourceLocations),
      sourceDirectories: sourceLocations.flatMap((location) => location.paths),
      sourceLocations,
    })
    onClose()
  }

  const selectedSourceConnection = !selectedSourceKey.startsWith('remote:')
    ? null
    : sshConnections.find((connection) => selectedSourceKey === `remote:${connection.id}`) || null
  const selectedAgent = selectedSourceKey.startsWith('agent:')
    ? agentMachines.find((agent) => selectedSourceKey === `agent:${agent.id}`) || null
    : null

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
    const hasRemoteOptions = sshConnections.length > 0
    const hasAgentOptions = agentMachines.length > 0
    const remoteDisabled = sourceKind === 'remote' && !hasRemoteOptions
    const agentDisabled = sourceKind === 'agent' && !hasAgentOptions
    const selectedSnapshotCapability =
      snapshotDraft.provider === 'none'
        ? null
        : snapshotCapabilities?.providers.find((provider) => provider.id === snapshotDraft.provider)
    const snapshotUnsupportedTargets = snapshotCapabilities?.unsupported_source_targets || [
      t('backupPlans.sourceChooser.snapshotLocalOnly'),
    ]

    return (
      <Stack spacing={2}>
        <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
          <Typography variant="subtitle2">{t('backupPlans.sourceChooser.where')}</Typography>
          <Button
            size="small"
            variant="text"
            endIcon={<DatabaseIcon size={14} />}
            onClick={() => setView('database')}
            sx={{ textTransform: 'none', fontWeight: 500 }}
          >
            {t('backupPlans.sourceChooser.scanDatabaseInstead')}
          </Button>
        </Stack>

        <Box
          sx={{
            display: 'flex',
            gap: 2,
            alignItems: 'stretch',
            flexDirection: { xs: 'column', sm: 'row' },
          }}
        >
          <RepoStyleSourceCard
            selected={sourceKind === 'local'}
            icon={<HardDrive size={28} />}
            title={t('backupPlans.sourceChooser.borgUiServer')}
            description={t('backupPlans.sourceChooser.localSourceDescription')}
            onClick={() => selectSourceKey('local')}
          />
          <RepoStyleSourceCard
            selected={sourceKind === 'remote'}
            disabled={!hasRemoteOptions}
            icon={<Server size={28} />}
            title={t('backupPlans.sourceChooser.remoteMachine')}
            description={
              hasRemoteOptions
                ? t('backupPlans.sourceChooser.remoteMachineDescription')
                : t('backupPlans.sourceChooser.noRemoteMachines')
            }
            onClick={() => {
              if (!hasRemoteOptions) return
              const targetId =
                selectedRemoteIdNum &&
                sshConnections.some((connection) => connection.id === selectedRemoteIdNum)
                  ? selectedRemoteIdNum
                  : sshConnections[0].id
              selectSourceKey(`remote:${targetId}`)
            }}
          />
          <RepoStyleSourceCard
            selected={sourceKind === 'agent'}
            disabled={!hasAgentOptions}
            icon={<Laptop size={28} />}
            title={t('backupPlans.sourceChooser.managedAgent')}
            description={
              hasAgentOptions
                ? t('backupPlans.sourceChooser.managedAgentDescription')
                : t('backupPlans.sourceChooser.noManagedAgents')
            }
            onClick={() => {
              if (!hasAgentOptions) return
              const targetId =
                selectedAgentIdNum && agentMachines.some((agent) => agent.id === selectedAgentIdNum)
                  ? selectedAgentIdNum
                  : agentMachines[0].id
              selectSourceKey(`agent:${targetId}`)
            }}
          />
        </Box>

        {sourceKind === 'remote' && hasRemoteOptions ? (
          <FormControl fullWidth sx={{ height: 56 }}>
            <InputLabel id="source-remote-machine-label">
              {t('backupPlans.sourceChooser.selectRemoteMachine')}
            </InputLabel>
            <Select
              labelId="source-remote-machine-label"
              value={selectedRemoteIdNum || ''}
              label={t('backupPlans.sourceChooser.selectRemoteMachine')}
              onChange={(event) => selectSourceKey(`remote:${Number(event.target.value)}`)}
              sx={{
                height: 56,
                '& .MuiSelect-select': { display: 'flex', alignItems: 'center' },
              }}
            >
              {sshConnections.map((connection) => (
                <MenuItem key={connection.id} value={connection.id}>
                  <Stack
                    direction="row"
                    spacing={1}
                    alignItems="center"
                    sx={{ minWidth: 0, width: '100%' }}
                  >
                    <Server
                      size={14}
                      style={{ flexShrink: 0, color: 'currentColor', opacity: 0.7 }}
                    />
                    <Typography variant="body2" noWrap>
                      {`${connection.username}@${connection.host}:${connection.port}`}
                    </Typography>
                    {connection.default_path && (
                      <Typography variant="caption" color="text.secondary" noWrap>
                        {connection.default_path}
                      </Typography>
                    )}
                    {connection.status === 'connected' && (
                      <Box
                        sx={{
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          bgcolor: 'success.main',
                          flexShrink: 0,
                          ml: 'auto',
                        }}
                      />
                    )}
                  </Stack>
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        ) : sourceKind === 'agent' && hasAgentOptions ? (
          <FormControl fullWidth sx={{ height: 56 }}>
            <InputLabel id="source-agent-machine-label">
              {t('backupPlans.sourceChooser.selectManagedAgent')}
            </InputLabel>
            <Select
              labelId="source-agent-machine-label"
              value={selectedAgentIdNum || ''}
              label={t('backupPlans.sourceChooser.selectManagedAgent')}
              onChange={(event) => selectSourceKey(`agent:${Number(event.target.value)}`)}
              sx={{
                height: 56,
                '& .MuiSelect-select': { display: 'flex', alignItems: 'center' },
              }}
            >
              {agentMachines.map((agent) => (
                <MenuItem key={agent.id} value={agent.id}>
                  <Stack
                    direction="row"
                    spacing={1}
                    alignItems="center"
                    sx={{ minWidth: 0, width: '100%' }}
                  >
                    <Laptop size={14} style={{ flexShrink: 0, opacity: 0.7 }} />
                    <Typography variant="body2" noWrap>
                      {agentDisplayName(agent)}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" noWrap>
                      {agent.status}
                    </Typography>
                    {agent.status === 'online' && (
                      <Box
                        sx={{
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          bgcolor: 'success.main',
                          flexShrink: 0,
                          ml: 'auto',
                        }}
                      />
                    )}
                  </Stack>
                </MenuItem>
              ))}
            </Select>
          </FormControl>
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
                ? t('backupPlans.sourceChooser.noManagedAgents')
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

        <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1, bgcolor: 'background.paper' }}>
          <Stack spacing={1.25}>
            {sourceKind === 'local' ? (
              <>
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
                      <Stack direction="row" spacing={0.75} alignItems="center" useFlexGap flexWrap="wrap">
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
                    />
                    <TextField
                      label={t('backupPlans.sourceChooser.snapshotZfsMountpoint')}
                      value={snapshotDraft.mountpoint}
                      onChange={(event) => updateSnapshotDraft({ mountpoint: event.target.value })}
                      size="small"
                      fullWidth
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
              </>
            ) : (
              <Alert severity="info">
                <Stack spacing={0.5}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {t('backupPlans.sourceChooser.snapshotLocalOnly')}
                  </Typography>
                  {snapshotUnsupportedTargets.map((target) => (
                    <Typography key={target} variant="caption">
                      {target}
                    </Typography>
                  ))}
                </Stack>
              </Alert>
            )}
          </Stack>
        </Paper>

        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            {t('backupPlans.sourceChooser.selectedSourceGroups')}
          </Typography>
          {draftSourceLocations.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              {t('backupPlans.sourceChooser.summaryEmpty')}
            </Typography>
          ) : (
            <Stack spacing={1}>
              {draftSourceLocations.map((location) => {
                const key = locationKey(location)
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
    const detections = scanResult?.detections || []
    const scanTemplates = scanResult?.templates || []
    const detectedIds = new Set(detections.map((item) => item.id))
    const effectiveTemplates = scanTemplates.length > 0 ? scanTemplates : fallbackTemplates
    const remainingTemplates = effectiveTemplates.filter((item) => !detectedIds.has(item.id))
    const hasRemoteOptions = sshConnections.length > 0
    const remoteDisabled = scanTarget.type === 'remote' && !hasRemoteOptions
    const scanCompleted = scanResult !== null
    const nothingFound = !scanLoading && !scanError && scanCompleted && detections.length === 0
    const awaitingFirstScan = !scanCompleted && !scanError
    const showSkeleton = scanLoading || awaitingFirstScan
    const targetLabel =
      scanResult?.scan_target.label ??
      (scanTarget.type === 'local'
        ? t('backupPlans.sourceChooser.borgUiServer')
        : t('backupPlans.sourceChooser.remoteMachine'))

    const addPath = () => {
      const next = scanPathDraft.trim()
      if (!next || scanPaths.includes(next)) {
        setScanPathDraft('')
        return
      }
      setScanPaths((current) => [...current, next])
      setScanPathDraft('')
    }

    const removePath = (path: string) => {
      setScanPaths((current) => current.filter((item) => item !== path))
    }

    return (
      <Stack spacing={2}>
        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            {t('backupPlans.sourceChooser.scanTarget')}
          </Typography>
          <Box
            sx={{
              display: 'flex',
              gap: 2,
              alignItems: 'stretch',
              flexDirection: { xs: 'column', sm: 'row' },
            }}
          >
            <RepoStyleSourceCard
              selected={scanTarget.type === 'local'}
              icon={<HardDrive size={28} />}
              title={t('backupPlans.sourceChooser.borgUiServer')}
              description={t('backupPlans.sourceChooser.localSourceDescription')}
              onClick={() => setScanTarget({ type: 'local', sshId: '' })}
            />
            <RepoStyleSourceCard
              selected={scanTarget.type === 'remote'}
              disabled={!hasRemoteOptions}
              icon={<Server size={28} />}
              title={t('backupPlans.sourceChooser.remoteMachine')}
              description={
                hasRemoteOptions
                  ? t('backupPlans.sourceChooser.remoteMachineDescription')
                  : t('backupPlans.sourceChooser.noRemoteMachines')
              }
              onClick={() => {
                if (!hasRemoteOptions) return
                const fallbackId =
                  scanTarget.sshId &&
                  sshConnections.some((connection) => connection.id === scanTarget.sshId)
                    ? scanTarget.sshId
                    : sshConnections[0].id
                setScanTarget({ type: 'remote', sshId: fallbackId })
              }}
            />
          </Box>
          <Box sx={{ mt: 2.5 }}>
            {scanTarget.type === 'remote' && hasRemoteOptions ? (
              <FormControl fullWidth sx={{ height: 56 }}>
                <InputLabel id="scan-remote-target-label">
                  {t('backupPlans.sourceChooser.selectRemoteMachine')}
                </InputLabel>
                <Select
                  labelId="scan-remote-target-label"
                  value={scanTarget.sshId || ''}
                  label={t('backupPlans.sourceChooser.selectRemoteMachine')}
                  onChange={(event) =>
                    setScanTarget({ type: 'remote', sshId: Number(event.target.value) })
                  }
                  sx={{
                    height: 56,
                    '& .MuiSelect-select': { display: 'flex', alignItems: 'center' },
                  }}
                >
                  {sshConnections.map((connection) => (
                    <MenuItem key={connection.id} value={connection.id}>
                      <Stack direction="row" spacing={1} alignItems="center" sx={{ width: '100%' }}>
                        <Server size={14} style={{ flexShrink: 0, opacity: 0.7 }} />
                        <Typography variant="body2" noWrap>
                          {`${connection.username}@${connection.host}:${connection.port}`}
                        </Typography>
                      </Stack>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
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
                  {remoteDisabled
                    ? t('backupPlans.sourceChooser.noRemoteMachines')
                    : t('backupPlans.sourceChooser.readingFromLocal')}
                </Typography>
              </Box>
            )}
          </Box>
        </Box>

        <Box>
          <Stack
            direction="row"
            spacing={1}
            alignItems="center"
            justifyContent="space-between"
            sx={{ mb: 1 }}
          >
            <Typography variant="subtitle2">
              {t('backupPlans.sourceChooser.pathsToScan')}
            </Typography>
            <Button
              size="small"
              variant="text"
              startIcon={
                scanLoading ? (
                  <CircularProgress size={12} color="inherit" />
                ) : (
                  <RefreshCw size={14} />
                )
              }
              onClick={() => runDatabaseScan(true)}
              disabled={scanLoading || remoteDisabled || scanPaths.length === 0}
              sx={{ textTransform: 'none', fontWeight: 500 }}
            >
              {scanLoading
                ? t('backupPlans.sourceChooser.scanning')
                : t('backupPlans.sourceChooser.rescan')}
            </Button>
          </Stack>
          <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" sx={{ mb: 1 }}>
            {scanPaths.map((path) => (
              <Chip
                key={path}
                size="small"
                label={path}
                onDelete={() => removePath(path)}
                deleteIcon={<X size={14} />}
                sx={{
                  fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace',
                  fontSize: '0.75rem',
                }}
              />
            ))}
            {scanPaths.length === 0 && (
              <Typography variant="caption" color="text.secondary">
                {t('backupPlans.sourceChooser.noScanPaths')}
              </Typography>
            )}
          </Stack>
          <Stack direction="row" spacing={1} alignItems="stretch">
            <TextField
              size="small"
              placeholder="/path/to/scan"
              value={scanPathDraft}
              onChange={(event) => setScanPathDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  addPath()
                }
              }}
              fullWidth
              sx={{
                '& .MuiInputBase-input': {
                  fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace',
                  fontSize: '0.8125rem',
                },
              }}
            />
            <Button
              variant="outlined"
              startIcon={<Plus size={14} />}
              onClick={addPath}
              disabled={!scanPathDraft.trim()}
              sx={{ flexShrink: 0 }}
            >
              {t('backupPlans.sourceChooser.addPath')}
            </Button>
          </Stack>
        </Box>

        {showSkeleton && (
          <>
            <Skeleton
              variant="rounded"
              height={88}
              sx={{ borderRadius: 1 }}
              animation={scanLoading ? 'wave' : 'pulse'}
            />
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
              {Array.from({ length: 4 }).map((_, index) => (
                <Skeleton
                  key={index}
                  variant="rounded"
                  height={64}
                  sx={{ borderRadius: 1 }}
                  animation={scanLoading ? 'wave' : 'pulse'}
                />
              ))}
            </Box>
          </>
        )}

        {!showSkeleton && scanResult && scanResult.warnings.length > 0 && (
          <Alert severity="warning">
            <Stack spacing={0.25}>
              {scanResult.warnings.map((warning, index) => (
                <Typography key={`${warning.code}-${index}`} variant="caption">
                  {warning.path ? `${warning.path}: ` : ''}
                  {warning.message}
                </Typography>
              ))}
            </Stack>
          </Alert>
        )}

        {!showSkeleton && scanError?.kind === 'ENDPOINT_MISSING' && (
          <Alert severity="info">{t('backupPlans.sourceChooser.scanEndpointMissing')}</Alert>
        )}

        {!showSkeleton && scanError?.kind === 'OTHER' && (
          <Alert
            severity="warning"
            action={
              <Button
                color="inherit"
                size="small"
                onClick={() => runDatabaseScan(true)}
                disabled={scanLoading}
              >
                {t('backupPlans.sourceChooser.rescan')}
              </Button>
            }
          >
            <Stack spacing={0.25}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {t('backupPlans.sourceChooser.scanFailedTitle', { target: targetLabel })}
              </Typography>
              <Typography variant="caption">
                {scanError.detail ?? t('backupPlans.sourceChooser.scanFailedBody')}
              </Typography>
            </Stack>
          </Alert>
        )}

        {!showSkeleton && nothingFound && (
          <Alert severity="info">
            <Stack spacing={0.5}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {t('backupPlans.sourceChooser.nothingFoundTitle', { target: targetLabel })}
              </Typography>
              {scanResult && scanResult.scanned_paths.length > 0 && (
                <Stack
                  direction="row"
                  spacing={0.5}
                  useFlexGap
                  flexWrap="wrap"
                  alignItems="baseline"
                >
                  <Typography variant="caption" sx={{ flexShrink: 0 }}>
                    {t('backupPlans.sourceChooser.checkedPaths')}
                  </Typography>
                  {scanResult.scanned_paths.map((path, index) => (
                    <Typography
                      key={path}
                      component="span"
                      variant="caption"
                      sx={{
                        fontFamily:
                          'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
                      }}
                    >
                      {path}
                      {index < scanResult.scanned_paths.length - 1 ? ',' : ''}
                    </Typography>
                  ))}
                </Stack>
              )}
              <Typography variant="caption">
                {t('backupPlans.sourceChooser.nothingFoundBody')}
              </Typography>
            </Stack>
          </Alert>
        )}

        {!showSkeleton && detections.length > 0 && (
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              {t('backupPlans.sourceChooser.detectedSection')}
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
              {detections.map((database) => (
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

        {!showSkeleton && remainingTemplates.length > 0 && (
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              {detections.length > 0
                ? t('backupPlans.sourceChooser.orPickTemplate')
                : t('backupPlans.sourceChooser.pickTemplateManually')}
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
              {remainingTemplates.map((database) => (
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

    return (
      <Stack spacing={2}>
        <Box>
          <Typography variant="subtitle1" fontWeight={600}>
            {selectedDatabase.display_name}
          </Typography>
          <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" sx={{ mt: 0.75 }}>
            <Chip size="small" label={selectedDatabase.engine} />
            <Chip size="small" label={selectedDatabase.backup_strategy.replace(/_/g, ' ')} />
            <Tooltip title={selectedDatabase.notes.join(' ')}>
              <Chip
                size="small"
                icon={<Info size={14} />}
                label={t('backupPlans.sourceChooser.notesLabel')}
                variant="outlined"
              />
            </Tooltip>
          </Stack>
        </Box>
        <Box>
          <Typography variant="caption" color="text.secondary">
            {t('backupPlans.sourceChooser.sourcePaths')}
          </Typography>
          <Typography variant="body2" sx={{ fontFamily: 'monospace', mt: 0.25 }}>
            {selectedDatabase.source_directories.join(', ')}
          </Typography>
        </Box>
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

  const content = (() => {
    if (view === 'database') return renderDatabaseList()
    if (view === 'database-detail') return renderDatabaseDetail()
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
          <Button onClick={onClose}>{t('common.buttons.cancel')}</Button>
          {view === 'paths' && (
            <Button
              variant="contained"
              onClick={applyPaths}
              disabled={cleanLocations(draftSourceLocations).length === 0}
            >
              {t('backupPlans.sourceChooser.applyPaths')}
            </Button>
          )}
          {view === 'database-detail' && (
            <Button variant="contained" onClick={applyDatabase} disabled={applying}>
              {t('backupPlans.sourceChooser.applyDatabase')}
            </Button>
          )}
        </DialogActions>
      }
    >
      <DialogTitle sx={{ pb: 1 }}>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
          {view !== 'paths' && (
            <IconButton
              aria-label={t('backupPlans.sourceChooser.back')}
              onClick={() => setView(view === 'database-detail' ? 'database' : 'paths')}
              size="small"
              edge="start"
              sx={{ mr: 0.5 }}
            >
              <ArrowLeft size={18} />
            </IconButton>
          )}
          <Typography component="span" variant="h6" sx={{ fontWeight: 600 }} noWrap>
            {view === 'database' && t('backupPlans.sourceChooser.databaseBackupTitle')}
            {view === 'database-detail' &&
              (selectedDatabase?.display_name || t('backupPlans.sourceChooser.databaseTitle'))}
            {view === 'paths' && t('backupPlans.sourceChooser.title')}
          </Typography>
        </Stack>
      </DialogTitle>
      <DialogContent sx={{ pt: 1, flex: 1, overflowY: 'auto' }}>
        <Stack spacing={2}>{content}</Stack>
      </DialogContent>
    </ResponsiveDialog>
  )
}

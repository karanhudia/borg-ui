import React, { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { DialogActions, Box, Button, CircularProgress } from '@mui/material'
import { Cloud, FolderOpen, Database, Shield, Settings, CheckCircle } from 'lucide-react'
import WizardDialog from './shared/WizardDialog'
import {
  RcloneRemoteDialog,
  RcloneRemoteFolderPickerDialog,
  WizardStepCloudMirror,
  WizardStepLocation,
  WizardStepDataSource,
  WizardStepSecurity,
  WizardStepRepositoryAdvanced,
  WizardStepBackupConfig,
  WizardStepReview,
} from './wizard'
import FileExplorerDialog from './FileExplorerDialog'
import { managedAgentsAPI, rcloneAPI, sshKeysAPI, RepositoryData } from '../services/api'
import { formatDirectRcloneUrl, parseDirectRcloneUrl } from './wizard/directRclonePath'
import type {
  AgentMachineResponse,
  CreateRcloneRemoteRequest,
  RcloneProvider,
  RcloneRemote,
  RcloneStatus,
} from '../services/api'
import { useAnalytics } from '../hooks/useAnalytics'
import { useFeatureAnalytics } from '../hooks/useFeatureAnalytics'
import { getApiErrorDetail } from '../utils/apiErrors'
import { translateBackendKey } from '../utils/translateBackendKey'
import { kibToUploadRatelimitMb, uploadRatelimitMbToKib } from '../utils/uploadRatelimit'
import type { SourceLocation } from '../types'

interface Repository extends RepositoryData {
  id: number
  passphrase?: string
  source_ssh_connection_id?: number | null
  source_directories?: string[]
  exclude_patterns?: string[]
  custom_flags?: string | null
  remote_path?: string
  pre_backup_script?: string
  post_backup_script?: string
  pre_hook_timeout?: number
  post_hook_timeout?: number
  continue_on_hook_failure?: boolean
  skip_on_hook_failure?: boolean
  bypass_lock?: boolean
}

interface RepositoryWizardProps {
  open: boolean
  onClose: () => void
  mode: 'create' | 'edit' | 'import'
  repository?: Repository
  onSubmit: (data: RepositoryData, keyfile?: File | null) => void | Promise<void>
  canUseManagedAgents?: boolean
  canUseRclone?: boolean
}

interface SSHConnection {
  id: number
  host: string
  username: string
  port: number
  ssh_key_id: number
  default_path?: string
  mount_point?: string
  status: string
}

interface WizardState {
  // Location step
  name: string
  borgVersion: 1 | 2
  repositoryMode: 'full' | 'observe'
  repositoryLocation: 'local' | 'ssh' | 'rclone'
  executionTarget: 'local' | 'agent'
  agentMachineId: number | ''
  path: string
  repoSshConnectionId: number | ''
  bypassLock: boolean
  cloudMirrorEnabled: boolean
  rcloneRemoteId: number | ''
  rcloneRemotePath: string
  rcloneRemotePathVerified: boolean
  rcloneSyncPolicy: 'after_success' | 'manual' | 'scheduled'
  rcloneSyncCronExpression: string
  rcloneSyncTimezone: string
  rcloneExtraFlags: string
  // Data source step
  dataSource: 'local' | 'remote'
  sourceSshConnectionId: number | ''
  sourceDirs: string[]
  sourceLocations: SourceLocation[]
  // Security step
  encryption: string
  passphrase: string
  remotePath: string
  selectedKeyfile: File | null
  // Backup config step
  compression: string
  excludePatterns: string[]
  customFlags: string
  preBackupScript: string
  postBackupScript: string
  preHookTimeout: number
  postHookTimeout: number
  hookFailureMode: 'fail' | 'continue' | 'skip'
  uploadRatelimitMb: string
}

const createInitialState = (): WizardState => ({
  name: '',
  borgVersion: 1,
  repositoryMode: 'full',
  repositoryLocation: 'local',
  executionTarget: 'local',
  agentMachineId: '',
  path: '',
  repoSshConnectionId: '',
  bypassLock: false,
  cloudMirrorEnabled: false,
  rcloneRemoteId: '',
  rcloneRemotePath: '',
  rcloneRemotePathVerified: false,
  rcloneSyncPolicy: 'after_success',
  rcloneSyncCronExpression: '0 */6 * * *',
  rcloneSyncTimezone: 'UTC',
  rcloneExtraFlags: '',
  dataSource: 'local',
  sourceSshConnectionId: '',
  sourceDirs: [],
  sourceLocations: [],
  encryption: 'repokey',
  passphrase: '',
  remotePath: '',
  selectedKeyfile: null,
  compression: 'lz4',
  excludePatterns: [],
  customFlags: '',
  preBackupScript: '',
  postBackupScript: '',
  preHookTimeout: 300,
  postHookTimeout: 300,
  hookFailureMode: 'fail',
  uploadRatelimitMb: '',
})

function repositorySourceLocations(repository?: Repository): SourceLocation[] {
  if (repository?.source_locations?.length) return repository.source_locations
  if (!repository?.source_directories?.length) return []
  return legacySourceLocations({
    dataSource: repository.source_ssh_connection_id ? 'remote' : 'local',
    sourceSshConnectionId: repository.source_ssh_connection_id || '',
    sourceDirs: repository.source_directories,
  })
}

function legacySourceLocations(source: {
  dataSource: 'local' | 'remote'
  sourceSshConnectionId: number | ''
  sourceDirs: string[]
}): SourceLocation[] {
  if (!source.sourceDirs.length) return []
  if (source.dataSource === 'remote' && source.sourceSshConnectionId) {
    return [
      {
        source_type: 'remote',
        source_ssh_connection_id: Number(source.sourceSshConnectionId),
        paths: source.sourceDirs,
      },
    ]
  }
  return [
    {
      source_type: 'local',
      source_ssh_connection_id: null,
      paths: source.sourceDirs,
    },
  ]
}

function isDirectRcloneRepositoryRecord(repository?: Repository): boolean {
  if (!repository) return false
  const repoVersion = repository.borg_version === 2 ? 2 : 1
  return Boolean(
    repository.storage_backend === 'rclone_direct' ||
    (repository.repository_type === 'rclone' &&
      !repository.rclone_storage &&
      repoVersion === 2 &&
      (repository.path || '').startsWith('rclone:'))
  )
}

function isCachedRcloneRepositoryRecord(repository?: Repository): boolean {
  if (!repository || isDirectRcloneRepositoryRecord(repository)) return false
  return Boolean(
    repository.rclone_storage &&
    (repository.storage_backend === 'rclone' || repository.repository_type === 'rclone')
  )
}

const RepositoryWizard = ({
  open,
  onClose,
  mode,
  repository,
  onSubmit,
  canUseManagedAgents = true,
  canUseRclone = true,
}: RepositoryWizardProps) => {
  const { track, trackRepository, EventCategory, EventAction } = useAnalytics()
  const { trackFeatureUsed, trackFeatureBlocked } = useFeatureAnalytics()
  const { t } = useTranslation()
  const [activeStep, setActiveStep] = useState(0)
  const [wizardState, setWizardState] = useState<WizardState>(() => createInitialState())
  const [sshConnections, setSshConnections] = useState<SSHConnection[]>([])
  const [agentMachines, setAgentMachines] = useState<AgentMachineResponse[]>([])
  const [agentRepoAdvertised, setAgentRepoAdvertised] = useState<boolean | null>(null)
  const [rcloneStatus, setRcloneStatus] = useState<RcloneStatus | null>(null)
  const [rcloneRemotes, setRcloneRemotes] = useState<RcloneRemote[]>([])
  const [rcloneProviders, setRcloneProviders] = useState<RcloneProvider[]>([])
  const [showRcloneRemoteDialog, setShowRcloneRemoteDialog] = useState(false)
  const [isCreatingRcloneRemote, setIsCreatingRcloneRemote] = useState(false)
  const [rcloneRemoteCreateError, setRcloneRemoteCreateError] = useState<string | null>(null)

  // File explorer states
  const [showPathExplorer, setShowPathExplorer] = useState(false)
  const [showSourceExplorer, setShowSourceExplorer] = useState(false)
  const [showRemoteSourceExplorer, setShowRemoteSourceExplorer] = useState(false)
  const [showExcludeExplorer, setShowExcludeExplorer] = useState(false)
  const [showRcloneRemoteExplorer, setShowRcloneRemoteExplorer] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const showLegacyBackupSteps =
    mode === 'edit' &&
    wizardState.repositoryMode === 'full' &&
    Boolean(
      repository?.source_directories?.length ||
      repository?.exclude_patterns?.length ||
      repository?.source_ssh_connection_id ||
      repository?.custom_flags ||
      repository?.pre_backup_script ||
      repository?.post_backup_script
    )
  const showSourceStep = showLegacyBackupSteps
  const isCloudMirrorEligible = (state: WizardState) =>
    state.executionTarget === 'agent' ||
    (state.executionTarget === 'local' &&
      (state.repositoryLocation === 'local' || state.repositoryLocation === 'ssh'))
  const isCachedRcloneRepositoryEdit = mode === 'edit' && isCachedRcloneRepositoryRecord(repository)
  const cloudMirrorPrimaryLocation: 'local' | 'ssh' | 'agent' =
    wizardState.executionTarget === 'agent'
      ? 'agent'
      : wizardState.repositoryLocation === 'ssh'
        ? 'ssh'
        : 'local'
  const isDirectRclone = wizardState.repositoryLocation === 'rclone'
  const directRclonePathParts = isDirectRclone ? parseDirectRcloneUrl(wizardState.path) : null
  const selectedDirectRcloneRemote =
    isDirectRclone && wizardState.rcloneRemoteId
      ? rcloneRemotes.find((remote) => remote.id === Number(wizardState.rcloneRemoteId))
      : directRclonePathParts
        ? rcloneRemotes.find((remote) => remote.name === directRclonePathParts.remoteName)
        : null
  const directRcloneRemotePath =
    isDirectRclone && wizardState.rcloneRemotePath
      ? wizardState.rcloneRemotePath
      : directRclonePathParts?.remotePath || ''

  // Step definitions
  const steps = useMemo(() => {
    const baseSteps = [
      {
        key: 'location',
        label: t('repositoryWizard.steps.location'),
        icon: <FolderOpen size={14} />,
      },
    ]

    if (!isDirectRclone) {
      baseSteps.push({
        key: 'cloudMirror',
        label: t('repositoryWizard.steps.cloudMirror'),
        icon: <Cloud size={14} />,
      })
    }

    if (showSourceStep) {
      baseSteps.push({
        key: 'source',
        label: t('repositoryWizard.steps.source'),
        icon: <Database size={14} />,
      })
    }

    baseSteps.push({
      key: 'security',
      label: t('repositoryWizard.steps.security'),
      icon: <Shield size={14} />,
    })

    baseSteps.push({
      key: 'advanced',
      label: t('repositoryWizard.steps.advanced'),
      icon: <Settings size={14} />,
    })

    if (showLegacyBackupSteps) {
      baseSteps.push({
        key: 'config',
        label: t('repositoryWizard.steps.config'),
        icon: <Database size={14} />,
      })
    }

    baseSteps.push({
      key: 'review',
      label: t('repositoryWizard.steps.review'),
      icon: <CheckCircle size={14} />,
    })

    return baseSteps
  }, [isDirectRclone, showLegacyBackupSteps, showSourceStep, t])

  useEffect(() => {
    setActiveStep((prev) => Math.min(prev, steps.length - 1))
  }, [steps.length])

  // Load selectable remote execution targets.
  const loadWizardData = React.useCallback(async () => {
    const [connectionsRes, agentsRes, statusRes, remotesRes, providersRes] =
      await Promise.allSettled([
        sshKeysAPI.getSSHConnections(),
        canUseManagedAgents ? managedAgentsAPI.listAgents() : Promise.resolve({ data: [] }),
        canUseRclone
          ? rcloneAPI.getStatus()
          : Promise.resolve({
              data: { available: false, error: t('wizard.location.rcloneRequiresPro') },
            }),
        canUseRclone ? rcloneAPI.listRemotes() : Promise.resolve({ data: { remotes: [] } }),
        canUseRclone ? rcloneAPI.getProviders() : Promise.resolve({ data: { providers: [] } }),
      ])

    if (connectionsRes.status === 'fulfilled') {
      const connections = connectionsRes.value.data?.connections || []
      setSshConnections(Array.isArray(connections) ? connections : [])
    } else {
      console.error('Failed to load SSH data:', connectionsRes.reason)
      setSshConnections([])
    }

    if (agentsRes.status === 'fulfilled') {
      setAgentMachines(Array.isArray(agentsRes.value.data) ? agentsRes.value.data : [])
    } else {
      console.error('Failed to load managed agents:', agentsRes.reason)
      setAgentMachines([])
    }

    if (statusRes.status === 'fulfilled') {
      setRcloneStatus(statusRes.value.data)
    } else {
      console.error('Failed to load rclone status:', statusRes.reason)
      setRcloneStatus({ available: false, error: 'Unable to load rclone status' })
    }

    if (remotesRes.status === 'fulfilled') {
      setRcloneRemotes(
        Array.isArray(remotesRes.value.data?.remotes) ? remotesRes.value.data.remotes : []
      )
    } else {
      console.error('Failed to load rclone remotes:', remotesRes.reason)
      setRcloneRemotes([])
    }

    if (providersRes.status === 'fulfilled') {
      setRcloneProviders(
        Array.isArray(providersRes.value.data?.providers) ? providersRes.value.data.providers : []
      )
    } else {
      console.error('Failed to load rclone providers:', providersRes.reason)
      setRcloneProviders([])
    }
  }, [canUseManagedAgents, canUseRclone, t])

  // Populate form data for edit mode
  const populateEditData = React.useCallback(() => {
    if (!repository) return

    let repoPath = repository.path || ''

    // Extract plain path from SSH URL if needed
    if (repoPath.startsWith('ssh://')) {
      const sshUrlMatch = repoPath.match(/^ssh:\/\/[^@]+@[^:/]+(?::\d+)?(.*)$/)
      if (sshUrlMatch) {
        repoPath = sshUrlMatch[1]
      }
    }

    // Determine repository location
    // If connection_id field exists (even if null), trust it as source of truth
    // Otherwise fall back to legacy detection for old repos not yet edited
    const isSSH =
      repository.connection_id !== undefined
        ? !!repository.connection_id // Trust connection_id if it exists
        : repository.repository_type === 'ssh' || (repository.path || '').startsWith('ssh://') // Legacy fallback

    const repoVersion = (repository.borg_version === 2 ? 2 : 1) as 1 | 2
    const isDirectRcloneRepository = isDirectRcloneRepositoryRecord(repository)
    const hasCloudMirror = !isDirectRcloneRepository && Boolean(repository.rclone_storage)
    const executionTarget =
      repository.executor_type === 'agent' || repository.execution_target === 'agent'
        ? 'agent'
        : 'local'

    setWizardState({
      name: repository.name || '',
      borgVersion: repoVersion,
      repositoryMode: repository.mode || 'full',
      repositoryLocation: isDirectRcloneRepository
        ? 'rclone'
        : executionTarget === 'agent'
          ? 'local'
          : isSSH
            ? 'ssh'
            : 'local',
      executionTarget,
      agentMachineId: executionTarget === 'agent' ? repository.agent_machine_id || '' : '',
      path: repoPath,
      repoSshConnectionId: executionTarget === 'agent' ? '' : repository.connection_id || '',
      bypassLock: repository.bypass_lock || false,
      cloudMirrorEnabled: hasCloudMirror,
      rcloneRemoteId: Number(repository.rclone_storage?.rclone_remote_id || '') || '',
      rcloneRemotePath: String(repository.rclone_storage?.rclone_remote_path || ''),
      rcloneRemotePathVerified: hasCloudMirror,
      rcloneSyncPolicy:
        (repository.rclone_storage?.sync_policy as 'after_success' | 'manual' | 'scheduled') ||
        'after_success',
      rcloneSyncCronExpression: String(
        repository.rclone_storage?.sync_cron_expression || '0 */6 * * *'
      ),
      rcloneSyncTimezone: String(repository.rclone_storage?.sync_timezone || 'UTC'),
      rcloneExtraFlags: Array.isArray(repository.rclone_storage?.extra_flags)
        ? repository.rclone_storage.extra_flags.join(' ')
        : '',
      dataSource:
        executionTarget === 'agent' || !repository.source_ssh_connection_id ? 'local' : 'remote',
      sourceSshConnectionId:
        executionTarget === 'agent' ? '' : repository.source_ssh_connection_id || '',
      sourceDirs: repository.source_directories || [],
      sourceLocations: repositorySourceLocations(repository),
      encryption: repository.encryption || (repoVersion === 2 ? 'repokey-aes-ocb' : 'repokey'),
      passphrase: repository.passphrase || '',
      remotePath: repository.remote_path || '',
      selectedKeyfile: null,
      compression: repository.compression || 'lz4',
      excludePatterns: repository.exclude_patterns || [],
      customFlags: repository.custom_flags || '',
      preBackupScript: repository.pre_backup_script || '',
      postBackupScript: repository.post_backup_script || '',
      preHookTimeout: repository.pre_hook_timeout || 300,
      postHookTimeout: repository.post_hook_timeout || 300,
      hookFailureMode: repository.skip_on_hook_failure
        ? 'skip'
        : repository.continue_on_hook_failure
          ? 'continue'
          : 'fail',
      uploadRatelimitMb: kibToUploadRatelimitMb(repository.upload_ratelimit_kib),
    })
  }, [repository])

  // Reset form
  const resetForm = () => {
    setActiveStep(0)
    setWizardState(createInitialState())
  }

  // Handle state changes
  const handleStateChange = (updates: Partial<WizardState>) => {
    setWizardState((prev) => {
      const nextUpdates = { ...updates }

      if (nextUpdates.repositoryLocation === 'rclone' && !canUseRclone) return prev
      if (nextUpdates.executionTarget === 'agent' && !canUseManagedAgents) return prev
      if (nextUpdates.cloudMirrorEnabled && !canUseRclone) {
        nextUpdates.cloudMirrorEnabled = false
      }

      // When borg version changes, reset encryption to a sensible default for that version
      if (nextUpdates.borgVersion !== undefined && nextUpdates.borgVersion !== prev.borgVersion) {
        nextUpdates.encryption = nextUpdates.borgVersion === 2 ? 'repokey-aes-ocb' : 'repokey'
        if (nextUpdates.borgVersion !== 2 && prev.repositoryLocation === 'rclone') {
          nextUpdates.repositoryLocation = 'local'
        }
      }

      if (nextUpdates.repositoryLocation === 'rclone') {
        nextUpdates.borgVersion = 2
        nextUpdates.executionTarget = 'local'
        nextUpdates.agentMachineId = ''
        nextUpdates.repoSshConnectionId = ''
        nextUpdates.cloudMirrorEnabled = false
        nextUpdates.rcloneRemoteId = ''
        nextUpdates.rcloneRemotePath = ''
        nextUpdates.rcloneRemotePathVerified = false
      }

      const effectiveExecutionTarget = nextUpdates.executionTarget ?? prev.executionTarget

      if (effectiveExecutionTarget === 'agent') {
        nextUpdates.dataSource = 'local'
        nextUpdates.sourceSshConnectionId = ''
        nextUpdates.repositoryLocation = 'local'
        nextUpdates.repoSshConnectionId = ''
      } else if (nextUpdates.executionTarget === 'local') {
        nextUpdates.agentMachineId = ''
      }

      if (effectiveExecutionTarget === 'agent' && nextUpdates.dataSource === 'remote') {
        nextUpdates.dataSource = 'local'
        nextUpdates.sourceSshConnectionId = ''
      }

      const next = { ...prev, ...nextUpdates }
      if (!isCloudMirrorEligible(next)) {
        next.cloudMirrorEnabled = false
        next.rcloneRemoteId = ''
        next.rcloneRemotePath = ''
        next.rcloneRemotePathVerified = false
      }
      const sourceFieldsChanged =
        nextUpdates.sourceDirs !== undefined ||
        nextUpdates.sourceSshConnectionId !== undefined ||
        nextUpdates.dataSource !== undefined
      if (sourceFieldsChanged && nextUpdates.sourceLocations === undefined) {
        next.sourceLocations = legacySourceLocations(next)
      }
      return next
    })
  }

  // Handle SSH connection selection for repository
  const handleRepoSshConnectionSelect = (connectionId: number) => {
    const connection = sshConnections.find((c) => c.id === connectionId)
    if (connection) {
      handleStateChange({
        repoSshConnectionId: connectionId,
        path: connection.default_path || wizardState.path,
      })
    }
  }

  // Handle path change with SSH URL detection
  const handlePathChange = (newPath: string) => {
    if (wizardState.repositoryLocation === 'rclone') {
      handleStateChange({ path: newPath })
      return
    }

    if (wizardState.executionTarget === 'agent') {
      handleStateChange({ path: newPath })
      return
    }

    if (newPath.startsWith('ssh://')) {
      const matchWithPort = newPath.match(/^ssh:\/\/([^@]+)@([^:/]+):(\d+)(\/.*)$/)
      const matchWithoutPort = newPath.match(/^ssh:\/\/([^@]+)@([^/]+)(\/.*)$/)

      if (matchWithPort) {
        const [, parsedUsername, parsedHost, parsedPort, remotePath] = matchWithPort
        const matchingConnection = sshConnections.find(
          (c) =>
            c.username === parsedUsername &&
            c.host === parsedHost &&
            c.port === parseInt(parsedPort)
        )

        handleStateChange({
          repositoryLocation: 'ssh',
          path: remotePath || '/',
          repoSshConnectionId: matchingConnection?.id || '',
        })
        return
      } else if (matchWithoutPort) {
        const [, parsedUsername, parsedHost, remotePath] = matchWithoutPort
        const matchingConnection = sshConnections.find(
          (c) => c.username === parsedUsername && c.host === parsedHost && c.port === 22
        )

        handleStateChange({
          repositoryLocation: 'ssh',
          path: remotePath || '/',
          repoSshConnectionId: matchingConnection?.id || '',
        })
        return
      }
    }

    handleStateChange({ path: newPath })
  }

  const normalizeSourceDirs = (
    paths: string[]
  ): { processedPaths: string[]; detectedSshConnectionId: number | '' } => {
    const processedPaths: string[] = []
    let detectedSshConnection: SSHConnection | null = null

    for (const p of paths) {
      if (p.startsWith('ssh://')) {
        const matchWithPort = p.match(/^ssh:\/\/([^@]+)@([^:/]+):(\d+)(\/.*)$/)
        const matchWithoutPort = p.match(/^ssh:\/\/([^@]+)@([^/]+)(\/.*)$/)

        if (matchWithPort) {
          const [, parsedUsername, parsedHost, parsedPort, remotePath] = matchWithPort
          if (!detectedSshConnection) {
            detectedSshConnection =
              sshConnections.find(
                (c) =>
                  c.username === parsedUsername &&
                  c.host === parsedHost &&
                  c.port === parseInt(parsedPort)
              ) || null
          }
          processedPaths.push(remotePath || '/')
        } else if (matchWithoutPort) {
          const [, parsedUsername, parsedHost, remotePath] = matchWithoutPort
          if (!detectedSshConnection) {
            detectedSshConnection =
              sshConnections.find(
                (c) => c.username === parsedUsername && c.host === parsedHost && c.port === 22
              ) || null
          }
          processedPaths.push(remotePath || '/')
        } else {
          processedPaths.push(p)
        }
      } else {
        processedPaths.push(p)
      }
    }

    return {
      processedPaths,
      detectedSshConnectionId: detectedSshConnection?.id ?? '',
    }
  }

  // Handle source directories change with SSH URL detection
  const handleSourceDirsChange = (paths: string[]) => {
    const { processedPaths, detectedSshConnectionId } = normalizeSourceDirs(paths)

    if (detectedSshConnectionId) {
      handleStateChange({
        dataSource: 'remote',
        sourceSshConnectionId: detectedSshConnectionId,
        sourceDirs: [...wizardState.sourceDirs, ...processedPaths],
      })
      return
    }

    handleStateChange({
      sourceDirs: [...wizardState.sourceDirs, ...processedPaths],
    })
  }

  // Initialize on dialog open
  useEffect(() => {
    if (open) {
      setActiveStep(0)
    }
  }, [open, mode, repository?.id])

  useEffect(() => {
    if (open) {
      loadWizardData()
      if (mode === 'edit' && repository) {
        populateEditData()
      } else {
        resetForm()
      }
    }
  }, [open, mode, repository, populateEditData, loadWizardData])

  // Auto-fill the repository target from the selected agent's own $BORG_REPO
  useEffect(() => {
    if (mode === 'edit' || wizardState.executionTarget !== 'agent' || !wizardState.agentMachineId) {
      setAgentRepoAdvertised(null)
      return
    }
    let cancelled = false
    setAgentRepoAdvertised(null)
    managedAgentsAPI
      .getRepositoryDefaults(Number(wizardState.agentMachineId))
      .then((res) => {
        if (cancelled) return
        // Only fill fields the user hasn't already started editing while the
        // request was in flight (evaluated at apply-time in the functional update).
        setWizardState((prev) => {
          const updates: Partial<WizardState> = {}
          if (res.data.repo && !(prev.path || '').trim()) updates.path = res.data.repo
          if (res.data.remote_path && !(prev.remotePath || '').trim()) {
            updates.remotePath = res.data.remote_path
          }
          return Object.keys(updates).length ? { ...prev, ...updates } : prev
        })
        setAgentRepoAdvertised(Boolean(res.data.repo))
      })
      .catch(() => {
        if (!cancelled) setAgentRepoAdvertised(false)
      })
    return () => {
      cancelled = true
    }
  }, [mode, wizardState.executionTarget, wizardState.agentMachineId])

  // Auto-select SSH connection for edit mode
  useEffect(() => {
    if (mode === 'edit' && repository && sshConnections.length > 0) {
      if (!wizardState.repoSshConnectionId && wizardState.repositoryLocation === 'ssh') {
        let repoHost = repository.host || ''
        let repoUsername = repository.username || ''
        let repoPort = repository.port || 22

        if (repository.path && repository.path.startsWith('ssh://')) {
          const sshUrlMatch = repository.path.match(/^ssh:\/\/([^@]+)@([^:/]+):?(\d+)?(.*)$/)
          if (sshUrlMatch) {
            repoUsername = sshUrlMatch[1]
            repoHost = sshUrlMatch[2]
            repoPort = sshUrlMatch[3] ? parseInt(sshUrlMatch[3]) : 22
          }
        }

        const matchingConnection = sshConnections.find(
          (conn) =>
            conn.host === repoHost && conn.username === repoUsername && conn.port === repoPort
        )

        if (matchingConnection) {
          setWizardState((prev) => ({
            ...prev,
            repoSshConnectionId: matchingConnection.id,
          }))
        }
      }
    }
  }, [
    mode,
    repository,
    sshConnections,
    wizardState.repoSshConnectionId,
    wizardState.repositoryLocation,
  ])

  // Validation
  const canProceed = () => {
    const currentStepKey = steps[activeStep]?.key

    switch (currentStepKey) {
      case 'location':
        if (!wizardState.name.trim()) return false
        if (!wizardState.path.trim()) return false
        if (wizardState.repositoryLocation === 'rclone' && !canUseRclone) return false
        if (wizardState.executionTarget === 'agent' && !canUseManagedAgents) return false
        if (
          wizardState.repositoryLocation === 'rclone' &&
          (wizardState.borgVersion !== 2 || !wizardState.path.trim().startsWith('rclone:'))
        )
          return false
        if (wizardState.executionTarget === 'agent' && !wizardState.agentMachineId) return false
        if (wizardState.repositoryLocation === 'ssh' && !wizardState.repoSshConnectionId)
          return false
        return true

      case 'cloudMirror':
        if (!wizardState.cloudMirrorEnabled) return true
        if (!canUseRclone) return false
        if (!isCloudMirrorEligible(wizardState)) return false
        if (rcloneStatus?.available !== true) return false
        if (!wizardState.rcloneRemoteId || !wizardState.rcloneRemotePath.trim()) return false
        if (wizardState.rcloneSyncPolicy === 'scheduled') {
          if (!wizardState.rcloneSyncCronExpression.trim()) return false
          if (!wizardState.rcloneSyncTimezone.trim()) return false
        }
        return true

      case 'source':
        if (wizardState.executionTarget === 'agent' && wizardState.dataSource === 'remote')
          return false
        if (
          wizardState.executionTarget !== 'agent' &&
          wizardState.dataSource === 'remote' &&
          !wizardState.sourceSshConnectionId
        )
          return false
        return true

      case 'security':
        if (mode === 'edit') return true
        if (mode === 'import') return true
        if (
          wizardState.encryption !== 'none' &&
          !wizardState.passphrase.trim() &&
          wizardState.executionTarget !== 'agent'
        )
          return false
        return true

      case 'config':
      case 'review':
        return true

      default:
        return true
    }
  }

  const handleNext = () => {
    setActiveStep((prev) => prev + 1)
  }

  const handleBack = () => {
    setActiveStep((prev) => prev - 1)
  }

  const handleSubmit = async () => {
    if (wizardState.repositoryLocation === 'rclone' && !canUseRclone) {
      trackFeatureBlocked('rclone', {
        surface: 'repository_wizard',
        operation: 'submit_direct_rclone_repository',
        mode,
      })
      return
    }
    if (wizardState.cloudMirrorEnabled && !canUseRclone) {
      trackFeatureBlocked('rclone', {
        surface: 'repository_wizard',
        operation: 'submit_cloud_mirror_repository',
        mode,
      })
      return
    }
    if (wizardState.executionTarget === 'agent' && !canUseManagedAgents) {
      trackFeatureBlocked('managed_agents', {
        surface: 'repository_wizard',
        operation: 'submit_agent_repository',
        mode,
      })
      return
    }

    const storageBackend = isCachedRcloneRepositoryEdit
      ? 'rclone'
      : wizardState.repositoryLocation === 'rclone'
        ? 'rclone_direct'
        : wizardState.executionTarget === 'agent'
          ? 'agent_local'
          : wizardState.repositoryLocation === 'ssh'
            ? 'ssh'
            : 'local'
    const directRcloneEnabled = wizardState.repositoryLocation === 'rclone'
    const cloudMirrorEnabled =
      !directRcloneEnabled && wizardState.cloudMirrorEnabled && isCloudMirrorEligible(wizardState)
    const rcloneFieldsEnabled = isCachedRcloneRepositoryEdit || cloudMirrorEnabled

    const data: RepositoryData = {
      name: wizardState.name,
      borg_version: wizardState.borgVersion,
      mode: wizardState.repositoryMode,
      path: wizardState.path,
      encryption: wizardState.encryption,
      passphrase: wizardState.passphrase,
      compression: wizardState.compression,
      source_directories: wizardState.sourceDirs,
      source_locations: wizardState.sourceLocations,
      exclude_patterns: wizardState.excludePatterns,
      custom_flags: wizardState.customFlags,
      remote_path: wizardState.remotePath,
      pre_backup_script: wizardState.preBackupScript,
      post_backup_script: wizardState.postBackupScript,
      pre_hook_timeout: wizardState.preHookTimeout,
      post_hook_timeout: wizardState.postHookTimeout,
      continue_on_hook_failure: wizardState.hookFailureMode === 'continue',
      skip_on_hook_failure: wizardState.hookFailureMode === 'skip',
      upload_ratelimit_kib: uploadRatelimitMbToKib(wizardState.uploadRatelimitMb),
      bypass_lock: wizardState.bypassLock,
      executor_type: wizardState.executionTarget === 'agent' ? 'agent' : 'server',
      execution_target: directRcloneEnabled
        ? 'local'
        : wizardState.executionTarget === 'agent'
          ? 'agent'
          : wizardState.repositoryLocation === 'ssh'
            ? 'ssh'
            : 'local',
      agent_machine_id:
        !directRcloneEnabled &&
        !isCachedRcloneRepositoryEdit &&
        wizardState.executionTarget === 'agent' &&
        wizardState.agentMachineId
          ? wizardState.agentMachineId
          : null,
      storage_backend: storageBackend,
      cloud_mirror_enabled: isCachedRcloneRepositoryEdit ? true : cloudMirrorEnabled,
      rclone_remote_id:
        rcloneFieldsEnabled && wizardState.rcloneRemoteId ? wizardState.rcloneRemoteId : null,
      rclone_remote_path: rcloneFieldsEnabled ? wizardState.rcloneRemotePath : null,
      rclone_remote_path_verified: cloudMirrorEnabled
        ? wizardState.rcloneRemotePathVerified
        : false,
      rclone_sync_policy: rcloneFieldsEnabled ? wizardState.rcloneSyncPolicy : 'after_success',
      rclone_sync_cron_expression:
        rcloneFieldsEnabled && wizardState.rcloneSyncPolicy === 'scheduled'
          ? wizardState.rcloneSyncCronExpression
          : null,
      rclone_sync_timezone:
        rcloneFieldsEnabled && wizardState.rcloneSyncPolicy === 'scheduled'
          ? wizardState.rcloneSyncTimezone
          : null,
      rclone_extra_flags: cloudMirrorEnabled
        ? wizardState.rcloneExtraFlags.split(/\s+/).filter(Boolean)
        : isCachedRcloneRepositoryEdit
          ? wizardState.rcloneExtraFlags.split(/\s+/).filter(Boolean)
          : [],
      // Connection IDs - single source of truth for SSH
      connection_id:
        directRcloneEnabled ||
        isCachedRcloneRepositoryEdit ||
        wizardState.executionTarget === 'agent'
          ? null
          : wizardState.repoSshConnectionId || null,
      source_connection_id:
        !directRcloneEnabled &&
        wizardState.executionTarget !== 'agent' &&
        wizardState.dataSource === 'remote' &&
        wizardState.sourceSshConnectionId
          ? wizardState.sourceSshConnectionId
          : null,
    }

    if (mode === 'edit' && !rcloneFieldsEnabled) {
      const shouldSubmitCloudMirrorDisable = Boolean(
        repository?.rclone_storage && !isDirectRcloneRepositoryRecord(repository)
      )
      if (!shouldSubmitCloudMirrorDisable) {
        delete data.cloud_mirror_enabled
      }
      delete data.rclone_remote_id
      delete data.rclone_remote_path
      delete data.rclone_remote_path_verified
      delete data.rclone_sync_policy
      delete data.rclone_sync_cron_expression
      delete data.rclone_sync_timezone
      delete data.rclone_extra_flags
    }

    if (isCachedRcloneRepositoryEdit) {
      delete data.connection_id
      delete data.execution_target
      delete data.executor_type
      delete data.agent_machine_id
    }

    track(
      EventCategory.REPOSITORY,
      mode === 'create'
        ? EventAction.CREATE
        : mode === 'import'
          ? EventAction.UPLOAD
          : EventAction.EDIT,
      { source: 'wizard', mode }
    )
    trackRepository(
      mode === 'create'
        ? EventAction.CREATE
        : mode === 'import'
          ? EventAction.UPLOAD
          : EventAction.EDIT,
      { name: wizardState.name }
    )

    const submitOperation =
      mode === 'create'
        ? 'create_repository'
        : mode === 'import'
          ? 'import_repository'
          : 'update_repository'
    const featureContext = {
      surface: 'repository_wizard',
      operation: submitOperation,
      mode,
      storage_backend: data.storage_backend,
      repository_mode: data.mode,
    }

    // Pass keyfile for import mode
    setIsSubmitting(true)
    try {
      await onSubmit(data, mode === 'import' ? wizardState.selectedKeyfile : null)
      if (wizardState.borgVersion === 2) {
        trackFeatureUsed('borg_v2', featureContext)
      }

      if (data.agent_machine_id) {
        trackFeatureUsed('managed_agents', featureContext)
      }

      if (
        data.storage_backend === 'rclone' ||
        data.storage_backend === 'rclone_direct' ||
        data.cloud_mirror_enabled
      ) {
        trackFeatureUsed('rclone', {
          ...featureContext,
          sync_policy: data.rclone_sync_policy,
        })
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleCreateRcloneRemote = async (data: CreateRcloneRemoteRequest) => {
    if (!canUseRclone) {
      trackFeatureBlocked('rclone', {
        surface: 'repository_wizard',
        operation: 'create_rclone_remote',
        mode,
      })
      return
    }
    setIsCreatingRcloneRemote(true)
    setRcloneRemoteCreateError(null)
    try {
      const response = await rcloneAPI.createRemote(data)
      const remote = response.data
      setRcloneRemotes((prev) =>
        [...prev.filter((item) => item.id !== remote.id), remote].sort((a, b) =>
          a.name.localeCompare(b.name)
        )
      )
      handleStateChange({
        cloudMirrorEnabled: true,
        rcloneRemoteId: remote.id,
        rcloneRemotePathVerified: false,
      })
      trackFeatureUsed('rclone', {
        surface: 'repository_wizard',
        operation: 'create_rclone_remote',
        mode,
        provider: data.provider,
        config_source: data.config_source,
      })
      setShowRcloneRemoteDialog(false)
    } catch (error) {
      setRcloneRemoteCreateError(
        translateBackendKey(getApiErrorDetail(error)) || t('wizard.location.rcloneCreateFailed')
      )
    } finally {
      setIsCreatingRcloneRemote(false)
    }
  }

  // Render current step content
  const renderStepContent = () => {
    const currentStepKey = steps[activeStep]?.key

    switch (currentStepKey) {
      case 'location':
        return (
          <>
            {wizardState.executionTarget === 'agent' &&
              wizardState.agentMachineId &&
              agentRepoAdvertised === false && (
                <div className="mb-4 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
                  {t('repositoryWizard.agentRepoUnknownWarning')}
                </div>
              )}
            <WizardStepLocation
              mode={mode}
              data={{
                name: wizardState.name,
                borgVersion: wizardState.borgVersion,
                repositoryMode: wizardState.repositoryMode,
                repositoryLocation: wizardState.repositoryLocation,
                executionTarget: wizardState.executionTarget,
                agentMachineId: wizardState.agentMachineId,
                path: wizardState.path,
                repoSshConnectionId: wizardState.repoSshConnectionId,
                rcloneRemoteId: wizardState.rcloneRemoteId || selectedDirectRcloneRemote?.id || '',
                rcloneRemotePath: directRcloneRemotePath,
                bypassLock: wizardState.bypassLock,
              }}
              sshConnections={sshConnections}
              agentMachines={agentMachines}
              rcloneStatus={rcloneStatus}
              rcloneRemotes={rcloneRemotes}
              canUseManagedAgents={canUseManagedAgents}
              canUseRclone={canUseRclone}
              dataSource={wizardState.dataSource}
              sourceSshConnectionId={wizardState.sourceSshConnectionId}
              onChange={(updates) => {
                if (typeof updates.path === 'string' && updates.repositoryLocation === undefined) {
                  if (wizardState.repositoryLocation === 'rclone') {
                    handleStateChange(updates)
                    return
                  }
                  handlePathChange(updates.path)
                  return
                }

                // Handle SSH connection selection
                if (
                  updates.repoSshConnectionId &&
                  updates.repoSshConnectionId !== wizardState.repoSshConnectionId
                ) {
                  handleRepoSshConnectionSelect(updates.repoSshConnectionId as number)
                } else {
                  handleStateChange(updates)
                }
              }}
              onBrowsePath={() => setShowPathExplorer(true)}
              onBrowseDirectRclonePath={() => setShowRcloneRemoteExplorer(true)}
            />
          </>
        )

      case 'cloudMirror':
        return (
          <WizardStepCloudMirror
            data={{
              cloudMirrorEnabled: wizardState.cloudMirrorEnabled,
              rcloneRemoteId: wizardState.rcloneRemoteId,
              rcloneRemotePath: wizardState.rcloneRemotePath,
              rcloneRemotePathVerified: wizardState.rcloneRemotePathVerified,
              rcloneSyncPolicy: wizardState.rcloneSyncPolicy,
              rcloneSyncCronExpression: wizardState.rcloneSyncCronExpression,
              rcloneSyncTimezone: wizardState.rcloneSyncTimezone,
              rcloneExtraFlags: wizardState.rcloneExtraFlags,
            }}
            rcloneStatus={rcloneStatus}
            rcloneRemotes={rcloneRemotes}
            eligible={isCloudMirrorEligible(wizardState)}
            primaryLocation={cloudMirrorPrimaryLocation}
            storageMode={isCachedRcloneRepositoryEdit ? 'cachedRepository' : 'mirror'}
            canUseRclone={canUseRclone}
            onChange={handleStateChange}
            onAddRcloneRemote={() => {
              setRcloneRemoteCreateError(null)
              setShowRcloneRemoteDialog(true)
            }}
            onBrowseRemotePath={() => setShowRcloneRemoteExplorer(true)}
          />
        )

      case 'source':
        return (
          <WizardStepDataSource
            repositoryLocation={wizardState.repositoryLocation}
            executionTarget={wizardState.executionTarget}
            repoSshConnectionId={wizardState.repoSshConnectionId}
            repositoryMode={wizardState.repositoryMode}
            data={{
              dataSource: wizardState.dataSource,
              sourceSshConnectionId: wizardState.sourceSshConnectionId,
              sourceDirs: wizardState.sourceDirs,
            }}
            sshConnections={sshConnections}
            onChange={(updates) => {
              if (updates.sourceDirs) {
                const { processedPaths, detectedSshConnectionId } = normalizeSourceDirs(
                  updates.sourceDirs
                )
                handleStateChange({
                  ...updates,
                  dataSource: detectedSshConnectionId
                    ? 'remote'
                    : (updates.dataSource ?? wizardState.dataSource),
                  sourceSshConnectionId:
                    detectedSshConnectionId || updates.sourceSshConnectionId || '',
                  sourceDirs: processedPaths,
                })
                return
              }

              handleStateChange(updates)
            }}
            onBrowseSource={() => setShowSourceExplorer(true)}
            onBrowseRemoteSource={() => setShowRemoteSourceExplorer(true)}
            sourceRequired={false}
          />
        )

      case 'security':
        return (
          <WizardStepSecurity
            mode={mode}
            borgVersion={wizardState.borgVersion}
            data={{
              encryption: wizardState.encryption,
              passphrase: wizardState.passphrase,
              remotePath: wizardState.remotePath,
              selectedKeyfile: wizardState.selectedKeyfile,
            }}
            onChange={handleStateChange}
            showRemotePath={wizardState.executionTarget === 'agent'}
          />
        )

      case 'advanced':
        return (
          <WizardStepRepositoryAdvanced
            repositoryId={mode === 'edit' ? repository?.id : null}
            repositoryMode={wizardState.repositoryMode}
            data={{
              compression: wizardState.compression,
              remotePath: wizardState.remotePath,
              preBackupScript: wizardState.preBackupScript,
              postBackupScript: wizardState.postBackupScript,
              preHookTimeout: wizardState.preHookTimeout,
              postHookTimeout: wizardState.postHookTimeout,
              hookFailureMode: wizardState.hookFailureMode,
              customFlags: wizardState.customFlags,
              uploadRatelimitMb: wizardState.uploadRatelimitMb,
            }}
            onChange={handleStateChange}
          />
        )

      case 'config':
        return (
          <WizardStepBackupConfig
            repositoryId={mode === 'edit' ? repository?.id : null}
            dataSource={wizardState.dataSource}
            repositoryMode={wizardState.repositoryMode}
            data={{
              compression: wizardState.compression,
              excludePatterns: wizardState.excludePatterns,
              customFlags: wizardState.customFlags,
              remotePath: wizardState.remotePath,
              preBackupScript: wizardState.preBackupScript,
              postBackupScript: wizardState.postBackupScript,
              preHookTimeout: wizardState.preHookTimeout,
              postHookTimeout: wizardState.postHookTimeout,
              hookFailureMode: wizardState.hookFailureMode,
              uploadRatelimitMb: wizardState.uploadRatelimitMb,
            }}
            onChange={handleStateChange}
            onBrowseExclude={
              wizardState.executionTarget === 'agent'
                ? undefined
                : () => setShowExcludeExplorer(true)
            }
            showAdvancedOptions={false}
          />
        )

      case 'review': {
        const selectedRcloneRemote =
          wizardState.rcloneRemoteId === ''
            ? null
            : rcloneRemotes.find((remote) => remote.id === wizardState.rcloneRemoteId)
        return (
          <WizardStepReview
            mode={mode}
            data={{
              name: wizardState.name,
              borgVersion: wizardState.borgVersion,
              repositoryMode: wizardState.repositoryMode,
              repositoryLocation: wizardState.repositoryLocation,
              executionTarget: wizardState.executionTarget,
              agentMachineId: wizardState.agentMachineId,
              path: wizardState.path,
              repoSshConnectionId: wizardState.repoSshConnectionId,
              dataSource: wizardState.dataSource,
              sourceSshConnectionId: wizardState.sourceSshConnectionId,
              sourceDirs: wizardState.sourceDirs,
              encryption: wizardState.encryption,
              passphrase: wizardState.passphrase,
              compression: wizardState.compression,
              excludePatterns: wizardState.excludePatterns,
              customFlags: wizardState.customFlags,
              remotePath: wizardState.remotePath,
              cloudMirrorEnabled: wizardState.cloudMirrorEnabled,
              rcloneRemoteName: selectedRcloneRemote?.name,
              rcloneRemotePath: wizardState.rcloneRemotePath,
              rcloneSyncPolicy: wizardState.rcloneSyncPolicy,
              rcloneSyncCronExpression: wizardState.rcloneSyncCronExpression,
              rcloneSyncTimezone: wizardState.rcloneSyncTimezone,
            }}
            sshConnections={sshConnections}
            agentMachines={agentMachines}
          />
        )
      }

      default:
        return null
    }
  }

  const selectedAgentMachine =
    wizardState.executionTarget === 'agent' && wizardState.agentMachineId
      ? agentMachines.find((agent) => agent.id === Number(wizardState.agentMachineId))
      : null

  return (
    <>
      <WizardDialog
        open={open}
        onClose={onClose}
        title={
          mode === 'create'
            ? t('repositoryWizard.titleCreate')
            : mode === 'edit'
              ? t('repositoryWizard.titleEdit')
              : t('repositoryWizard.titleImport')
        }
        steps={steps}
        currentStep={activeStep}
        onStepClick={setActiveStep}
        footer={
          <DialogActions sx={{ px: { xs: 1, sm: 3 }, pb: { xs: 1, sm: 2 } }}>
            <Button onClick={onClose} disabled={isSubmitting}>
              {t('common.buttons.cancel')}
            </Button>
            <Box sx={{ flex: 1 }} />
            <Button disabled={activeStep === 0 || isSubmitting} onClick={handleBack}>
              {t('common.buttons.back')}
            </Button>
            {activeStep < steps.length - 1 ? (
              <Button
                variant="contained"
                onClick={handleNext}
                disabled={!canProceed()}
                sx={{ boxShadow: '0 2px 8px rgba(37,99,235,0.3)' }}
              >
                {t('common.buttons.next')}
              </Button>
            ) : (
              <Button
                variant="contained"
                onClick={handleSubmit}
                disabled={!canProceed() || isSubmitting}
                startIcon={
                  isSubmitting ? <CircularProgress size={16} color="inherit" /> : undefined
                }
                sx={{ boxShadow: isSubmitting ? 'none' : '0 2px 8px rgba(37,99,235,0.3)' }}
              >
                {isSubmitting
                  ? t(
                      `repositoryWizard.finalButton${mode === 'create' ? 'Creating' : mode === 'edit' ? 'Saving' : 'Importing'}`
                    )
                  : mode === 'create'
                    ? t('repositoryWizard.finalButtonCreate')
                    : mode === 'edit'
                      ? t('repositoryWizard.finalButtonEdit')
                      : t('repositoryWizard.finalButtonImport')}
              </Button>
            )}
          </DialogActions>
        }
      >
        {renderStepContent()}
      </WizardDialog>

      <RcloneRemoteDialog
        open={showRcloneRemoteDialog}
        isCreating={isCreatingRcloneRemote}
        error={rcloneRemoteCreateError}
        providers={rcloneProviders}
        onClose={() => {
          if (!isCreatingRcloneRemote) {
            setShowRcloneRemoteDialog(false)
          }
        }}
        onCreate={handleCreateRcloneRemote}
      />

      <RcloneRemoteFolderPickerDialog
        open={showRcloneRemoteExplorer}
        remoteId={
          isDirectRclone
            ? selectedDirectRcloneRemote?.id || null
            : wizardState.rcloneRemoteId === ''
              ? null
              : Number(wizardState.rcloneRemoteId)
        }
        initialPath={isDirectRclone ? directRcloneRemotePath : wizardState.rcloneRemotePath}
        onClose={() => setShowRcloneRemoteExplorer(false)}
        onSelect={(path) => {
          if (isDirectRclone && selectedDirectRcloneRemote) {
            handleStateChange({
              rcloneRemoteId: selectedDirectRcloneRemote.id,
              rcloneRemotePath: path,
              path: formatDirectRcloneUrl(selectedDirectRcloneRemote.name, path),
            })
          } else {
            handleStateChange({
              rcloneRemotePath: path,
              rcloneRemotePathVerified: true,
            })
          }
          setShowRcloneRemoteExplorer(false)
        }}
      />

      {/* File Explorer Dialogs */}
      <FileExplorerDialog
        key={`path-explorer-${wizardState.executionTarget}-${wizardState.repositoryLocation}-${wizardState.repoSshConnectionId}-${wizardState.agentMachineId}`}
        open={showPathExplorer}
        onClose={() => setShowPathExplorer(false)}
        onSelect={(paths) => {
          if (paths.length > 0) {
            handlePathChange(paths[0])
          }
          setShowPathExplorer(false)
        }}
        title={t('repositoryWizard.fileExplorer.selectRepoPath')}
        initialPath={
          wizardState.path ||
          (wizardState.repositoryLocation === 'ssh' && wizardState.repoSshConnectionId
            ? sshConnections.find((c) => c.id === wizardState.repoSshConnectionId)?.default_path ||
              '/'
            : '/')
        }
        multiSelect={false}
        connectionType={
          wizardState.executionTarget === 'agent'
            ? 'agent'
            : wizardState.repositoryLocation === 'local'
              ? 'local'
              : 'ssh'
        }
        agentId={
          wizardState.executionTarget === 'agent' && wizardState.agentMachineId
            ? Number(wizardState.agentMachineId)
            : undefined
        }
        agentName={selectedAgentMachine?.name}
        agentDefaultPath={selectedAgentMachine?.default_path}
        sshConfig={
          wizardState.executionTarget !== 'agent' &&
          wizardState.repositoryLocation === 'ssh' &&
          wizardState.repoSshConnectionId
            ? (() => {
                const conn = sshConnections.find((c) => c.id === wizardState.repoSshConnectionId)
                return conn
                  ? {
                      ssh_key_id: conn.ssh_key_id,
                      host: conn.host,
                      username: conn.username,
                      port: conn.port,
                    }
                  : undefined
              })()
            : undefined
        }
        selectMode="directories"
      />

      <FileExplorerDialog
        open={showSourceExplorer}
        onClose={() => setShowSourceExplorer(false)}
        onSelect={(paths) => {
          handleSourceDirsChange(paths)
          setShowSourceExplorer(false)
        }}
        title={
          wizardState.sourceSshConnectionId && wizardState.dataSource === 'local'
            ? t('repositoryWizard.fileExplorer.selectSourceDirsRemote')
            : t('repositoryWizard.fileExplorer.selectSourceDirs')
        }
        initialPath="/"
        multiSelect={true}
        connectionType="local"
        selectMode="both"
        showSshMountPoints={
          wizardState.repositoryLocation !== 'ssh' &&
          (!!wizardState.sourceSshConnectionId || wizardState.sourceDirs.length === 0)
        }
        allowedSshConnectionId={
          wizardState.dataSource === 'local' ? wizardState.sourceSshConnectionId || null : null
        }
      />

      {showRemoteSourceExplorer &&
        wizardState.sourceSshConnectionId &&
        (() => {
          const conn = sshConnections.find((c) => c.id === wizardState.sourceSshConnectionId)
          const config = conn
            ? {
                ssh_key_id: conn.ssh_key_id,
                host: conn.host,
                username: conn.username,
                port: conn.port,
              }
            : undefined

          return (
            <FileExplorerDialog
              open={true}
              onClose={() => setShowRemoteSourceExplorer(false)}
              onSelect={(paths) => {
                handleStateChange({
                  sourceDirs: [...wizardState.sourceDirs, ...paths],
                })
                setShowRemoteSourceExplorer(false)
              }}
              title={t('repositoryWizard.fileExplorer.selectSourceDirsOrFilesRemote')}
              initialPath="/"
              multiSelect={true}
              connectionType="ssh"
              sshConfig={config}
              selectMode="both"
            />
          )
        })()}

      {showExcludeExplorer &&
        (() => {
          // For remote source, build SSH config
          const isRemote = wizardState.dataSource === 'remote'
          const conn = isRemote
            ? sshConnections.find((c) => c.id === wizardState.sourceSshConnectionId)
            : null
          const sshConfig =
            isRemote && conn
              ? {
                  ssh_key_id: conn.ssh_key_id,
                  host: conn.host,
                  username: conn.username,
                  port: conn.port,
                }
              : undefined

          return (
            <FileExplorerDialog
              open={true}
              onClose={() => setShowExcludeExplorer(false)}
              onSelect={(paths) => {
                handleStateChange({
                  excludePatterns: [...wizardState.excludePatterns, ...paths],
                })
              }}
              title={t('repositoryWizard.fileExplorer.selectExclude')}
              initialPath="/"
              multiSelect={true}
              connectionType={isRemote ? 'ssh' : 'local'}
              sshConfig={sshConfig}
              selectMode="both"
              showSshMountPoints={false}
            />
          )
        })()}
    </>
  )
}

export default RepositoryWizard

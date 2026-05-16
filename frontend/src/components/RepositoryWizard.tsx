import React, { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { DialogActions, Box, Button, CircularProgress } from '@mui/material'
import { FolderOpen, Database, Shield, Settings, CheckCircle } from 'lucide-react'
import {
  WizardDialog,
  WizardStepLocation,
  WizardStepDataSource,
  WizardStepSecurity,
  WizardStepRepositoryAdvanced,
  WizardStepBackupConfig,
  WizardStepReview,
} from './wizard'
import FileExplorerDialog from './FileExplorerDialog'
import { sshKeysAPI, RepositoryData } from '../services/api'
import { useAnalytics } from '../hooks/useAnalytics'

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
  repositoryLocation: 'local' | 'ssh'
  path: string
  repoSshConnectionId: number | ''
  bypassLock: boolean
  // Data source step
  dataSource: 'local' | 'remote'
  sourceSshConnectionId: number | ''
  sourceDirs: string[]
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
}

const createInitialState = (): WizardState => ({
  name: '',
  borgVersion: 1,
  repositoryMode: 'full',
  repositoryLocation: 'local',
  path: '',
  repoSshConnectionId: '',
  bypassLock: false,
  dataSource: 'local',
  sourceSshConnectionId: '',
  sourceDirs: [],
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
})

const RepositoryWizard = ({ open, onClose, mode, repository, onSubmit }: RepositoryWizardProps) => {
  const { track, trackRepository, EventCategory, EventAction } = useAnalytics()
  const { t } = useTranslation()
  const [activeStep, setActiveStep] = useState(0)
  const [wizardState, setWizardState] = useState<WizardState>(() => createInitialState())
  const [sshConnections, setSshConnections] = useState<SSHConnection[]>([])

  // File explorer states
  const [showPathExplorer, setShowPathExplorer] = useState(false)
  const [showSourceExplorer, setShowSourceExplorer] = useState(false)
  const [showRemoteSourceExplorer, setShowRemoteSourceExplorer] = useState(false)
  const [showExcludeExplorer, setShowExcludeExplorer] = useState(false)
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

  // Step definitions
  const steps = useMemo(() => {
    const baseSteps = [
      {
        key: 'location',
        label: t('repositoryWizard.steps.location'),
        icon: <FolderOpen size={14} />,
      },
    ]

    if (showLegacyBackupSteps) {
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
  }, [showLegacyBackupSteps, t])

  // Load SSH connections
  const loadSshData = async () => {
    try {
      const connectionsRes = await sshKeysAPI.getSSHConnections()
      const connections = connectionsRes.data?.connections || []
      setSshConnections(Array.isArray(connections) ? connections : [])
    } catch (error) {
      console.error('Failed to load SSH data:', error)
      setSshConnections([])
    }
  }

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
    setWizardState({
      name: repository.name || '',
      borgVersion: repoVersion,
      repositoryMode: repository.mode || 'full',
      repositoryLocation: isSSH ? 'ssh' : 'local',
      path: repoPath,
      repoSshConnectionId: repository.connection_id || '',
      bypassLock: repository.bypass_lock || false,
      dataSource: repository.source_ssh_connection_id ? 'remote' : 'local',
      sourceSshConnectionId: repository.source_ssh_connection_id || '',
      sourceDirs: repository.source_directories || [],
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
      // When borg version changes, reset encryption to a sensible default for that version
      if (updates.borgVersion !== undefined && updates.borgVersion !== prev.borgVersion) {
        updates.encryption = updates.borgVersion === 2 ? 'repokey-aes-ocb' : 'repokey'
      }
      return { ...prev, ...updates }
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
      loadSshData()
      if (mode === 'edit' && repository) {
        populateEditData()
      } else {
        resetForm()
      }
    }
  }, [open, mode, repository, populateEditData])

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
          handleStateChange({ repoSshConnectionId: matchingConnection.id })
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
        if (!wizardState.name.trim() || !wizardState.path.trim()) return false
        if (wizardState.repositoryLocation === 'ssh' && !wizardState.repoSshConnectionId)
          return false
        return true

      case 'source':
        if (wizardState.dataSource === 'remote' && !wizardState.sourceSshConnectionId) return false
        return true

      case 'security':
        if (mode === 'edit') return true
        if (mode === 'import') return true
        if (wizardState.encryption !== 'none' && !wizardState.passphrase.trim()) return false
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
    const data: RepositoryData = {
      name: wizardState.name,
      borg_version: wizardState.borgVersion,
      mode: wizardState.repositoryMode,
      path: wizardState.path,
      encryption: wizardState.encryption,
      passphrase: wizardState.passphrase,
      compression: wizardState.compression,
      source_directories: wizardState.sourceDirs,
      exclude_patterns: wizardState.excludePatterns,
      custom_flags: wizardState.customFlags,
      remote_path: wizardState.remotePath,
      pre_backup_script: wizardState.preBackupScript,
      post_backup_script: wizardState.postBackupScript,
      pre_hook_timeout: wizardState.preHookTimeout,
      post_hook_timeout: wizardState.postHookTimeout,
      continue_on_hook_failure: wizardState.hookFailureMode === 'continue',
      skip_on_hook_failure: wizardState.hookFailureMode === 'skip',
      bypass_lock: wizardState.bypassLock,
      // Connection IDs - single source of truth for SSH
      connection_id: wizardState.repoSshConnectionId || null,
      source_connection_id:
        wizardState.dataSource === 'remote' && wizardState.sourceSshConnectionId
          ? wizardState.sourceSshConnectionId
          : null,
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

    // Pass keyfile for import mode
    setIsSubmitting(true)
    try {
      await onSubmit(data, mode === 'import' ? wizardState.selectedKeyfile : null)
    } finally {
      setIsSubmitting(false)
    }
  }

  // Render current step content
  const renderStepContent = () => {
    const currentStepKey = steps[activeStep]?.key

    switch (currentStepKey) {
      case 'location':
        return (
          <WizardStepLocation
            mode={mode}
            data={{
              name: wizardState.name,
              borgVersion: wizardState.borgVersion,
              repositoryMode: wizardState.repositoryMode,
              repositoryLocation: wizardState.repositoryLocation,
              path: wizardState.path,
              repoSshConnectionId: wizardState.repoSshConnectionId,
              bypassLock: wizardState.bypassLock,
            }}
            sshConnections={sshConnections}
            dataSource={wizardState.dataSource}
            sourceSshConnectionId={wizardState.sourceSshConnectionId}
            onChange={(updates) => {
              if (typeof updates.path === 'string') {
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
          />
        )

      case 'source':
        return (
          <WizardStepDataSource
            repositoryLocation={wizardState.repositoryLocation}
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
            showRemotePath={false}
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
            }}
            onChange={handleStateChange}
            onBrowseExclude={() => setShowExcludeExplorer(true)}
            showAdvancedOptions={false}
          />
        )

      case 'review':
        return (
          <WizardStepReview
            mode={mode}
            data={{
              name: wizardState.name,
              borgVersion: wizardState.borgVersion,
              repositoryMode: wizardState.repositoryMode,
              repositoryLocation: wizardState.repositoryLocation,
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
            }}
            sshConnections={sshConnections}
          />
        )

      default:
        return null
    }
  }

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

      {/* File Explorer Dialogs */}
      <FileExplorerDialog
        key={`path-explorer-${wizardState.repositoryLocation}-${wizardState.repoSshConnectionId}`}
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
          wizardState.repositoryLocation === 'ssh' && wizardState.repoSshConnectionId
            ? sshConnections.find((c) => c.id === wizardState.repoSshConnectionId)?.default_path ||
              '/'
            : '/'
        }
        multiSelect={false}
        connectionType={wizardState.repositoryLocation === 'local' ? 'local' : 'ssh'}
        sshConfig={
          wizardState.repositoryLocation === 'ssh' && wizardState.repoSshConnectionId
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

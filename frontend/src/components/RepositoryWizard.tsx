import React, { useState, useEffect, useMemo } from 'react'
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Box,
  Button,
  Typography,
} from '@mui/material'
import { FolderOpen, Database, Shield, Settings, CheckCircle } from 'lucide-react'
import {
  WizardStepIndicator,
  WizardStepLocation,
  WizardStepDataSource,
  WizardStepSecurity,
  WizardStepBackupConfig,
  WizardStepReview,
} from './wizard'
import FileExplorerDialog from './FileExplorerDialog'
import { sshKeysAPI, RepositoryData } from '../services/api'
import { useMatomo } from '../hooks/useMatomo'

interface Repository extends RepositoryData {
  id: number
  source_ssh_connection_id?: number | null
  source_directories?: string[]
  exclude_patterns?: string[]
  custom_flags?: string
  remote_path?: string
  pre_backup_script?: string
  post_backup_script?: string
  pre_hook_timeout?: number
  post_hook_timeout?: number
  continue_on_hook_failure?: boolean
  bypass_lock?: boolean
}

interface RepositoryWizardProps {
  open: boolean
  onClose: () => void
  mode: 'create' | 'edit' | 'import'
  repository?: Repository
  onSubmit: (data: RepositoryData) => void
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
  repositoryMode: 'full' | 'observe'
  repositoryLocation: 'local' | 'ssh'
  path: string
  repoSshConnectionId: number | ''
  bypassLock: boolean
  // Repository type details (for SSH)
  repositoryType: 'local' | 'ssh' | 'sftp'
  host: string
  username: string
  port: string
  sshKeyId: number | ''
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
  continueOnHookFailure: boolean
}

const initialState: WizardState = {
  name: '',
  repositoryMode: 'full',
  repositoryLocation: 'local',
  path: '',
  repoSshConnectionId: '',
  bypassLock: false,
  repositoryType: 'local',
  host: '',
  username: '',
  port: '22',
  sshKeyId: '',
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
  continueOnHookFailure: false,
}

const RepositoryWizard = ({ open, onClose, mode, repository, onSubmit }: RepositoryWizardProps) => {
  const { track, trackRepository, EventCategory, EventAction } = useMatomo()
  const [activeStep, setActiveStep] = useState(0)
  const [wizardState, setWizardState] = useState<WizardState>(initialState)
  const [sshConnections, setSshConnections] = useState<SSHConnection[]>([])

  // File explorer states
  const [showPathExplorer, setShowPathExplorer] = useState(false)
  const [showSourceExplorer, setShowSourceExplorer] = useState(false)
  const [showRemoteSourceExplorer, setShowRemoteSourceExplorer] = useState(false)
  const [showExcludeExplorer, setShowExcludeExplorer] = useState(false)

  // Step definitions
  const steps = useMemo(() => {
    const baseSteps = [{ key: 'location', label: 'Location', icon: <FolderOpen size={14} /> }]

    // Add data source step only for full mode (not observe) and not import
    if (wizardState.repositoryMode === 'full' || mode === 'import') {
      baseSteps.push({ key: 'source', label: 'Source', icon: <Database size={14} /> })
    }

    baseSteps.push({ key: 'security', label: 'Security', icon: <Shield size={14} /> })

    // Add backup config step only for full mode
    if (wizardState.repositoryMode === 'full') {
      baseSteps.push({ key: 'config', label: 'Config', icon: <Settings size={14} /> })
    }

    baseSteps.push({ key: 'review', label: 'Review', icon: <CheckCircle size={14} /> })

    return baseSteps
  }, [wizardState.repositoryMode, mode])

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
    let repoHost = repository.host || ''
    let repoUsername = repository.username || ''
    let repoPort = repository.port || 22

    // Parse SSH URL format
    if (repoPath.startsWith('ssh://')) {
      let sshUrlMatch = repoPath.match(/^ssh:\/\/([^@]+)@([^:/]+):(\d+)(.*)$/)
      if (sshUrlMatch) {
        repoUsername = sshUrlMatch[1]
        repoHost = sshUrlMatch[2]
        repoPort = parseInt(sshUrlMatch[3])
        repoPath = sshUrlMatch[4]
      } else {
        sshUrlMatch = repoPath.match(/^ssh:\/\/([^@]+)@([^/]+)(.*)$/)
        if (sshUrlMatch) {
          repoUsername = sshUrlMatch[1]
          repoHost = sshUrlMatch[2]
          repoPort = 22
          repoPath = sshUrlMatch[3]
        }
      }
    }

    setWizardState({
      name: repository.name || '',
      repositoryMode: repository.mode || 'full',
      repositoryLocation: repository.repository_type === 'local' ? 'local' : 'ssh',
      path: repoPath,
      repoSshConnectionId: '',
      bypassLock: repository.bypass_lock || false,
      repositoryType: (repository.repository_type as 'local' | 'ssh' | 'sftp') || 'local',
      host: repoHost,
      username: repoUsername,
      port: String(repoPort),
      sshKeyId: repository.ssh_key_id || '',
      dataSource: repository.source_ssh_connection_id ? 'remote' : 'local',
      sourceSshConnectionId: repository.source_ssh_connection_id || '',
      sourceDirs: repository.source_directories || [],
      encryption: repository.encryption || 'repokey',
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
      continueOnHookFailure: repository.continue_on_hook_failure || false,
    })
  }, [repository])

  // Reset form
  const resetForm = () => {
    setActiveStep(0)
    setWizardState(initialState)
  }

  // Handle state changes
  const handleStateChange = (updates: Partial<WizardState>) => {
    setWizardState((prev) => ({ ...prev, ...updates }))
  }

  // Handle SSH connection selection for repository
  const handleRepoSshConnectionSelect = (connectionId: number) => {
    const connection = sshConnections.find((c) => c.id === connectionId)
    if (connection) {
      handleStateChange({
        repoSshConnectionId: connectionId,
        repositoryType: 'ssh',
        host: connection.host,
        username: connection.username,
        port: String(connection.port),
        sshKeyId: connection.ssh_key_id,
        path: connection.default_path || wizardState.path,
      })
    }
  }

  // Handle path change with SSH URL detection
  const handlePathChange = (newPath: string) => {
    if (newPath.startsWith('ssh://')) {
      const matchWithPort = newPath.match(/^ssh:\/\/([^@]+)@([^:/]+):(\d+)(.*)$/)
      const matchWithoutPort = newPath.match(/^ssh:\/\/([^@]+)@([^/]+)(.*)$/)

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
          repositoryType: 'ssh',
          path: remotePath || '/',
          host: parsedHost,
          username: parsedUsername,
          port: parsedPort,
          repoSshConnectionId: matchingConnection?.id || '',
          sshKeyId: matchingConnection?.ssh_key_id || '',
        })
        return
      } else if (matchWithoutPort) {
        const [, parsedUsername, parsedHost, remotePath] = matchWithoutPort
        const matchingConnection = sshConnections.find(
          (c) => c.username === parsedUsername && c.host === parsedHost && c.port === 22
        )

        handleStateChange({
          repositoryLocation: 'ssh',
          repositoryType: 'ssh',
          path: remotePath || '/',
          host: parsedHost,
          username: parsedUsername,
          port: '22',
          repoSshConnectionId: matchingConnection?.id || '',
          sshKeyId: matchingConnection?.ssh_key_id || '',
        })
        return
      }
    }

    handleStateChange({ path: newPath })
  }

  // Handle source directories change with SSH URL detection
  const handleSourceDirsChange = (paths: string[]) => {
    const processedPaths: string[] = []
    let detectedSshConnection: SSHConnection | null = null

    for (const p of paths) {
      if (p.startsWith('ssh://')) {
        const matchWithPort = p.match(/^ssh:\/\/([^@]+)@([^:/]+):(\d+)(.*)$/)
        const matchWithoutPort = p.match(/^ssh:\/\/([^@]+)@([^/]+)(.*)$/)

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

    if (detectedSshConnection) {
      handleStateChange({
        dataSource: 'remote',
        sourceSshConnectionId: detectedSshConnection.id,
        sourceDirs: [...wizardState.sourceDirs, ...processedPaths],
      })
    } else {
      handleStateChange({
        sourceDirs: [...wizardState.sourceDirs, ...processedPaths],
      })
    }
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
        if (wizardState.repositoryMode !== 'observe' && wizardState.sourceDirs.length === 0)
          return false
        return true

      case 'security':
        if (mode === 'edit') return true
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

  const handleSubmit = () => {
    const data: RepositoryData = {
      name: wizardState.name,
      mode: wizardState.repositoryMode,
      path: wizardState.path,
      repository_type: wizardState.repositoryType,
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
      continue_on_hook_failure: wizardState.continueOnHookFailure,
      bypass_lock: wizardState.bypassLock,
    }

    if (wizardState.repositoryType === 'ssh') {
      data.host = wizardState.host
      data.username = wizardState.username
      data.port = parseInt(wizardState.port) || 22
      data.ssh_key_id = wizardState.sshKeyId
      data.connection_id = wizardState.repoSshConnectionId || null
    }

    if (wizardState.dataSource === 'remote' && wizardState.sourceSshConnectionId) {
      data.source_connection_id = wizardState.sourceSshConnectionId
    }

    track(EventCategory.REPOSITORY, EventAction.CREATE, `wizard-${mode}`)
    trackRepository(
      mode === 'create'
        ? EventAction.CREATE
        : mode === 'import'
          ? EventAction.UPLOAD
          : EventAction.EDIT,
      wizardState.name
    )

    onSubmit(data)
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
              repositoryMode: wizardState.repositoryMode,
              repositoryLocation: wizardState.repositoryLocation,
              path: wizardState.path,
              repoSshConnectionId: wizardState.repoSshConnectionId,
              bypassLock: wizardState.bypassLock,
            }}
            sshConnections={sshConnections}
            onChange={(updates) => {
              // Handle SSH connection selection
              if (
                updates.repoSshConnectionId &&
                updates.repoSshConnectionId !== wizardState.repoSshConnectionId
              ) {
                handleRepoSshConnectionSelect(updates.repoSshConnectionId as number)
              } else if (updates.repositoryLocation === 'local') {
                handleStateChange({
                  ...updates,
                  repositoryType: 'local',
                  host: '',
                  username: '',
                  port: '22',
                  sshKeyId: '',
                })
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
            onChange={handleStateChange}
            onBrowseSource={() => setShowSourceExplorer(true)}
            onBrowseRemoteSource={() => setShowRemoteSourceExplorer(true)}
          />
        )

      case 'security':
        return (
          <WizardStepSecurity
            mode={mode}
            data={{
              encryption: wizardState.encryption,
              passphrase: wizardState.passphrase,
              remotePath: wizardState.remotePath,
              selectedKeyfile: wizardState.selectedKeyfile,
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
              continueOnHookFailure: wizardState.continueOnHookFailure,
            }}
            onChange={handleStateChange}
            onBrowseExclude={() => setShowExcludeExplorer(true)}
          />
        )

      case 'review':
        return (
          <WizardStepReview
            mode={mode}
            data={{
              name: wizardState.name,
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
              host: wizardState.host,
              username: wizardState.username,
              port: parseInt(wizardState.port) || 22,
              repositoryType: wizardState.repositoryType,
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
      <Dialog
        open={open}
        onClose={onClose}
        maxWidth="md"
        fullWidth
        PaperProps={{
          sx: {
            borderRadius: 3,
            overflow: 'hidden',
            backdropFilter: 'blur(10px)',
            backgroundImage:
              'linear-gradient(rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.05))',
            boxShadow: (theme) =>
              theme.palette.mode === 'dark'
                ? '0 24px 48px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.1)'
                : '0 24px 48px rgba(0,0,0,0.1)',
          },
        }}
      >
        <DialogTitle sx={{ pt: 3, pb: 1 }}>
          <Typography variant="h5" component="div" fontWeight={700}>
            {mode === 'create' ? 'Create' : mode === 'edit' ? 'Edit' : 'Import'} Repository
          </Typography>
        </DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2 }}>
            {/* Step Indicator */}
            <WizardStepIndicator
              steps={steps}
              currentStep={activeStep}
              onStepClick={setActiveStep}
            />

            {/* Step Content - Fixed height to prevent layout shift */}
            <Box sx={{ height: 450, overflow: 'auto', p: 3 }}>{renderStepContent()}</Box>
          </Box>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose}>Cancel</Button>
          <Box sx={{ flex: 1 }} />
          <Button disabled={activeStep === 0} onClick={handleBack}>
            Back
          </Button>
          {activeStep < steps.length - 1 ? (
            <Button variant="contained" onClick={handleNext} disabled={!canProceed()}>
              Next
            </Button>
          ) : (
            <Button variant="contained" onClick={handleSubmit} disabled={!canProceed()}>
              {mode === 'create'
                ? 'Create Repository'
                : mode === 'edit'
                  ? 'Save Changes'
                  : 'Import Repository'}
            </Button>
          )}
        </DialogActions>
      </Dialog>

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
        title="Select Repository Path"
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
            ? 'Select Source Directories (Remote Machine)'
            : 'Select Source Directories'
        }
        initialPath="/"
        multiSelect={true}
        connectionType="local"
        selectMode="directories"
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
              title="Select Source Directories (Remote)"
              initialPath="/"
              multiSelect={true}
              connectionType="ssh"
              sshConfig={config}
              selectMode="directories"
            />
          )
        })()}

      <FileExplorerDialog
        open={showExcludeExplorer}
        onClose={() => setShowExcludeExplorer(false)}
        onSelect={(paths) => {
          handleStateChange({
            excludePatterns: [...wizardState.excludePatterns, ...paths],
          })
        }}
        title="Select Directories/Files to Exclude"
        initialPath="/"
        multiSelect={true}
        connectionType="local"
        selectMode="both"
      />
    </>
  )
}

export default RepositoryWizard

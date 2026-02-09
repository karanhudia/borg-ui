import { useState, useEffect, useMemo } from 'react'
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Box,
  Button,
  Typography,
} from '@mui/material'
import { HardDrive, FolderOpen, CheckCircle } from 'lucide-react'
import {
  WizardStepIndicator,
  WizardStepRestoreDestination,
  WizardStepRestorePath,
  WizardStepRestoreReview,
} from './wizard'
import FileExplorerDialog from './FileExplorerDialog'
import { sshKeysAPI } from '../services/api'
import { useMatomo } from '../hooks/useMatomo'

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

interface ArchiveFile {
  path: string
  mode: string
  user: string
  group: string
  size: number
  mtime: string
  healthy: boolean
}

interface RestoreWizardProps {
  open: boolean
  onClose: () => void
  archiveName: string
  repositoryId: number
  selectedFiles: ArchiveFile[]
  onRestore: (data: RestoreData) => void
}

export interface RestoreData {
  destination_type: 'local' | 'ssh'
  destination_connection_id: number | null
  restore_strategy: 'original' | 'custom'
  custom_path: string | null
}

interface WizardState {
  // Step 1: Destination
  destinationType: 'local' | 'ssh'
  destinationConnectionId: number | ''

  // Step 2: Path
  restoreStrategy: 'original' | 'custom'
  customPath: string
}

const initialState: WizardState = {
  destinationType: 'local',
  destinationConnectionId: '',
  restoreStrategy: 'original',
  customPath: '',
}

const RestoreWizard = ({
  open,
  onClose,
  archiveName,
  repositoryId,
  selectedFiles,
  onRestore,
}: RestoreWizardProps) => {
  const { track, EventCategory, EventAction } = useMatomo()
  const [activeStep, setActiveStep] = useState(0)
  const [wizardState, setWizardState] = useState<WizardState>(initialState)
  const [sshConnections, setSshConnections] = useState<SSHConnection[]>([])

  // File explorer state
  const [showPathExplorer, setShowPathExplorer] = useState(false)

  // Step definitions
  const steps = useMemo(
    () => [
      { key: 'destination', label: 'Destination', icon: <HardDrive size={14} /> },
      { key: 'path', label: 'Path', icon: <FolderOpen size={14} /> },
      { key: 'review', label: 'Review', icon: <CheckCircle size={14} /> },
    ],
    []
  )

  // Load SSH connections
  const loadSshConnections = async () => {
    try {
      const connectionsRes = await sshKeysAPI.getSSHConnections()
      const connections = connectionsRes.data?.connections || []
      setSshConnections(Array.isArray(connections) ? connections : [])
    } catch (error) {
      console.error('Failed to load SSH connections:', error)
      setSshConnections([])
    }
  }

  // Initialize/reset on dialog open/close or archive change
  useEffect(() => {
    if (open) {
      setActiveStep(0)
      setWizardState(initialState)
      loadSshConnections()
    }
  }, [open, archiveName, repositoryId])

  // Handle state changes
  const handleStateChange = (updates: Partial<WizardState>) => {
    setWizardState((prev) => ({ ...prev, ...updates }))
  }

  // Handle SSH connection selection
  const handleSshConnectionSelect = (connectionId: number) => {
    const connection = sshConnections.find((c) => c.id === connectionId)
    if (connection) {
      handleStateChange({
        destinationConnectionId: connectionId,
        customPath: connection.default_path || wizardState.customPath,
      })
    }
  }

  // Validation
  const canProceed = () => {
    const currentStepKey = steps[activeStep]?.key

    switch (currentStepKey) {
      case 'destination':
        if (wizardState.destinationType === 'ssh' && !wizardState.destinationConnectionId) {
          return false
        }
        return true

      case 'path':
        if (wizardState.restoreStrategy === 'custom' && !wizardState.customPath.trim()) {
          return false
        }
        return true

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
    const data: RestoreData = {
      destination_type: wizardState.destinationType,
      destination_connection_id:
        wizardState.destinationType === 'ssh' && wizardState.destinationConnectionId
          ? (wizardState.destinationConnectionId as number)
          : null,
      restore_strategy: wizardState.restoreStrategy,
      custom_path: wizardState.restoreStrategy === 'custom' ? wizardState.customPath : null,
    }

    track(EventCategory.ARCHIVE, EventAction.DOWNLOAD, 'restore-wizard')

    onRestore(data)
  }

  // Render current step content
  const renderStepContent = () => {
    const currentStepKey = steps[activeStep]?.key

    switch (currentStepKey) {
      case 'destination':
        return (
          <WizardStepRestoreDestination
            data={{
              destinationType: wizardState.destinationType,
              destinationConnectionId: wizardState.destinationConnectionId,
            }}
            sshConnections={sshConnections}
            onChange={(updates) => {
              // Handle SSH connection selection
              if (
                updates.destinationConnectionId &&
                updates.destinationConnectionId !== wizardState.destinationConnectionId
              ) {
                handleSshConnectionSelect(updates.destinationConnectionId as number)
              } else {
                handleStateChange(updates)
              }
            }}
          />
        )

      case 'path':
        return (
          <WizardStepRestorePath
            data={{
              restoreStrategy: wizardState.restoreStrategy,
              customPath: wizardState.customPath,
            }}
            selectedFiles={selectedFiles}
            destinationType={wizardState.destinationType}
            destinationConnectionId={wizardState.destinationConnectionId}
            sshConnections={sshConnections}
            onChange={handleStateChange}
            onBrowsePath={() => setShowPathExplorer(true)}
          />
        )

      case 'review':
        return (
          <WizardStepRestoreReview
            data={{
              destinationType: wizardState.destinationType,
              destinationConnectionId: wizardState.destinationConnectionId,
              restoreStrategy: wizardState.restoreStrategy,
              customPath: wizardState.customPath,
            }}
            selectedFiles={selectedFiles}
            sshConnections={sshConnections}
            archiveName={archiveName}
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
            Restore Files
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            From archive: {archiveName}
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
              Restore Files
            </Button>
          )}
        </DialogActions>
      </Dialog>

      {/* File Explorer Dialog for custom path */}
      {showPathExplorer && (
        <FileExplorerDialog
          key={`path-explorer-${wizardState.destinationType}-${wizardState.destinationConnectionId}`}
          open={showPathExplorer}
          onClose={() => setShowPathExplorer(false)}
          onSelect={(paths) => {
            if (paths.length > 0) {
              handleStateChange({ customPath: paths[0] })
            }
            setShowPathExplorer(false)
          }}
          title="Select Restore Destination"
          initialPath={
            wizardState.destinationType === 'ssh' && wizardState.destinationConnectionId
              ? sshConnections.find((c) => c.id === wizardState.destinationConnectionId)
                  ?.default_path || '/'
              : '/'
          }
          multiSelect={false}
          connectionType={wizardState.destinationType === 'local' ? 'local' : 'ssh'}
          sshConfig={
            wizardState.destinationType === 'ssh' && wizardState.destinationConnectionId
              ? (() => {
                  const conn = sshConnections.find(
                    (c) => c.id === wizardState.destinationConnectionId
                  )
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
      )}
    </>
  )
}

export default RestoreWizard

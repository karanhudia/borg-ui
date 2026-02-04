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
import { FileText, Clock, Code, Wrench, CheckCircle } from 'lucide-react'
import { WizardStepIndicator } from './wizard'
import {
  WizardStepBasicInfo,
  WizardStepScheduleConfig,
  WizardStepScripts,
  WizardStepMaintenance,
  WizardStepScheduleReview,
} from './wizard/schedule'
import { convertCronToUTC, convertCronToLocal } from '../utils/dateUtils'
import { useMatomo } from '../hooks/useMatomo'
import { ScriptParameter } from './ScriptParameterInputs'

export interface ScheduledJob {
  id: number
  name: string
  cron_expression: string
  repository: string | null
  repository_id: number | null
  repository_ids: number[] | null
  enabled: boolean
  description: string | null
  archive_name_template: string | null
  run_repository_scripts: boolean
  pre_backup_script_id: number | null
  post_backup_script_id: number | null
  pre_backup_script_parameters?: Record<string, string> | null
  post_backup_script_parameters?: Record<string, string> | null
  run_prune_after: boolean
  run_compact_after: boolean
  prune_keep_hourly: number
  prune_keep_daily: number
  prune_keep_weekly: number
  prune_keep_monthly: number
  prune_keep_quarterly: number
  prune_keep_yearly: number
}

export interface Repository {
  id: number
  name: string
  path: string
  mode?: string
  [key: string]: unknown
}

export interface Script {
  id: number
  name: string
  parameters?: ScriptParameter[] | null
}

interface ScheduleWizardProps {
  open: boolean
  onClose: () => void
  mode: 'create' | 'edit'
  scheduledJob?: ScheduledJob
  repositories: Repository[]
  scripts: Script[]
  onSubmit: (data: ScheduleData) => void
}

export interface ScheduleData {
  name: string
  description: string | null
  repository_ids: number[]
  enabled: boolean
  cron_expression: string
  archive_name_template: string
  pre_backup_script_id: number | null
  post_backup_script_id: number | null
  pre_backup_script_parameters?: Record<string, string>
  post_backup_script_parameters?: Record<string, string>
  run_repository_scripts: boolean
  run_prune_after: boolean
  run_compact_after: boolean
  prune_keep_hourly: number
  prune_keep_daily: number
  prune_keep_weekly: number
  prune_keep_monthly: number
  prune_keep_quarterly: number
  prune_keep_yearly: number
  [key: string]: unknown
}

interface WizardState {
  // Step 1: Basic Info
  name: string
  description: string
  repositoryIds: number[]

  // Step 2: Schedule
  cronExpression: string
  archiveNameTemplate: string

  // Step 3: Scripts
  preBackupScriptId: number | null
  postBackupScriptId: number | null
  preBackupScriptParameters: Record<string, string>
  postBackupScriptParameters: Record<string, string>
  runRepositoryScripts: boolean

  // Step 4: Maintenance
  runPruneAfter: boolean
  runCompactAfter: boolean
  pruneKeepHourly: number
  pruneKeepDaily: number
  pruneKeepWeekly: number
  pruneKeepMonthly: number
  pruneKeepQuarterly: number
  pruneKeepYearly: number
}

const initialState: WizardState = {
  name: '',
  description: '',
  repositoryIds: [],
  cronExpression: '0 2 * * *',
  archiveNameTemplate: '{job_name}-{now}',
  preBackupScriptId: null,
  postBackupScriptId: null,
  preBackupScriptParameters: {},
  postBackupScriptParameters: {},
  runRepositoryScripts: false,
  runPruneAfter: false,
  runCompactAfter: false,
  pruneKeepHourly: 0,
  pruneKeepDaily: 7,
  pruneKeepWeekly: 4,
  pruneKeepMonthly: 6,
  pruneKeepQuarterly: 0,
  pruneKeepYearly: 1,
}

const ScheduleWizard: React.FC<ScheduleWizardProps> = ({
  open,
  onClose,
  mode,
  scheduledJob,
  repositories,
  scripts,
  onSubmit,
}) => {
  const { track, EventCategory, EventAction } = useMatomo()
  const [activeStep, setActiveStep] = useState(0)
  const [wizardState, setWizardState] = useState<WizardState>(initialState)

  // Step definitions
  const steps = useMemo(
    () => [
      { key: 'basic', label: 'Basic', icon: <FileText size={14} /> },
      { key: 'schedule', label: 'Schedule', icon: <Clock size={14} /> },
      { key: 'scripts', label: 'Scripts', icon: <Code size={14} /> },
      { key: 'maintenance', label: 'Maintenance', icon: <Wrench size={14} /> },
      { key: 'review', label: 'Review', icon: <CheckCircle size={14} /> },
    ],
    []
  )

  // Populate form data for edit mode
  const populateEditData = React.useCallback(() => {
    if (!scheduledJob) return

    // Handle converting old single-repo format to new multi-repo format
    let repository_ids: number[] = []
    if (scheduledJob.repository_ids && scheduledJob.repository_ids.length > 0) {
      repository_ids = scheduledJob.repository_ids
    } else if (scheduledJob.repository_id) {
      repository_ids = [scheduledJob.repository_id]
    } else if (scheduledJob.repository) {
      const repo = repositories?.find((r: Repository) => r.path === scheduledJob.repository)
      if (repo) {
        repository_ids = [repo.id]
      }
    }

    // Convert UTC cron expression from server to local time for editing
    const localCron = convertCronToLocal(scheduledJob.cron_expression)

    setWizardState({
      name: scheduledJob.name,
      description: scheduledJob.description || '',
      repositoryIds: Array.from(new Set(repository_ids)),
      cronExpression: localCron,
      archiveNameTemplate: scheduledJob.archive_name_template || '{job_name}-{now}',
      preBackupScriptId: scheduledJob.pre_backup_script_id || null,
      postBackupScriptId: scheduledJob.post_backup_script_id || null,
      preBackupScriptParameters: scheduledJob.pre_backup_script_parameters || {},
      postBackupScriptParameters: scheduledJob.post_backup_script_parameters || {},
      runRepositoryScripts: scheduledJob.run_repository_scripts || false,
      runPruneAfter: scheduledJob.run_prune_after || false,
      runCompactAfter: scheduledJob.run_compact_after || false,
      pruneKeepHourly: scheduledJob.prune_keep_hourly ?? 0,
      pruneKeepDaily: scheduledJob.prune_keep_daily ?? 7,
      pruneKeepWeekly: scheduledJob.prune_keep_weekly ?? 4,
      pruneKeepMonthly: scheduledJob.prune_keep_monthly ?? 6,
      pruneKeepQuarterly: scheduledJob.prune_keep_quarterly ?? 0,
      pruneKeepYearly: scheduledJob.prune_keep_yearly ?? 1,
    })
  }, [scheduledJob, repositories])

  // Reset form
  const resetForm = () => {
    setActiveStep(0)
    setWizardState(initialState)
  }

  // Handle state changes
  const handleStateChange = (updates: Partial<WizardState>) => {
    setWizardState((prev) => ({ ...prev, ...updates }))
  }

  // Initialize on dialog open
  useEffect(() => {
    if (open) {
      setActiveStep(0)
      if (mode === 'edit' && scheduledJob) {
        populateEditData()
      } else {
        resetForm()
      }
    }
  }, [open, mode, scheduledJob, populateEditData])

  // Validation
  const canProceed = () => {
    const currentStepKey = steps[activeStep]?.key

    switch (currentStepKey) {
      case 'basic':
        if (!wizardState.name.trim()) return false
        if (wizardState.repositoryIds.length === 0) return false
        return true

      case 'schedule':
        if (!wizardState.cronExpression.trim()) return false
        if (!wizardState.archiveNameTemplate.trim()) return false
        return true

      case 'scripts':
      case 'maintenance':
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
    // Convert cron expression from local time to UTC before sending to server
    const utcCron = convertCronToUTC(wizardState.cronExpression)

    const data: ScheduleData = {
      name: wizardState.name,
      description: wizardState.description || null,
      repository_ids: Array.from(new Set(wizardState.repositoryIds)),
      enabled: mode === 'edit' && scheduledJob ? scheduledJob.enabled : true,
      cron_expression: utcCron,
      archive_name_template: wizardState.archiveNameTemplate,
      pre_backup_script_id: wizardState.preBackupScriptId,
      post_backup_script_id: wizardState.postBackupScriptId,
      pre_backup_script_parameters: wizardState.preBackupScriptParameters,
      post_backup_script_parameters: wizardState.postBackupScriptParameters,
      run_repository_scripts: wizardState.runRepositoryScripts,
      run_prune_after: wizardState.runPruneAfter,
      run_compact_after: wizardState.runCompactAfter,
      prune_keep_hourly: wizardState.pruneKeepHourly,
      prune_keep_daily: wizardState.pruneKeepDaily,
      prune_keep_weekly: wizardState.pruneKeepWeekly,
      prune_keep_monthly: wizardState.pruneKeepMonthly,
      prune_keep_quarterly: wizardState.pruneKeepQuarterly,
      prune_keep_yearly: wizardState.pruneKeepYearly,
    }

    track(
      EventCategory.BACKUP,
      mode === 'create' ? EventAction.CREATE : EventAction.EDIT,
      `schedule-wizard-${mode}`
    )

    onSubmit(data)
    onClose()
  }

  // Render current step content
  const renderStepContent = () => {
    const currentStepKey = steps[activeStep]?.key

    switch (currentStepKey) {
      case 'basic':
        return (
          <WizardStepBasicInfo
            data={{
              name: wizardState.name,
              description: wizardState.description,
              repositoryIds: wizardState.repositoryIds,
            }}
            repositories={repositories}
            onChange={handleStateChange}
          />
        )

      case 'schedule':
        return (
          <WizardStepScheduleConfig
            data={{
              cronExpression: wizardState.cronExpression,
              archiveNameTemplate: wizardState.archiveNameTemplate,
            }}
            jobName={wizardState.name}
            onChange={handleStateChange}
          />
        )

      case 'scripts':
        return (
          <WizardStepScripts
            data={{
              preBackupScriptId: wizardState.preBackupScriptId,
              postBackupScriptId: wizardState.postBackupScriptId,
              preBackupScriptParameters: wizardState.preBackupScriptParameters,
              postBackupScriptParameters: wizardState.postBackupScriptParameters,
              runRepositoryScripts: wizardState.runRepositoryScripts,
            }}
            scripts={scripts}
            repositoryCount={wizardState.repositoryIds.length}
            onChange={handleStateChange}
          />
        )

      case 'maintenance':
        return (
          <WizardStepMaintenance
            data={{
              runPruneAfter: wizardState.runPruneAfter,
              runCompactAfter: wizardState.runCompactAfter,
              pruneKeepHourly: wizardState.pruneKeepHourly,
              pruneKeepDaily: wizardState.pruneKeepDaily,
              pruneKeepWeekly: wizardState.pruneKeepWeekly,
              pruneKeepMonthly: wizardState.pruneKeepMonthly,
              pruneKeepQuarterly: wizardState.pruneKeepQuarterly,
              pruneKeepYearly: wizardState.pruneKeepYearly,
            }}
            onChange={handleStateChange}
          />
        )

      case 'review':
        return (
          <WizardStepScheduleReview
            data={wizardState}
            repositories={repositories}
            scripts={scripts}
          />
        )

      default:
        return null
    }
  }

  return (
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
          backgroundImage: 'linear-gradient(rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.05))',
          boxShadow: (theme) =>
            theme.palette.mode === 'dark'
              ? '0 24px 48px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.1)'
              : '0 24px 48px rgba(0,0,0,0.1)',
        },
      }}
    >
      <DialogTitle sx={{ pt: 3, pb: 1 }}>
        <Typography variant="h5" component="div" fontWeight={700}>
          {mode === 'create' ? 'Create' : 'Edit'} Backup Schedule
        </Typography>
      </DialogTitle>
      <DialogContent sx={{ pb: 1 }}>
        <Box sx={{ mt: 1.5 }}>
          {/* Step Indicator */}
          <WizardStepIndicator steps={steps} currentStep={activeStep} onStepClick={setActiveStep} />

          {/* Step Content - Fixed height to prevent layout shift */}
          <Box
            sx={{
              height: 450,
              overflow: 'auto',
              p: 2.5,
            }}
          >
            {renderStepContent()}
          </Box>
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
            {mode === 'create' ? 'Create Schedule' : 'Save Changes'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  )
}

export default ScheduleWizard

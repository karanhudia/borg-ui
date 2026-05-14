import React, { useState, useEffect, useRef, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { DialogActions, Box, Button } from '@mui/material'
import { FileText, Clock, Code, Wrench, CheckCircle } from 'lucide-react'
import { WizardDialog } from './wizard'
import {
  WizardStepBasicInfo,
  WizardStepScheduleConfig,
  WizardStepScripts,
  WizardStepMaintenance,
  WizardStepScheduleReview,
} from './wizard/schedule'
import { getBrowserTimeZone } from '../utils/dateUtils'
import { useAnalytics } from '../hooks/useAnalytics'
import { ScriptParameter } from './ScriptParameterInputs'
import { Repository } from '../types'

export interface ScheduledJob {
  id: number
  name: string
  cron_expression: string
  timezone?: string | null
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
  timezone: string
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
  timezone: string
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

const createInitialState = (): WizardState => ({
  name: '',
  description: '',
  repositoryIds: [],
  cronExpression: '0 2 * * *',
  timezone: getBrowserTimeZone(),
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
})

const ScheduleWizard: React.FC<ScheduleWizardProps> = ({
  open,
  onClose,
  mode,
  scheduledJob,
  repositories,
  scripts,
  onSubmit,
}) => {
  const { track, EventCategory, EventAction } = useAnalytics()
  const { t } = useTranslation()
  const [activeStep, setActiveStep] = useState(0)
  const [wizardState, setWizardState] = useState<WizardState>(createInitialState)
  const prevOpenRef = useRef(false)

  // Step definitions
  const steps = useMemo(
    () => [
      { key: 'basic', label: t('scheduleWizard.steps.basic'), icon: <FileText size={14} /> },
      { key: 'schedule', label: t('scheduleWizard.steps.schedule'), icon: <Clock size={14} /> },
      { key: 'scripts', label: t('scheduleWizard.steps.scripts'), icon: <Code size={14} /> },
      {
        key: 'maintenance',
        label: t('scheduleWizard.steps.maintenance'),
        icon: <Wrench size={14} />,
      },
      { key: 'review', label: t('scheduleWizard.steps.review'), icon: <CheckCircle size={14} /> },
    ],
    [t]
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

    setWizardState({
      name: scheduledJob.name,
      description: scheduledJob.description || '',
      repositoryIds: Array.from(new Set(repository_ids)),
      cronExpression: scheduledJob.cron_expression,
      timezone: scheduledJob.timezone || 'UTC',
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
    setWizardState(createInitialState())
  }

  // Handle state changes
  const handleStateChange = (updates: Partial<WizardState>) => {
    setWizardState((prev) => ({ ...prev, ...updates }))
  }

  // Initialize on dialog open (only on false → true transition)
  useEffect(() => {
    const wasOpen = prevOpenRef.current
    prevOpenRef.current = open

    if (open && !wasOpen) {
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
        if (!wizardState.timezone.trim()) return false
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
    const data: ScheduleData = {
      name: wizardState.name,
      description: wizardState.description || null,
      repository_ids: Array.from(new Set(wizardState.repositoryIds)),
      enabled: mode === 'edit' && scheduledJob ? scheduledJob.enabled : true,
      cron_expression: wizardState.cronExpression,
      timezone: wizardState.timezone,
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

    track(EventCategory.BACKUP, mode === 'create' ? EventAction.CREATE : EventAction.EDIT, {
      entity: 'schedule',
      source: 'wizard',
      mode,
      repository_count: wizardState.repositoryIds.length,
    })

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
              timezone: wizardState.timezone,
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
    <WizardDialog
      open={open}
      onClose={onClose}
      title={mode === 'create' ? t('scheduleWizard.titleCreate') : t('scheduleWizard.titleEdit')}
      steps={steps}
      currentStep={activeStep}
      onStepClick={setActiveStep}
      stepContentSx={{ p: { xs: 1, sm: 2.5 } }}
      footer={
        <DialogActions sx={{ px: { xs: 1, sm: 3 }, pb: { xs: 1, sm: 2 } }}>
          <Button onClick={onClose}>{t('common.buttons.cancel')}</Button>
          <Box sx={{ flex: 1 }} />
          <Button disabled={activeStep === 0} onClick={handleBack}>
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
              disabled={!canProceed()}
              sx={{ boxShadow: '0 2px 8px rgba(37,99,235,0.3)' }}
            >
              {mode === 'create'
                ? t('scheduleWizard.finalButtonCreate')
                : t('scheduleWizard.finalButtonEdit')}
            </Button>
          )}
        </DialogActions>
      }
    >
      {renderStepContent()}
    </WizardDialog>
  )
}

export default ScheduleWizard

import { useCallback, useState } from 'react'
import { Alert, Button, DialogActions, Stack } from '@mui/material'
import {
  CalendarClock,
  Compass,
  FolderOpen,
  HardDrive,
  ListChecks,
  Lock,
  Plug,
  type LucideIcon,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { toast } from 'react-hot-toast'

import WizardDialog, { type WizardStep } from '../shared/WizardDialog'
import { usePlan } from '../../hooks/usePlan'
import { backupPlansAPI } from '../../services/api'
import { getApiErrorDetail } from '../../utils/apiErrors'
import { translateBackendKey } from '../../utils/translateBackendKey'
import QuickStartProgress from './QuickStartProgress'
import {
  createInitialQuickStartAnswers,
  isStepValid,
  suggestedDestinationPath,
  suggestedName,
  visibleSteps,
  type QuickStartAnswers,
  type QuickStartSettingsChange,
  type QuickStartStepKey,
} from './quickStartState'
import QuickStartConnectStep from './steps/QuickStartConnectStep'
import QuickStartDestinationStep from './steps/QuickStartDestinationStep'
import QuickStartFoldersStep from './steps/QuickStartFoldersStep'
import QuickStartProtectStep from './steps/QuickStartProtectStep'
import QuickStartReviewStep from './steps/QuickStartReviewStep'
import QuickStartScheduleStep from './steps/QuickStartScheduleStep'
import QuickStartWhatStep from './steps/QuickStartWhatStep'
import { useQuickStartRunner } from './useQuickStartRunner'

// Color keys come from WizardStepIndicator; each step needs its own.
const STEP_META: Record<QuickStartStepKey, { colorKey: string; icon: LucideIcon }> = {
  what: { colorKey: 'basic', icon: Compass },
  connect: { colorKey: 'config', icon: Plug },
  folders: { colorKey: 'source', icon: FolderOpen },
  destination: { colorKey: 'location', icon: HardDrive },
  protect: { colorKey: 'security', icon: Lock },
  schedule: { colorKey: 'schedule', icon: CalendarClock },
  review: { colorKey: 'review', icon: ListChecks },
}

interface QuickStartDialogProps {
  open: boolean
  onClose: () => void
  initialAnswers?: QuickStartAnswers
  canAddMachine?: boolean
}

export default function QuickStartDialog({
  open,
  onClose,
  initialAnswers,
  canAddMachine = false,
}: QuickStartDialogProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { can } = usePlan()
  const runner = useQuickStartRunner()
  const [answers, setAnswers] = useState<QuickStartAnswers>(
    () => initialAnswers ?? createInitialQuickStartAnswers()
  )
  const [stepIndex, setStepIndex] = useState(0)
  const [startingBackup, setStartingBackup] = useState(false)

  const steps = visibleSteps(answers)
  const step = steps[Math.min(stepIndex, steps.length - 1)]
  const showProgress = runner.actions.length > 0
  const finished = showProgress && !runner.running && !runner.error
  const firstInvalid = steps.find((key) => !isStepValid(key, answers))

  const wizardSteps: WizardStep[] = steps.map((key) => {
    const { colorKey, icon: Icon } = STEP_META[key]
    return { key: colorKey, label: t(`quickStart.steps.${key}`), icon: <Icon size={16} /> }
  })

  const update = useCallback(
    (patch: Partial<QuickStartAnswers>) => setAnswers((prev) => ({ ...prev, ...patch })),
    []
  )
  const updateSettings = useCallback<QuickStartSettingsChange>(
    (patch) => setAnswers((prev) => ({ ...prev, settings: { ...prev.settings, ...patch } })),
    []
  )

  // An SSH key deploy in flight would land in the next session's answers.
  const [busy, setBusy] = useState(false)

  const close = () => {
    if (runner.running || busy) return
    runner.reset()
    setAnswers(initialAnswers ?? createInitialQuickStartAnswers())
    setStepIndex(0)
    onClose()
  }

  const next = () => {
    if (step === 'folders') {
      const name = answers.name.trim() || suggestedName(answers)
      update({
        name,
        destinationPath:
          answers.destinationPath ||
          (answers.destinationKind === 'server' ? suggestedDestinationPath(name) : ''),
      })
    }
    setStepIndex((index) => Math.min(index + 1, steps.length - 1))
  }

  const create = () => {
    void runner.run(answers)
  }

  const runFirstBackup = async () => {
    if (!runner.results.planId) return
    setStartingBackup(true)
    try {
      await backupPlansAPI.run(runner.results.planId)
      toast.success(t('quickStart.progress.backupStarted'))
      close()
      navigate('/backup-plans')
    } catch (error) {
      toast.error(translateBackendKey(getApiErrorDetail(error)))
    } finally {
      setStartingBackup(false)
    }
  }

  const renderStep = () => {
    switch (step) {
      case 'what':
        return (
          <QuickStartWhatStep
            answers={answers}
            onChange={update}
            canUseAgents={can('managed_agents')}
          />
        )
      case 'connect':
        return (
          <QuickStartConnectStep
            answers={answers}
            onChange={update}
            canAddMachine={canAddMachine}
            onBusyChange={setBusy}
          />
        )
      case 'folders':
        return <QuickStartFoldersStep answers={answers} onChange={update} />
      case 'destination':
        return (
          <QuickStartDestinationStep
            answers={answers}
            onChange={update}
            canAddMachine={canAddMachine}
            onBusyChange={setBusy}
          />
        )
      case 'protect':
        return <QuickStartProtectStep answers={answers} onChange={update} />
      case 'schedule':
        return <QuickStartScheduleStep answers={answers} onChange={update} />
      case 'review':
        return (
          <QuickStartReviewStep
            answers={answers}
            onSettingsChange={updateSettings}
            canUseBorg2={can('borg_v2')}
          />
        )
      default:
        return null
    }
  }

  const formFooter = (
    <DialogActions>
      <Button onClick={close} disabled={busy}>
        {t('common.buttons.cancel')}
      </Button>
      <Button onClick={() => setStepIndex((index) => index - 1)} disabled={stepIndex === 0 || busy}>
        {t('common.buttons.back')}
      </Button>
      {step === 'review' ? (
        <Button
          variant="contained"
          onClick={create}
          disabled={Boolean(firstInvalid) || runner.running}
        >
          {t('quickStart.create')}
        </Button>
      ) : (
        <Button variant="contained" onClick={next} disabled={busy || !isStepValid(step, answers)}>
          {t('common.buttons.next')}
        </Button>
      )}
    </DialogActions>
  )

  const progressFooter = (
    <DialogActions>
      {finished ? (
        <>
          <Button onClick={close}>{t('common.buttons.close')}</Button>
          <Button
            onClick={() => {
              close()
              navigate('/backup-plans')
            }}
          >
            {t('quickStart.progress.openPlan')}
          </Button>
          <Button variant="contained" onClick={runFirstBackup} disabled={startingBackup}>
            {t('quickStart.progress.runNow')}
          </Button>
        </>
      ) : (
        <>
          <Button onClick={close} disabled={runner.running}>
            {t('common.buttons.close')}
          </Button>
          <Button onClick={runner.edit} disabled={runner.running}>
            {t('quickStart.progress.editAnswers')}
          </Button>
          <Button variant="contained" onClick={create} disabled={runner.running}>
            {t('quickStart.progress.retry')}
          </Button>
        </>
      )}
    </DialogActions>
  )

  return (
    <WizardDialog
      open={open}
      onClose={close}
      title={t('quickStart.title')}
      subtitle={t('quickStart.subtitle')}
      steps={wizardSteps}
      currentStep={showProgress ? steps.length - 1 : stepIndex}
      onStepClick={
        showProgress
          ? undefined
          : (index) => {
              // Jumping forward is only allowed past steps that are already valid.
              if (
                index <= stepIndex ||
                steps.slice(0, index).every((key) => isStepValid(key, answers))
              )
                setStepIndex(index)
            }
      }
      footer={showProgress ? progressFooter : formFooter}
    >
      {showProgress ? (
        <QuickStartProgress
          actions={runner.actions}
          statuses={runner.statuses}
          error={runner.error}
          finished={finished}
        />
      ) : runner.results.repositoryId ? (
        <Stack spacing={2}>
          <Alert severity="info" variant="outlined">
            {t('quickStart.repositoryAlreadyCreated')}
          </Alert>
          {renderStep()}
        </Stack>
      ) : (
        renderStep()
      )}
    </WizardDialog>
  )
}

import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useTranslation } from 'react-i18next'
import type { Repository } from './types'

interface CreateBackupPlanDialogProps {
  repository: Repository | null
  backupPlanName: string
  copyExistingSchedule: boolean
  disableExistingSchedule: boolean
  moveSourceSettings: boolean
  isPending: boolean
  onClose: () => void
  onPlanNameChange: (value: string) => void
  onCopyExistingScheduleChange: (value: boolean) => void
  onDisableExistingScheduleChange: (value: boolean) => void
  onMoveSourceSettingsChange: (value: boolean) => void
  onConfirm: () => void
}

export function CreateBackupPlanDialog({
  repository,
  backupPlanName,
  copyExistingSchedule,
  disableExistingSchedule,
  moveSourceSettings,
  isPending,
  onClose,
  onPlanNameChange,
  onCopyExistingScheduleChange,
  onDisableExistingScheduleChange,
  onMoveSourceSettingsChange,
  onConfirm,
}: CreateBackupPlanDialogProps) {
  const { t } = useTranslation()

  return (
    <Dialog
      open={Boolean(repository)}
      onClose={() => {
        if (!isPending) {
          onClose()
        }
      }}
      fullWidth
      maxWidth="sm"
    >
      <DialogTitle>{t('repositories.createPlanDialog.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            {t('repositories.createPlanDialog.description', {
              name: repository?.name || '',
            })}
          </Typography>

          <TextField
            label={t('repositories.createPlanDialog.planName')}
            value={backupPlanName}
            onChange={(event) => onPlanNameChange(event.target.value)}
            placeholder={repository ? `${repository.name} Backup Plan` : ''}
            fullWidth
          />

          {repository?.has_schedule && (
            <Alert severity="info">
              {t('repositories.createPlanDialog.scheduleNotice', {
                schedule: repository.schedule_name || t('common.schedule'),
              })}
            </Alert>
          )}

          {repository && !repository.source_directories?.length && (
            <Alert severity="warning">{t('repositories.createPlanDialog.sourceRequired')}</Alert>
          )}

          <FormControlLabel
            control={
              <Checkbox
                checked={moveSourceSettings}
                onChange={(event) => onMoveSourceSettingsChange(event.target.checked)}
              />
            }
            label={t('repositories.createPlanDialog.moveSourceSettings')}
          />

          {repository?.has_schedule && (
            <>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={copyExistingSchedule}
                    onChange={(event) => {
                      onCopyExistingScheduleChange(event.target.checked)
                      if (!event.target.checked) {
                        onDisableExistingScheduleChange(false)
                      }
                    }}
                  />
                }
                label={t('repositories.createPlanDialog.copySchedule')}
              />
              {copyExistingSchedule && (
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={disableExistingSchedule}
                      onChange={(event) => onDisableExistingScheduleChange(event.target.checked)}
                    />
                  }
                  label={t('repositories.createPlanDialog.disableSchedule')}
                />
              )}
            </>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={isPending}>
          {t('common.buttons.cancel')}
        </Button>
        <Button
          variant="contained"
          onClick={onConfirm}
          disabled={isPending || !repository?.source_directories?.length}
        >
          {isPending
            ? t('repositories.createPlanDialog.creating')
            : t('repositories.createPlanDialog.confirm')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

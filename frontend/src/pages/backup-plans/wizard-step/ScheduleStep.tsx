import { Box, Divider, FormControlLabel, Stack, Switch, TextField, Typography } from '@mui/material'

import PruneSettingsInput from '../../../components/PruneSettingsInput'
import SchedulePicker from '../../../components/SchedulePicker'
import type { BackupPlanWizardStepProps } from './types'

const wizardSwitchRowSx = {
  m: 0,
  alignItems: 'center',
  gap: 1.5,
  '& .MuiSwitch-root': {
    flexShrink: 0,
  },
  '& .MuiFormControlLabel-label': {
    lineHeight: 1.35,
  },
}

const wizardSwitchChildSx = {
  pt: 2,
}

type ScheduleStepProps = Pick<
  BackupPlanWizardStepProps,
  'wizardState' | 'updateState' | 'handlePruneSettingsChange' | 't'
>

export function ScheduleStep({
  wizardState,
  updateState,
  handlePruneSettingsChange,
  t,
}: ScheduleStepProps) {
  return (
    <Stack spacing={3}>
      <Stack spacing={2}>
        <Box>
          <Typography variant="subtitle2" fontWeight={600}>
            {t('backupPlans.wizard.schedule.title')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('backupPlans.wizard.schedule.description')}
          </Typography>
        </Box>
        <FormControlLabel
          sx={wizardSwitchRowSx}
          control={
            <Switch
              checked={wizardState.scheduleEnabled}
              onChange={(event) => updateState({ scheduleEnabled: event.target.checked })}
            />
          }
          label={t('backupPlans.wizard.schedule.enabled')}
        />
        {wizardState.scheduleEnabled && (
          <SchedulePicker
            cronExpression={wizardState.cronExpression}
            timezone={wizardState.timezone}
            onChange={(updates) => updateState(updates)}
            required
            size="medium"
            cronLabel={t('backupPlans.wizard.fields.cronExpression')}
            cronHelperText={t('backupPlans.wizard.schedule.cronHelper')}
            timezoneLabel={t('backupPlans.wizard.fields.timezone')}
          />
        )}
      </Stack>
      <Divider />
      <Stack spacing={2.5}>
        <Box>
          <Typography variant="subtitle2" fontWeight={600}>
            {t('backupPlans.wizard.maintenance.title')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('backupPlans.wizard.maintenance.description')}
          </Typography>
        </Box>

        <Box>
          <FormControlLabel
            sx={wizardSwitchRowSx}
            control={
              <Switch
                checked={wizardState.runPruneAfter}
                onChange={(event) => updateState({ runPruneAfter: event.target.checked })}
              />
            }
            label={t('backupPlans.wizard.maintenance.runPruneAfter')}
          />
          {wizardState.runPruneAfter && (
            <Box sx={wizardSwitchChildSx}>
              <PruneSettingsInput
                values={{
                  keepHourly: wizardState.pruneKeepHourly,
                  keepDaily: wizardState.pruneKeepDaily,
                  keepWeekly: wizardState.pruneKeepWeekly,
                  keepMonthly: wizardState.pruneKeepMonthly,
                  keepQuarterly: wizardState.pruneKeepQuarterly,
                  keepYearly: wizardState.pruneKeepYearly,
                }}
                onChange={handlePruneSettingsChange}
              />
            </Box>
          )}
        </Box>

        <FormControlLabel
          sx={wizardSwitchRowSx}
          control={
            <Switch
              checked={wizardState.runCompactAfter}
              onChange={(event) => updateState({ runCompactAfter: event.target.checked })}
            />
          }
          label={t('backupPlans.wizard.maintenance.runCompactAfter')}
        />

        <Box>
          <FormControlLabel
            sx={wizardSwitchRowSx}
            control={
              <Switch
                checked={wizardState.runCheckAfter}
                onChange={(event) => updateState({ runCheckAfter: event.target.checked })}
              />
            }
            label={t('backupPlans.wizard.maintenance.runCheckAfter')}
          />
          {wizardState.runCheckAfter && (
            <Box sx={wizardSwitchChildSx}>
              <Stack spacing={2}>
                <TextField
                  label={t('backupPlans.wizard.fields.checkMaxDuration')}
                  type="number"
                  value={wizardState.checkMaxDuration}
                  onChange={(event) =>
                    updateState({
                      checkMaxDuration: Math.max(0, Number(event.target.value) || 0),
                    })
                  }
                  helperText={t('backupPlans.wizard.maintenance.checkMaxDurationHelper')}
                  inputProps={{ min: 0 }}
                  fullWidth
                />
                <TextField
                  label={t('backupPlans.wizard.fields.checkExtraFlags')}
                  value={wizardState.checkExtraFlags}
                  onChange={(event) => updateState({ checkExtraFlags: event.target.value })}
                  helperText={t('backupPlans.wizard.maintenance.checkExtraFlagsHelper')}
                  placeholder="--repair --verify-data"
                  inputProps={{ spellCheck: false }}
                  fullWidth
                />
              </Stack>
            </Box>
          )}
        </Box>
      </Stack>
    </Stack>
  )
}

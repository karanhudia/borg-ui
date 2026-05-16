import {
  FormControl,
  FormControlLabel,
  FormLabel,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Tooltip,
} from '@mui/material'

import CompressionSettings from '../../../components/CompressionSettings'
import type { BackupPlanWizardStepProps } from './types'

type SettingsStepProps = Pick<
  BackupPlanWizardStepProps,
  'wizardState' | 'canUseMultiRepository' | 'updateState' | 't'
>

export function SettingsStep({
  wizardState,
  canUseMultiRepository,
  updateState,
  t,
}: SettingsStepProps) {
  return (
    <Stack spacing={3}>
      <TextField
        label={t('backupPlans.wizard.fields.archiveNameTemplate')}
        value={wizardState.archiveNameTemplate}
        onChange={(event) => updateState({ archiveNameTemplate: event.target.value })}
        helperText={t('backupPlans.wizard.settings.archiveNameHelper')}
        fullWidth
      />
      <CompressionSettings
        value={wizardState.compression}
        onChange={(compression) => updateState({ compression })}
      />
      <TextField
        label={t('backupPlans.wizard.fields.extraBorgFlags')}
        value={wizardState.customFlags}
        onChange={(event) => updateState({ customFlags: event.target.value })}
        placeholder="--stats --list"
        helperText={t('backupPlans.wizard.settings.extraBorgFlagsHelper')}
        fullWidth
      />
      <TextField
        label={t('backupPlans.wizard.fields.uploadSpeedLimit')}
        type="number"
        value={wizardState.uploadRatelimitMb}
        onChange={(event) => updateState({ uploadRatelimitMb: event.target.value })}
        helperText={t('backupPlans.wizard.settings.uploadSpeedHelper')}
        fullWidth
      />
      <FormControl>
        <FormLabel>{t('backupPlans.wizard.fields.runRepositories')}</FormLabel>
        <RadioGroup
          value={wizardState.repositoryRunMode}
          onChange={(event) => {
            const mode = event.target.value as 'series' | 'parallel'
            updateState({
              repositoryRunMode: mode,
              maxParallelRepositories: mode === 'parallel' ? 2 : 1,
            })
          }}
        >
          <FormControlLabel
            value="series"
            control={<Radio />}
            label={t('backupPlans.wizard.settings.seriesLabel')}
          />
          <Tooltip
            title={
              canUseMultiRepository
                ? t('backupPlans.wizard.settings.parallelTooltip')
                : t('backupPlans.wizard.settings.parallelRequiresPro')
            }
            placement="right"
          >
            <span>
              <FormControlLabel
                value="parallel"
                control={<Radio />}
                disabled={!canUseMultiRepository}
                label={t('backupPlans.wizard.settings.parallelLabel')}
              />
            </span>
          </Tooltip>
        </RadioGroup>
      </FormControl>
      {wizardState.repositoryRunMode === 'parallel' && (
        <TextField
          label={t('backupPlans.wizard.fields.maxParallelRepositories')}
          type="number"
          value={wizardState.maxParallelRepositories}
          onChange={(event) =>
            updateState({ maxParallelRepositories: Math.max(2, Number(event.target.value)) })
          }
          fullWidth
        />
      )}
    </Stack>
  )
}

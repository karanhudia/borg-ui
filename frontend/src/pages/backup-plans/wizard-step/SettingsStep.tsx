import {
  Box,
  Button,
  FormControl,
  FormControlLabel,
  FormLabel,
  IconButton,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { Plus, Trash2 } from 'lucide-react'

import CompressionSettings from '../../../components/CompressionSettings'
import type { UploadRatelimitSchedulePolicyState } from '../../../utils/backupPlanPayload'
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
  const uploadPolicies = wizardState.uploadRatelimitSchedulePolicies || []
  const updateUploadPolicy = (
    index: number,
    updates: Partial<UploadRatelimitSchedulePolicyState>
  ) => {
    updateState({
      uploadRatelimitSchedulePolicies: uploadPolicies.map((policy, policyIndex) =>
        policyIndex === index ? { ...policy, ...updates } : policy
      ),
    })
  }
  const removeUploadPolicy = (index: number) => {
    updateState({
      uploadRatelimitSchedulePolicies: uploadPolicies.filter(
        (_policy, policyIndex) => policyIndex !== index
      ),
    })
  }
  const addUploadPolicy = () => {
    updateState({
      uploadRatelimitSchedulePolicies: [
        ...uploadPolicies,
        {
          label: t('backupPlans.wizard.settings.daytimePolicyLabel'),
          startTime: '08:00',
          endTime: '18:00',
          uploadRatelimitMb: '',
        },
      ],
    })
  }

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
      <Box
        sx={{
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 1,
          p: 2,
        }}
      >
        <Stack spacing={1.5}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 1,
            }}
          >
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="subtitle2">
                {t('backupPlans.wizard.settings.uploadPoliciesTitle')}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {t('backupPlans.wizard.settings.uploadPoliciesHelper')}
              </Typography>
            </Box>
            <Button
              type="button"
              variant="outlined"
              size="small"
              startIcon={<Plus size={16} />}
              onClick={addUploadPolicy}
            >
              {t('backupPlans.wizard.settings.addUploadPolicy')}
            </Button>
          </Box>

          {uploadPolicies.map((policy, index) => (
            <Box
              key={`${policy.startTime}-${policy.endTime}-${index}`}
              sx={{
                display: 'grid',
                gridTemplateColumns: {
                  xs: '1fr',
                  sm: 'minmax(140px, 1.4fr) minmax(96px, 0.7fr) minmax(96px, 0.7fr) minmax(120px, 0.9fr) auto',
                },
                gap: 1,
                alignItems: 'center',
              }}
            >
              <TextField
                label={t('backupPlans.wizard.settings.policyLabel')}
                value={policy.label}
                onChange={(event) => updateUploadPolicy(index, { label: event.target.value })}
                fullWidth
              />
              <TextField
                label={t('backupPlans.wizard.settings.policyStartTime')}
                type="time"
                value={policy.startTime}
                onChange={(event) => updateUploadPolicy(index, { startTime: event.target.value })}
                InputLabelProps={{ shrink: true }}
                fullWidth
              />
              <TextField
                label={t('backupPlans.wizard.settings.policyEndTime')}
                type="time"
                value={policy.endTime}
                onChange={(event) => updateUploadPolicy(index, { endTime: event.target.value })}
                InputLabelProps={{ shrink: true }}
                fullWidth
              />
              <TextField
                label={t('backupPlans.wizard.settings.policyLimit')}
                type="number"
                value={policy.uploadRatelimitMb}
                onChange={(event) =>
                  updateUploadPolicy(index, { uploadRatelimitMb: event.target.value })
                }
                fullWidth
              />
              <Tooltip title={t('backupPlans.wizard.settings.removeUploadPolicy')}>
                <IconButton
                  type="button"
                  aria-label={t('backupPlans.wizard.settings.removeUploadPolicy')}
                  onClick={() => removeUploadPolicy(index)}
                  size="small"
                >
                  <Trash2 size={16} />
                </IconButton>
              </Tooltip>
            </Box>
          ))}
        </Stack>
      </Box>
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

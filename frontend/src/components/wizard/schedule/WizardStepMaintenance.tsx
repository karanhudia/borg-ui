import React from 'react'
import { useTranslation } from 'react-i18next'
import { Stack, Box, Typography, FormControlLabel, Switch, Alert, Collapse } from '@mui/material'
import PruneSettingsInput, { PruneSettings } from '../../PruneSettingsInput'

interface WizardStepMaintenanceData {
  runPruneAfter: boolean
  runCompactAfter: boolean
  pruneKeepHourly: number
  pruneKeepDaily: number
  pruneKeepWeekly: number
  pruneKeepMonthly: number
  pruneKeepQuarterly: number
  pruneKeepYearly: number
}

interface WizardStepMaintenanceProps {
  data: WizardStepMaintenanceData
  onChange: (updates: Partial<WizardStepMaintenanceData>) => void
}

const WizardStepMaintenance: React.FC<WizardStepMaintenanceProps> = ({ data, onChange }) => {
  const { t } = useTranslation()

  const handlePruneSettingsChange = (values: PruneSettings) => {
    onChange({
      pruneKeepHourly: values.keepHourly,
      pruneKeepDaily: values.keepDaily,
      pruneKeepWeekly: values.keepWeekly,
      pruneKeepMonthly: values.keepMonthly,
      pruneKeepQuarterly: values.keepQuarterly,
      pruneKeepYearly: values.keepYearly,
    })
  }

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h6" fontWeight={600} gutterBottom>
          {t('wizard.scheduleWizard.maintenance.title')}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t('wizard.scheduleWizard.maintenance.subtitle')}
        </Typography>
      </Box>

      <Alert severity="info" sx={{ py: 0.5 }}>
        {t('wizard.scheduleWizard.maintenance.info')}
      </Alert>

      <Box>
        <FormControlLabel
          control={
            <Switch
              checked={data.runPruneAfter}
              onChange={(e) => onChange({ runPruneAfter: e.target.checked })}
            />
          }
          label={
            <Box>
              <Typography variant="body2" fontWeight={600}>
                {t('wizard.scheduleWizard.maintenance.pruneAfterBackup')}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {t('wizard.scheduleWizard.maintenance.pruneAfterBackupDesc')}
              </Typography>
            </Box>
          }
        />

        <Collapse in={data.runPruneAfter}>
          <Box sx={{ pl: 4, pt: 2 }}>
            <PruneSettingsInput
              values={{
                keepHourly: data.pruneKeepHourly,
                keepDaily: data.pruneKeepDaily,
                keepWeekly: data.pruneKeepWeekly,
                keepMonthly: data.pruneKeepMonthly,
                keepQuarterly: data.pruneKeepQuarterly,
                keepYearly: data.pruneKeepYearly,
              }}
              onChange={handlePruneSettingsChange}
            />
            <Alert severity="warning" sx={{ mt: 2, py: 0.5 }}>
              <Typography variant="caption">
                <strong>Caution:</strong> {t('wizard.scheduleWizard.maintenance.pruneCaution')}
              </Typography>
            </Alert>
          </Box>
        </Collapse>
      </Box>

      <Box>
        <FormControlLabel
          control={
            <Switch
              checked={data.runCompactAfter}
              onChange={(e) => onChange({ runCompactAfter: e.target.checked })}
            />
          }
          label={
            <Box>
              <Typography variant="body2" fontWeight={600}>
                {t('wizard.scheduleWizard.maintenance.compactAfterPrune')}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {t('wizard.scheduleWizard.maintenance.compactAfterPruneDesc')}
              </Typography>
            </Box>
          }
        />

        {data.runCompactAfter && (
          <Alert severity="info" sx={{ ml: 4, mt: 1, py: 0.5 }}>
            {t('wizard.scheduleWizard.maintenance.compactInfo')}
          </Alert>
        )}
      </Box>
    </Stack>
  )
}

export default WizardStepMaintenance

import React from 'react'
import { useTranslation } from 'react-i18next'
import {
  Stack,
  Box,
  Typography,
  FormControlLabel,
  Switch,
  Alert,
  Collapse,
  Tooltip,
} from '@mui/material'
import { Info } from 'lucide-react'
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
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
          <Typography variant="h6" fontWeight={600}>
            {t('wizard.scheduleWizard.maintenance.title')}
          </Typography>
          <Tooltip title={t('wizard.scheduleWizard.maintenance.info')} arrow placement="right">
            <Box
              component="span"
              tabIndex={0}
              aria-label={t('wizard.scheduleWizard.maintenance.info')}
              sx={{
                display: 'inline-flex',
                cursor: 'help',
                color: 'text.disabled',
                '&:hover': { color: 'text.secondary' },
                '&:focus-visible': {
                  outline: '2px solid',
                  outlineColor: 'primary.main',
                  borderRadius: 0.5,
                },
              }}
            >
              <Info size={15} />
            </Box>
          </Tooltip>
        </Box>
        <Typography variant="body2" color="text.secondary">
          {t('wizard.scheduleWizard.maintenance.subtitle')}
        </Typography>
      </Box>

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
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
              <Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                  <Typography variant="body2" fontWeight={600}>
                    {t('wizard.scheduleWizard.maintenance.compactAfterPrune')}
                  </Typography>
                  <Tooltip
                    title={t('wizard.scheduleWizard.maintenance.compactInfo')}
                    arrow
                    placement="right"
                  >
                    <Box
                      component="span"
                      tabIndex={0}
                      aria-label={t('wizard.scheduleWizard.maintenance.compactInfo')}
                      sx={{
                        display: 'inline-flex',
                        cursor: 'help',
                        color: 'text.disabled',
                        '&:hover': { color: 'text.secondary' },
                        '&:focus-visible': {
                          outline: '2px solid',
                          outlineColor: 'primary.main',
                          borderRadius: 0.5,
                        },
                      }}
                    >
                      <Info size={14} />
                    </Box>
                  </Tooltip>
                </Box>
                <Typography variant="caption" color="text.secondary">
                  {t('wizard.scheduleWizard.maintenance.compactAfterPruneDesc')}
                </Typography>
              </Box>
            </Box>
          }
        />
      </Box>
    </Stack>
  )
}

export default WizardStepMaintenance

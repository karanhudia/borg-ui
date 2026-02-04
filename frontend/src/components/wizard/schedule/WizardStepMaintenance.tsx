import React from 'react'
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
          Maintenance Options
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Run prune and compact after backups to manage disk space.
        </Typography>
      </Box>

      <Alert severity="info" sx={{ py: 0.5 }}>
        <strong>Prune</strong> removes old archives. <strong>Compact</strong> reclaims disk space.
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
                Run prune after backup
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Remove old archives based on retention policy
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
                <strong>Caution:</strong> Pruning permanently deletes old backups.
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
                Run compact after prune
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Reclaim disk space by freeing segments
              </Typography>
            </Box>
          }
        />

        {data.runCompactAfter && (
          <Alert severity="info" sx={{ ml: 4, mt: 1, py: 0.5 }}>
            Compact reclaims disk space after prune. May take time on large repositories.
          </Alert>
        )}
      </Box>
    </Stack>
  )
}

export default WizardStepMaintenance

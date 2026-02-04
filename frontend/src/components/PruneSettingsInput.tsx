import React from 'react'
import { Box, TextField } from '@mui/material'

export interface PruneSettings {
  keepHourly: number
  keepDaily: number
  keepWeekly: number
  keepMonthly: number
  keepQuarterly: number
  keepYearly: number
}

interface PruneSettingsInputProps {
  values: PruneSettings
  onChange: (values: PruneSettings) => void
  disabled?: boolean
}

const PruneSettingsInput: React.FC<PruneSettingsInputProps> = ({
  values,
  onChange,
  disabled = false,
}) => {
  const handleChange = (field: keyof PruneSettings, value: string) => {
    const parsedValue = parseInt(value, 10)
    const finalValue = isNaN(parsedValue) ? 0 : Math.max(0, parsedValue)
    onChange({
      ...values,
      [field]: finalValue,
    })
  }

  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 2 }}>
      <TextField
        label="Keep Hourly"
        type="number"
        value={values.keepHourly}
        onChange={(e) => handleChange('keepHourly', e.target.value)}
        inputProps={{ min: 0 }}
        size="small"
        helperText="Hourly backups to keep (0 = disabled)"
        disabled={disabled}
      />
      <TextField
        label="Keep Daily"
        type="number"
        value={values.keepDaily}
        onChange={(e) => handleChange('keepDaily', e.target.value)}
        inputProps={{ min: 0 }}
        size="small"
        helperText="Daily backups to keep"
        disabled={disabled}
      />
      <TextField
        label="Keep Weekly"
        type="number"
        value={values.keepWeekly}
        onChange={(e) => handleChange('keepWeekly', e.target.value)}
        inputProps={{ min: 0 }}
        size="small"
        helperText="Weekly backups to keep"
        disabled={disabled}
      />
      <TextField
        label="Keep Monthly"
        type="number"
        value={values.keepMonthly}
        onChange={(e) => handleChange('keepMonthly', e.target.value)}
        inputProps={{ min: 0 }}
        size="small"
        helperText="Monthly backups to keep"
        disabled={disabled}
      />
      <TextField
        label="Keep Quarterly"
        type="number"
        value={values.keepQuarterly}
        onChange={(e) => handleChange('keepQuarterly', e.target.value)}
        inputProps={{ min: 0 }}
        size="small"
        helperText="Quarterly backups to keep (0 = disabled)"
        disabled={disabled}
      />
      <TextField
        label="Keep Yearly"
        type="number"
        value={values.keepYearly}
        onChange={(e) => handleChange('keepYearly', e.target.value)}
        inputProps={{ min: 0 }}
        size="small"
        helperText="Yearly backups to keep"
        disabled={disabled}
      />
    </Box>
  )
}

export default PruneSettingsInput

import React from 'react'
import { useTranslation } from 'react-i18next'
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
  const { t } = useTranslation()
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
        label={t('pruneSettings.keepHourly')}
        type="number"
        value={values.keepHourly}
        onChange={(e) => handleChange('keepHourly', e.target.value)}
        inputProps={{ min: 0 }}
        size="small"
        helperText={t('pruneSettings.keepHourlyHint')}
        disabled={disabled}
      />
      <TextField
        label={t('pruneSettings.keepDaily')}
        type="number"
        value={values.keepDaily}
        onChange={(e) => handleChange('keepDaily', e.target.value)}
        inputProps={{ min: 0 }}
        size="small"
        helperText={t('pruneSettings.keepDailyHint')}
        disabled={disabled}
      />
      <TextField
        label={t('pruneSettings.keepWeekly')}
        type="number"
        value={values.keepWeekly}
        onChange={(e) => handleChange('keepWeekly', e.target.value)}
        inputProps={{ min: 0 }}
        size="small"
        helperText={t('pruneSettings.keepWeeklyHint')}
        disabled={disabled}
      />
      <TextField
        label={t('pruneSettings.keepMonthly')}
        type="number"
        value={values.keepMonthly}
        onChange={(e) => handleChange('keepMonthly', e.target.value)}
        inputProps={{ min: 0 }}
        size="small"
        helperText={t('pruneSettings.keepMonthlyHint')}
        disabled={disabled}
      />
      <TextField
        label={t('pruneSettings.keepQuarterly')}
        type="number"
        value={values.keepQuarterly}
        onChange={(e) => handleChange('keepQuarterly', e.target.value)}
        inputProps={{ min: 0 }}
        size="small"
        helperText={t('pruneSettings.keepQuarterlyHint')}
        disabled={disabled}
      />
      <TextField
        label={t('pruneSettings.keepYearly')}
        type="number"
        value={values.keepYearly}
        onChange={(e) => handleChange('keepYearly', e.target.value)}
        inputProps={{ min: 0 }}
        size="small"
        helperText={t('pruneSettings.keepYearlyHint')}
        disabled={disabled}
      />
    </Box>
  )
}

export default PruneSettingsInput

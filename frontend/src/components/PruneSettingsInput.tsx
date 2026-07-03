import React from 'react'
import { useTranslation } from 'react-i18next'
import { Box, TextField } from '@mui/material'

export interface PruneSettings {
  keepWithin: string
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
  const handleCountChange = (field: Exclude<keyof PruneSettings, 'keepWithin'>, value: string) => {
    const parsedValue = parseInt(value, 10)
    const finalValue = isNaN(parsedValue) ? 0 : Math.max(0, parsedValue)
    onChange({
      ...values,
      [field]: finalValue,
    })
  }
  const handleKeepWithinChange = (value: string) => {
    onChange({
      ...values,
      keepWithin: value,
    })
  }

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)' },
        gap: 2,
      }}
    >
      <TextField
        label={t('pruneSettings.keepWithin')}
        value={values.keepWithin}
        onChange={(e) => handleKeepWithinChange(e.target.value)}
        size="small"
        helperText={t('pruneSettings.keepWithinHint')}
        disabled={disabled}
        placeholder={t('pruneSettings.keepWithinPlaceholder')}
        sx={{ gridColumn: { xs: 'auto', sm: '1 / -1' } }}
      />
      <TextField
        label={t('pruneSettings.keepHourly')}
        type="number"
        value={values.keepHourly}
        onChange={(e) => handleCountChange('keepHourly', e.target.value)}
        inputProps={{ min: 0 }}
        size="small"
        helperText={t('pruneSettings.keepHourlyHint')}
        disabled={disabled}
      />
      <TextField
        label={t('pruneSettings.keepDaily')}
        type="number"
        value={values.keepDaily}
        onChange={(e) => handleCountChange('keepDaily', e.target.value)}
        inputProps={{ min: 0 }}
        size="small"
        helperText={t('pruneSettings.keepDailyHint')}
        disabled={disabled}
      />
      <TextField
        label={t('pruneSettings.keepWeekly')}
        type="number"
        value={values.keepWeekly}
        onChange={(e) => handleCountChange('keepWeekly', e.target.value)}
        inputProps={{ min: 0 }}
        size="small"
        helperText={t('pruneSettings.keepWeeklyHint')}
        disabled={disabled}
      />
      <TextField
        label={t('pruneSettings.keepMonthly')}
        type="number"
        value={values.keepMonthly}
        onChange={(e) => handleCountChange('keepMonthly', e.target.value)}
        inputProps={{ min: 0 }}
        size="small"
        helperText={t('pruneSettings.keepMonthlyHint')}
        disabled={disabled}
      />
      <TextField
        label={t('pruneSettings.keepQuarterly')}
        type="number"
        value={values.keepQuarterly}
        onChange={(e) => handleCountChange('keepQuarterly', e.target.value)}
        inputProps={{ min: 0 }}
        size="small"
        helperText={t('pruneSettings.keepQuarterlyHint')}
        disabled={disabled}
      />
      <TextField
        label={t('pruneSettings.keepYearly')}
        type="number"
        value={values.keepYearly}
        onChange={(e) => handleCountChange('keepYearly', e.target.value)}
        inputProps={{ min: 0 }}
        size="small"
        helperText={t('pruneSettings.keepYearlyHint')}
        disabled={disabled}
      />
    </Box>
  )
}

export default PruneSettingsInput

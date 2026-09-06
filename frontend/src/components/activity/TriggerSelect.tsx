import { MenuItem, Select } from '@mui/material'
import { useTranslation } from 'react-i18next'
import type { OperationTrigger } from '../../types/operations'
import { FILTER_SELECT_SX } from './filterSelectSx'

const TRIGGERS: OperationTrigger[] = [
  'manual',
  'schedule',
  'plan',
  'import',
  'followup',
  'reconcile',
  'retry',
]

interface TriggerSelectProps {
  value: string
  onChange: (value: string) => void
}

export default function TriggerSelect({ value, onChange }: TriggerSelectProps) {
  const { t } = useTranslation()
  return (
    <Select
      size="small"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      inputProps={{ 'aria-label': t('activity.filterTrigger') }}
      sx={FILTER_SELECT_SX}
    >
      <MenuItem value="all">{t('activity.allTriggers')}</MenuItem>
      {TRIGGERS.map((trigger) => (
        <MenuItem key={trigger} value={trigger}>
          {t(`activity.triggers.${trigger}`)}
        </MenuItem>
      ))}
    </Select>
  )
}

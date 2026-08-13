import { Alert, type AlertColor, Chip, type SxProps, type Theme } from '@mui/material'
import { CalendarCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { SourceType } from '../../types'
import RichSelect, { type RichSelectOption } from './RichSelect'

export interface BackupPlanSummary {
  id: number
  name: string
  source_type: SourceType
  repository_count: number
  schedule_enabled: boolean
}

interface BackupPlanSelectProps {
  value: number | ''
  onChange: (id: number) => void
  plans: BackupPlanSummary[]
  /** Label shown both as the floating InputLabel and the notched outline. */
  label: string
  /** Used when plans is empty (unless hideEmptyAlert is true). */
  emptyMessage: string
  /** Optional placeholder rendered when value is empty. */
  placeholder?: string
  /** Explicit ID for the InputLabel ↔ Select binding. Generated if omitted. */
  labelId?: string
  /** Explicit ID for the Select element. */
  selectId?: string
  disabled?: boolean
  /** Skip the built-in empty-state Alert (caller handles empty state). */
  hideEmptyAlert?: boolean
  emptySeverity?: AlertColor
  sx?: SxProps<Theme>
  formatSecondary?: (plan: BackupPlanSummary) => string
  getIndicatorLabel?: (plan: BackupPlanSummary) => string | undefined
}

export default function BackupPlanSelect({
  value,
  onChange,
  plans,
  label,
  emptyMessage,
  placeholder,
  labelId,
  selectId,
  disabled,
  hideEmptyAlert,
  emptySeverity = 'info',
  sx,
  formatSecondary,
  getIndicatorLabel,
}: BackupPlanSelectProps) {
  const { t } = useTranslation()

  if (!Array.isArray(plans) || plans.length === 0) {
    if (hideEmptyAlert) return null
    return <Alert severity={emptySeverity}>{emptyMessage}</Alert>
  }

  const options: RichSelectOption[] = plans.map((plan) => {
    const indicatorLabel = getIndicatorLabel
      ? getIndicatorLabel(plan)
      : getDefaultIndicatorLabel(plan, t)

    return {
      value: String(plan.id),
      icon: <CalendarCheck size={16} />,
      primary: plan.name,
      secondary: formatSecondary?.(plan) ?? formatBackupPlanSecondary(plan, t),
      indicator: indicatorLabel ? (
        <Chip
          size="small"
          label={indicatorLabel}
          variant="outlined"
          sx={{ height: 20, fontSize: '0.65rem', flexShrink: 0 }}
        />
      ) : undefined,
    }
  })

  return (
    <RichSelect
      value={value === '' ? '' : String(value)}
      onChange={(next) => {
        if (next) onChange(Number(next))
      }}
      options={options}
      label={label}
      labelId={labelId}
      selectId={selectId}
      disabled={disabled}
      placeholder={placeholder}
      sx={sx}
    />
  )
}

function formatBackupPlanSecondary(
  plan: BackupPlanSummary,
  t: (key: string, options?: Record<string, unknown>) => string
): string {
  return `${formatSourceType(plan.source_type, t)} · ${formatRepositoryCount(plan.repository_count, t)}`
}

function formatSourceType(sourceType: SourceType, t: (key: string) => string): string {
  if (sourceType === 'remote') return t('backupPlans.select.source.remote')
  if (sourceType === 'agent') return t('backupPlans.select.source.agent')
  if (sourceType === 'mixed') return t('backupPlans.select.source.mixed')
  return t('backupPlans.select.source.local')
}

function formatRepositoryCount(
  count: number,
  t: (key: string, options?: Record<string, unknown>) => string
): string {
  return t('backupPlans.select.repositories', { count })
}

function getDefaultIndicatorLabel(plan: BackupPlanSummary, t: (key: string) => string): string {
  return plan.schedule_enabled ? t('backupPlans.select.scheduled') : t('backupPlans.select.manual')
}

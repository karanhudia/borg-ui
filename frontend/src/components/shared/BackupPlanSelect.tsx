import {
  Alert,
  type AlertColor,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  type SxProps,
  type Theme,
  Typography,
} from '@mui/material'
import { CalendarCheck } from 'lucide-react'
import type { SourceType } from '../../types'
import RichSelectRow from './RichSelectRow'

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

let autoIdCounter = 0

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
  formatSecondary = formatBackupPlanSecondary,
  getIndicatorLabel = getDefaultIndicatorLabel,
}: BackupPlanSelectProps) {
  if (!Array.isArray(plans) || plans.length === 0) {
    if (hideEmptyAlert) return null
    return <Alert severity={emptySeverity}>{emptyMessage}</Alert>
  }

  const resolvedLabelId = labelId ?? `backup-plan-select-${++autoIdCounter}`
  const selectedValue = value === '' ? '' : String(value)

  return (
    <FormControl fullWidth disabled={disabled} sx={sx}>
      <InputLabel id={resolvedLabelId} shrink={Boolean(placeholder) || undefined}>
        {label}
      </InputLabel>
      <Select
        labelId={resolvedLabelId}
        id={selectId}
        value={selectedValue}
        label={label}
        displayEmpty={Boolean(placeholder)}
        onChange={(event) => {
          const next = event.target.value
          if (next) onChange(Number(next))
        }}
        renderValue={(selected) => {
          if (selected === '' && placeholder) {
            return (
              <Typography variant="body2" color="text.secondary" noWrap>
                {placeholder}
              </Typography>
            )
          }

          const plan = plans.find((item) => String(item.id) === selected)
          if (!plan) return null
          return renderBackupPlanRow(plan, formatSecondary, getIndicatorLabel)
        }}
        // Match the fixed rich-select trigger height used by SSH connections,
        // managed agents, rclone remotes, and repository destinations.
        sx={{
          height: 56,
          '& .MuiSelect-select': {
            height: 56,
            boxSizing: 'border-box',
            display: 'flex',
            alignItems: 'center',
          },
        }}
      >
        {placeholder && (
          <MenuItem value="" disabled>
            <Typography variant="body2" color="text.secondary">
              {placeholder}
            </Typography>
          </MenuItem>
        )}
        {plans.map((plan) => (
          <MenuItem key={plan.id} value={String(plan.id)} sx={{ py: 1 }}>
            {renderBackupPlanRow(plan, formatSecondary, getIndicatorLabel)}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  )
}

function renderBackupPlanRow(
  plan: BackupPlanSummary,
  formatSecondary: (plan: BackupPlanSummary) => string,
  getIndicatorLabel: (plan: BackupPlanSummary) => string | undefined
) {
  const indicatorLabel = getIndicatorLabel(plan)

  return (
    <RichSelectRow
      icon={<CalendarCheck size={16} />}
      primary={plan.name}
      secondary={formatSecondary(plan)}
      indicator={
        indicatorLabel ? (
          <Chip
            size="small"
            label={indicatorLabel}
            variant="outlined"
            sx={{ height: 20, fontSize: '0.65rem', flexShrink: 0 }}
          />
        ) : undefined
      }
    />
  )
}

function formatBackupPlanSecondary(plan: BackupPlanSummary): string {
  return `${formatSourceType(plan.source_type)} · ${formatRepositoryCount(plan.repository_count)}`
}

function formatSourceType(sourceType: SourceType): string {
  if (sourceType === 'remote') return 'Remote source'
  if (sourceType === 'agent') return 'Managed agent'
  if (sourceType === 'mixed') return 'Multiple sources'
  return 'Local source'
}

function formatRepositoryCount(count: number): string {
  return count === 1 ? '1 repository' : `${count} repositories`
}

function getDefaultIndicatorLabel(plan: BackupPlanSummary): string {
  return plan.schedule_enabled ? 'Scheduled' : 'Manual'
}

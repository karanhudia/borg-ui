import { Alert, type AlertColor, Chip } from '@mui/material'
import { Cloud } from 'lucide-react'
import RichSelect, { type RichSelectOption } from './RichSelect'

export interface RcloneRemoteSummary {
  id: number
  name: string
  provider: string
  last_test_status?: string | null
}

interface RcloneRemoteSelectProps {
  value: number | ''
  onChange: (id: number) => void
  remotes: RcloneRemoteSummary[]
  /** Label shown both as the floating InputLabel and the notched outline. */
  label: string
  /** Used when remotes is empty (unless hideEmptyAlert is true). */
  emptyMessage: string
  /** Explicit ID for the InputLabel ↔ Select binding. Generated if omitted. */
  labelId?: string
  /** Explicit ID for the Select element. */
  selectId?: string
  disabled?: boolean
  /** Skip the built-in empty-state Alert (caller handles empty state). */
  hideEmptyAlert?: boolean
  emptySeverity?: AlertColor
}

export default function RcloneRemoteSelect({
  value,
  onChange,
  remotes,
  label,
  emptyMessage,
  labelId,
  selectId,
  disabled,
  hideEmptyAlert,
  emptySeverity = 'info',
}: RcloneRemoteSelectProps) {
  if (!Array.isArray(remotes) || remotes.length === 0) {
    if (hideEmptyAlert) return null
    return <Alert severity={emptySeverity}>{emptyMessage}</Alert>
  }

  const options: RichSelectOption[] = remotes.map((remote) => ({
    value: String(remote.id),
    icon: <Cloud size={16} />,
    primary: remote.name,
    secondary: remote.last_test_status || undefined,
    indicator: (
      <Chip
        size="small"
        label={remote.provider}
        variant="outlined"
        sx={{ height: 20, fontSize: '0.65rem', flexShrink: 0 }}
      />
    ),
  }))

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
    />
  )
}

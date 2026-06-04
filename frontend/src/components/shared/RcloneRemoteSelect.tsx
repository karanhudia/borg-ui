import {
  Alert,
  type AlertColor,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
} from '@mui/material'
import { Cloud } from 'lucide-react'
import RichSelectRow from './RichSelectRow'

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

let autoIdCounter = 0

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

  const resolvedLabelId = labelId ?? `rclone-remote-select-${++autoIdCounter}`

  return (
    <FormControl fullWidth disabled={disabled}>
      <InputLabel id={resolvedLabelId}>{label}</InputLabel>
      <Select
        labelId={resolvedLabelId}
        id={selectId}
        value={value === '' ? '' : String(value)}
        label={label}
        onChange={(event) => {
          const next = event.target.value
          if (next) onChange(Number(next))
        }}
        renderValue={(selected) => {
          const remote = remotes.find((item) => String(item.id) === selected)
          if (!remote) return null
          return renderRcloneRemoteRow(remote)
        }}
        // Match the rich dropdown controls used by SSH connections, managed
        // agents, and repository destinations.
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
        {remotes.map((remote) => (
          <MenuItem key={remote.id} value={String(remote.id)} sx={{ py: 1 }}>
            {renderRcloneRemoteRow(remote)}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  )
}

function renderRcloneRemoteRow(remote: RcloneRemoteSummary) {
  return (
    <RichSelectRow
      icon={<Cloud size={16} />}
      primary={remote.name}
      secondary={remote.last_test_status || undefined}
      indicator={
        <Chip
          size="small"
          label={remote.provider}
          variant="outlined"
          sx={{ height: 20, fontSize: '0.65rem', flexShrink: 0 }}
        />
      }
    />
  )
}

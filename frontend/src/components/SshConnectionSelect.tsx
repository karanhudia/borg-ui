import { Alert, Box, FormControl, InputLabel, MenuItem, Select } from '@mui/material'
import { Cloud } from 'lucide-react'
import RichSelectRow from './shared/RichSelectRow'

export interface SshConnectionSummary {
  id: number
  host: string
  username: string
  port: number
  ssh_key_id?: number
  default_path?: string | null
  mount_point?: string | null
  status: string
}

interface SshConnectionSelectProps {
  value: number | ''
  onChange: (id: number) => void
  connections: SshConnectionSummary[]
  /** Label shown both as the floating InputLabel and the notched outline. */
  label: string
  /** Used when connections is empty (unless hideEmptyAlert is true). */
  emptyMessage: string
  /** Explicit ID for the InputLabel ↔ Select binding. Generated if omitted. */
  labelId?: string
  disabled?: boolean
  /** Skip the built-in empty-state Alert (caller handles empty state). */
  hideEmptyAlert?: boolean
  /** Tooltip on the status dot when the connection is connected. */
  connectedTooltip?: string
}

let autoIdCounter = 0

export default function SshConnectionSelect({
  value,
  onChange,
  connections,
  label,
  emptyMessage,
  labelId,
  disabled,
  hideEmptyAlert,
  connectedTooltip,
}: SshConnectionSelectProps) {
  if (!Array.isArray(connections) || connections.length === 0) {
    if (hideEmptyAlert) return null
    return <Alert severity="warning">{emptyMessage}</Alert>
  }

  const resolvedLabelId = labelId ?? `ssh-connection-select-${++autoIdCounter}`

  return (
    <FormControl fullWidth disabled={disabled}>
      <InputLabel id={resolvedLabelId}>{label}</InputLabel>
      <Select
        labelId={resolvedLabelId}
        value={value === '' ? '' : String(value)}
        label={label}
        onChange={(event) => {
          const next = event.target.value
          if (next) onChange(Number(next))
        }}
        // Force a fixed 56px trigger height on the outlined wrapper AND the
        // inner content area. Without both, the empty state collapses to the
        // MuiSelect-select default min-height (~23px) instead of the standard
        // outlined input height.
        sx={{
          '& .MuiOutlinedInput-root': { height: 56 },
          '& .MuiSelect-select': {
            height: 56,
            boxSizing: 'border-box',
            display: 'flex',
            alignItems: 'center',
          },
        }}
      >
        {connections.map((conn) => (
          <MenuItem key={conn.id} value={String(conn.id)} sx={{ py: 1 }}>
            <RichSelectRow
              icon={<Cloud size={16} />}
              primary={`${conn.username}@${conn.host}`}
              secondary={formatSecondary(conn)}
              indicator={
                conn.status === 'connected' ? (
                  <Box title={connectedTooltip} sx={{ display: 'flex' }}>
                    <Box
                      sx={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        bgcolor: 'success.main',
                        flexShrink: 0,
                      }}
                    />
                  </Box>
                ) : undefined
              }
            />
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  )
}

function formatSecondary(conn: SshConnectionSummary): string {
  const detail = conn.mount_point || conn.default_path
  return detail ? `Port ${conn.port} • ${detail}` : `Port ${conn.port}`
}

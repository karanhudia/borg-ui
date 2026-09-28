import { Alert, Box } from '@mui/material'
import { Cloud } from 'lucide-react'
import RichSelect, { type RichSelectOption } from './RichSelect'

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

  const options: RichSelectOption[] = connections.map((conn) => ({
    value: String(conn.id),
    icon: <Cloud size={16} />,
    primary: `${conn.username}@${conn.host}`,
    secondary: formatSecondary(conn),
    indicator:
      conn.status === 'connected' ? (
        <Box title={connectedTooltip} sx={{ display: 'flex' }}>
          <StatusDot />
        </Box>
      ) : undefined,
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
      disabled={disabled}
    />
  )
}

function StatusDot() {
  return (
    <Box
      sx={{
        width: 8,
        height: 8,
        borderRadius: '50%',
        bgcolor: 'success.main',
        flexShrink: 0,
      }}
    />
  )
}

function formatSecondary(conn: SshConnectionSummary): string {
  const detail = conn.mount_point || conn.default_path
  return detail ? `Port ${conn.port} • ${detail}` : `Port ${conn.port}`
}

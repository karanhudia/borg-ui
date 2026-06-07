import { Alert, Box } from '@mui/material'
import { Laptop } from 'lucide-react'
import RichSelect, { type RichSelectOption } from './RichSelect'

export interface ManagedAgentSummary {
  id: number
  name: string
  hostname?: string | null
  status: string
}

interface ManagedAgentSelectProps {
  value: number | ''
  onChange: (id: number) => void
  agents: ManagedAgentSummary[]
  /** Label shown both as the floating InputLabel and the notched outline. */
  label: string
  /** Used when agents is empty (unless hideEmptyAlert is true). */
  emptyMessage: string
  /** Explicit ID for the InputLabel ↔ Select binding. Generated if omitted. */
  labelId?: string
  disabled?: boolean
  /** Skip the built-in empty-state Alert (caller handles empty state). */
  hideEmptyAlert?: boolean
  /** Tooltip on the status dot when the agent is online. */
  connectedTooltip?: string
}

export default function ManagedAgentSelect({
  value,
  onChange,
  agents,
  label,
  emptyMessage,
  labelId,
  disabled,
  hideEmptyAlert,
  connectedTooltip,
}: ManagedAgentSelectProps) {
  if (!Array.isArray(agents) || agents.length === 0) {
    if (hideEmptyAlert) return null
    return <Alert severity="warning">{emptyMessage}</Alert>
  }

  const options: RichSelectOption[] = agents.map((agent) => ({
    value: String(agent.id),
    icon: <Laptop size={16} />,
    primary: agent.hostname || agent.name,
    secondary: formatSecondary(agent),
    indicator:
      agent.status === 'online' ? (
        <Box title={connectedTooltip} sx={{ display: 'flex' }}>
          <StatusDot color="success.main" />
        </Box>
      ) : (
        <StatusDot color="text.disabled" />
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
      disabled={disabled}
    />
  )
}

function StatusDot({ color }: { color: string }) {
  return (
    <Box
      sx={{
        width: 8,
        height: 8,
        borderRadius: '50%',
        bgcolor: color,
        flexShrink: 0,
      }}
    />
  )
}

function formatSecondary(agent: ManagedAgentSummary): string {
  const metaSecondary = agent.hostname && agent.name !== agent.hostname ? agent.name : undefined
  return [metaSecondary, agent.status].filter(Boolean).join(' · ')
}

import { Alert, Box, FormControl, InputLabel, MenuItem, Select } from '@mui/material'
import { Laptop } from 'lucide-react'
import RichSelectRow from './RichSelectRow'

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

let autoIdCounter = 0

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

  const resolvedLabelId = labelId ?? `managed-agent-select-${++autoIdCounter}`

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
        {agents.map((agent) => (
          <MenuItem key={agent.id} value={String(agent.id)} sx={{ py: 1 }}>
            <RichSelectRow
              icon={<Laptop size={16} />}
              primary={agent.hostname || agent.name}
              secondary={formatSecondary(agent)}
              indicator={
                agent.status === 'online' ? (
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
                ) : (
                  <Box
                    sx={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      bgcolor: 'text.disabled',
                      flexShrink: 0,
                    }}
                  />
                )
              }
            />
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  )
}

function formatSecondary(agent: ManagedAgentSummary): string {
  const metaSecondary = agent.hostname && agent.name !== agent.hostname ? agent.name : undefined
  return [metaSecondary, agent.status].filter(Boolean).join(' · ')
}

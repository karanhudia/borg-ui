import type { ReactNode } from 'react'
import { FormControl, InputLabel, MenuItem, Select } from '@mui/material'
import RichSelectRow from './shared/RichSelectRow'

export interface DestinationOption {
  key: string
  icon: ReactNode
  label: string
  description: string
  disabled?: boolean
}

interface DestinationSelectProps {
  value: string
  onChange: (key: string) => void
  destinations: DestinationOption[]
  /** Label shown both as the floating InputLabel and the notched outline. */
  label: string
  /** Explicit ID for the InputLabel ↔ Select binding. Generated if omitted. */
  labelId?: string
  disabled?: boolean
}

let autoIdCounter = 0

export default function DestinationSelect({
  value,
  onChange,
  destinations,
  label,
  labelId,
  disabled,
}: DestinationSelectProps) {
  const resolvedLabelId = labelId ?? `destination-select-${++autoIdCounter}`

  return (
    <FormControl fullWidth disabled={disabled}>
      <InputLabel id={resolvedLabelId}>{label}</InputLabel>
      <Select
        labelId={resolvedLabelId}
        value={value}
        label={label}
        onChange={(event) => onChange(event.target.value)}
        // Force a fixed 56px trigger height on the outlined wrapper AND the
        // inner content area. Without both, the rich row collapses to the
        // MuiSelect-select default min-height (~23px) instead of the standard
        // outlined input height. Same trick as SshConnectionSelect and
        // ManagedAgentSelect.
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
        {destinations.map((dest) => (
          <MenuItem key={dest.key} value={dest.key} disabled={dest.disabled} sx={{ py: 1 }}>
            <RichSelectRow icon={dest.icon} primary={dest.label} secondary={dest.description} />
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  )
}

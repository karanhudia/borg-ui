import type { ReactNode } from 'react'
import RichSelect, { type RichSelectOption } from './RichSelect'

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

export default function DestinationSelect({
  value,
  onChange,
  destinations,
  label,
  labelId,
  disabled,
}: DestinationSelectProps) {
  const options: RichSelectOption[] = destinations.map((dest) => ({
    value: dest.key,
    icon: dest.icon,
    primary: dest.label,
    secondary: dest.description,
    disabled: dest.disabled,
  }))

  return (
    <RichSelect
      value={value}
      onChange={onChange}
      options={options}
      label={label}
      labelId={labelId}
      disabled={disabled}
    />
  )
}

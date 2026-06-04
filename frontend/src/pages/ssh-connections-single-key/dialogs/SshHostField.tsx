import { TextField } from '@mui/material'

interface SshHostFieldProps {
  label: string
  value: string
  placeholder: string
  hostError?: string
  onHostChange: (value: string) => void
}

export function SshHostField({
  label,
  value,
  placeholder,
  hostError,
  onHostChange,
}: SshHostFieldProps) {
  return (
    <TextField
      label={label}
      fullWidth
      value={value}
      onChange={(event) => onHostChange(event.target.value)}
      placeholder={placeholder}
      error={Boolean(hostError)}
      helperText={hostError}
      InputLabelProps={{ shrink: true }}
    />
  )
}

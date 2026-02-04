import React from 'react'
import { TextField, InputAdornment } from '@mui/material'
import CronBuilderDialog from './CronBuilderDialog'

interface CronExpressionInputProps {
  value: string
  onChange: (cron: string) => void
  label?: string
  helperText?: string
  required?: boolean
  disabled?: boolean
  size?: 'small' | 'medium'
}

const CronExpressionInput: React.FC<CronExpressionInputProps> = ({
  value,
  onChange,
  label = 'Schedule',
  helperText,
  required = false,
  disabled = false,
  size = 'medium',
}) => {
  return (
    <TextField
      label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      required={required}
      disabled={disabled}
      fullWidth
      size={size}
      placeholder="0 2 * * *"
      helperText={helperText}
      InputProps={{
        sx: {
          fontFamily: 'monospace',
          fontSize: size === 'medium' ? '1.1rem' : '0.875rem',
          letterSpacing: '0.1em',
        },
        endAdornment: (
          <InputAdornment position="end">
            <CronBuilderDialog value={value} onChange={onChange} dialogTitle="Configure Schedule" />
          </InputAdornment>
        ),
      }}
      InputLabelProps={{
        sx: { fontSize: size === 'medium' ? '1.1rem' : '0.875rem' },
      }}
    />
  )
}

export default CronExpressionInput

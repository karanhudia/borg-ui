import React, { useMemo } from 'react'
import { TextField, Alert, Box } from '@mui/material'

interface ArchiveNameTemplateInputProps {
  value: string
  onChange: (template: string) => void
  disabled?: boolean
  size?: 'small' | 'medium'
  jobName?: string
}

const ArchiveNameTemplateInput: React.FC<ArchiveNameTemplateInputProps> = ({
  value,
  onChange,
  disabled = false,
  size = 'medium',
  jobName = 'example-job',
}) => {
  // Generate preview of archive name with current timestamp
  const previewName = useMemo(() => {
    const now = new Date()
    const timestamp = Math.floor(now.getTime() / 1000)
    const date = now.toISOString().split('T')[0]
    const time = now.toTimeString().split(' ')[0].replace(/:/g, '-')
    const isoString = now.toISOString().replace(/[:.]/g, '-').slice(0, -5)

    return value
      .replace(/{job_name}/g, jobName)
      .replace(/{now}/g, isoString)
      .replace(/{date}/g, date)
      .replace(/{time}/g, time)
      .replace(/{timestamp}/g, String(timestamp))
  }, [value, jobName])

  return (
    <Box>
      <TextField
        label="Archive Name Template"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        fullWidth
        size={size}
        disabled={disabled}
        helperText="Customize archive naming. Available placeholders: {job_name}, {now}, {date}, {time}, {timestamp}"
        InputProps={{
          sx: {
            fontSize: size === 'medium' ? '1.1rem' : '0.875rem',
            fontFamily: 'monospace',
          },
        }}
        InputLabelProps={{
          sx: { fontSize: size === 'medium' ? '1.1rem' : '0.875rem' },
        }}
      />
      {value && (
        <Alert severity="info" sx={{ mt: 2, fontFamily: 'monospace', fontSize: '0.875rem' }}>
          <strong>Preview:</strong> {previewName}
        </Alert>
      )}
    </Box>
  )
}

export default ArchiveNameTemplateInput

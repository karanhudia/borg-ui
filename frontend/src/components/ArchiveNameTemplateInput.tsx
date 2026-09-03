import React, { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
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
  const { t } = useTranslation()
  // Generate preview of archive name with current timestamp.
  // {now}/{date}/{time} render in the creating machine's local time (matching
  // the backend and borg's own expansion); {utcnow} renders in UTC. The
  // formats mirror the backend expansion exactly, millisecond precision
  // included, so the preview matches the generated archive name.
  const previewName = useMemo(() => {
    const now = new Date()
    const pad = (n: number) => String(n).padStart(2, '0')
    const pad3 = (n: number) => String(n).padStart(3, '0')
    const timestamp = Math.floor(now.getTime() / 1000)
    const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
    const time = now.toTimeString().split(' ')[0]
    const localIso = `${date}T${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}.${pad3(now.getMilliseconds())}`
    const utcIso = now.toISOString().slice(0, -1)

    return value
      .replace(/{job_name}/g, jobName)
      .replace(/{utcnow}/g, utcIso)
      .replace(/{now}/g, localIso)
      .replace(/{date}/g, date)
      .replace(/{time}/g, time)
      .replace(/{timestamp}/g, String(timestamp))
  }, [value, jobName])

  return (
    <Box>
      <TextField
        label={t('archiveNameTemplate.label')}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        fullWidth
        size={size}
        disabled={disabled}
        helperText={t('archiveNameTemplate.hint')}
        slotProps={{
          input: {
            sx: {
              fontSize: size === 'medium' ? '1.1rem' : '0.875rem',
              fontFamily: 'monospace',
            },
          },

          inputLabel: {
            sx: { fontSize: size === 'medium' ? '1.1rem' : '0.875rem' },
          },
        }}
      />
      {value && (
        <Alert severity="info" sx={{ mt: 2, fontFamily: 'monospace', fontSize: '0.875rem' }}>
          <strong>{t('archiveNameTemplate.preview')}</strong> {previewName}
        </Alert>
      )}
    </Box>
  )
}

export default ArchiveNameTemplateInput

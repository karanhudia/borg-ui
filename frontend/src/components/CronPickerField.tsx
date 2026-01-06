import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  TextField,
  IconButton,
  Tooltip,
  InputAdornment,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Stack,
  Paper,
  Box,
  Typography,
  Chip,
} from '@mui/material'
import { Clock, CheckCircle } from 'lucide-react'
import { scheduleAPI } from '../services/api'

interface CronPreset {
  name: string
  expression: string
  description: string
}

interface CronPickerFieldProps {
  value: string
  onChange: (value: string) => void
  label?: string
  placeholder?: string
  required?: boolean
  fullWidth?: boolean
  size?: 'small' | 'medium'
  helperText?: React.ReactNode
  disabled?: boolean
}

/**
 * Format cron expression to human-readable string
 * This is a simplified version - you may want to use a library like cronstrue
 */
const formatCronExpression = (cronExpression: string): string => {
  if (!cronExpression || !cronExpression.trim()) {
    return 'Invalid cron expression'
  }

  const parts = cronExpression.trim().split(/\s+/)
  if (parts.length !== 5) {
    return cronExpression // Return as-is if not standard 5-part cron
  }

  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts

  // Common patterns
  if (cronExpression === '0 2 * * *') return 'Daily at 2:00 AM'
  if (cronExpression === '0 0 * * 0') return 'Weekly on Sunday at midnight'
  if (cronExpression === '0 0 1 * *') return 'Monthly on the 1st at midnight'
  if (cronExpression === '0 */6 * * *') return 'Every 6 hours'
  if (cronExpression === '0 */12 * * *') return 'Every 12 hours'
  if (cronExpression === '*/15 * * * *') return 'Every 15 minutes'
  if (cronExpression === '*/30 * * * *') return 'Every 30 minutes'

  // Generic description
  let description = ''

  // Minute
  if (minute === '*') {
    description += 'Every minute'
  } else if (minute.startsWith('*/')) {
    description += `Every ${minute.substring(2)} minutes`
  } else {
    description += `At minute ${minute}`
  }

  // Hour
  if (hour !== '*') {
    if (hour.startsWith('*/')) {
      description += `, every ${hour.substring(2)} hours`
    } else {
      description += `, hour ${hour}`
    }
  }

  // Day of month
  if (dayOfMonth !== '*') {
    description += `, on day ${dayOfMonth}`
  }

  // Month
  if (month !== '*') {
    description += `, in month ${month}`
  }

  // Day of week
  if (dayOfWeek !== '*') {
    const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    const dayNum = parseInt(dayOfWeek)
    if (!isNaN(dayNum) && dayNum >= 0 && dayNum <= 6) {
      description += `, on ${days[dayNum]}`
    }
  }

  return description
}

export const CronPickerField: React.FC<CronPickerFieldProps> = ({
  value,
  onChange,
  label = 'Schedule',
  placeholder = '0 2 * * *',
  required = false,
  fullWidth = true,
  size = 'medium',
  helperText,
  disabled = false,
}) => {
  const [showPresets, setShowPresets] = useState(false)

  // Get cron presets
  const { data: presetsData } = useQuery({
    queryKey: ['cron-presets'],
    queryFn: scheduleAPI.getCronPresets,
  })

  const handlePresetSelect = (preset: CronPreset) => {
    onChange(preset.expression)
    setShowPresets(false)
  }

  const defaultHelperText = (
    <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
      <CheckCircle size={14} style={{ color: '#2e7d32' }} />
      <span>{formatCronExpression(value)}</span>
    </Box>
  )

  return (
    <>
      <TextField
        label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        fullWidth={fullWidth}
        size={size}
        placeholder={placeholder}
        disabled={disabled}
        InputProps={{
          sx: {
            fontFamily: 'monospace',
            fontSize: size === 'small' ? '0.9rem' : '1.1rem',
            letterSpacing: '0.1em',
          },
          endAdornment: (
            <InputAdornment position="end">
              <Tooltip title="Choose preset schedule" arrow>
                <IconButton onClick={() => setShowPresets(true)} edge="end" disabled={disabled}>
                  <Clock size={20} />
                </IconButton>
              </Tooltip>
            </InputAdornment>
          ),
        }}
        InputLabelProps={{
          sx: { fontSize: size === 'small' ? '0.9rem' : '1.1rem' },
        }}
        helperText={helperText !== undefined ? helperText : defaultHelperText}
      />

      {/* Presets Dialog */}
      <Dialog open={showPresets} onClose={() => setShowPresets(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Cron Expression Presets</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" gutterBottom sx={{ mt: 1 }}>
            Select a preset schedule
          </Typography>
          <Stack spacing={1} sx={{ mt: 2 }}>
            {presetsData?.data?.presets?.map((preset: CronPreset) => (
              <Paper
                key={preset.expression}
                sx={{
                  p: 2,
                  cursor: 'pointer',
                  border: 1,
                  borderColor: 'divider',
                  '&:hover': {
                    backgroundColor: 'action.hover',
                    borderColor: 'primary.main',
                  },
                }}
                onClick={() => handlePresetSelect(preset)}
              >
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Box>
                    <Typography variant="body2" fontWeight={500}>
                      {preset.name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {preset.description}
                    </Typography>
                  </Box>
                  <Chip
                    label={preset.expression}
                    size="small"
                    variant="outlined"
                    sx={{ fontFamily: 'monospace' }}
                  />
                </Stack>
              </Paper>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowPresets(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </>
  )
}

export default CronPickerField

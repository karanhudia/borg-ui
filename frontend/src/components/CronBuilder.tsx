import React, { useState, useEffect } from 'react'
import {
  Box,
  TextField,
  Stack,
  Typography,
  ToggleButtonGroup,
  ToggleButton,
  Select,
  MenuItem,
  alpha,
  Paper,
  InputAdornment,
  Divider,
  Tooltip,
} from '@mui/material'
import { Clock, Calendar, CalendarDays, CalendarRange, Code, Timer } from 'lucide-react'

interface CronBuilderProps {
  value: string // Cron expression in LOCAL time
  onChange: (cronExpression: string) => void // Returns LOCAL cron (parent handles UTC conversion when saving)
  label?: string
  helperText?: string
}

type Frequency = 'minute' | 'hourly' | 'daily' | 'weekly' | 'monthly' | 'custom'

interface CronState {
  frequency: Frequency
  minuteInterval: number
  hourInterval: number
  startingMinute: number
  hour: number
  minute: number
  selectedDays: boolean[]
  dayOfMonth: number
  customCron: string
}

const DAYS = ['M', 'T', 'W', 'T', 'F', 'S', 'S']
const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const DAY_NUMBERS = [1, 2, 3, 4, 5, 6, 0]

const parseCron = (cronExpression: string): CronState => {
  const parts = cronExpression.trim().split(/\s+/)
  if (parts.length !== 5) {
    return {
      frequency: 'daily',
      minuteInterval: 5,
      hourInterval: 6,
      startingMinute: 0,
      hour: 2,
      minute: 0,
      selectedDays: [true, false, false, false, false, false, false],
      dayOfMonth: 1,
      customCron: cronExpression,
    }
  }

  const [minute, hour, day, , dayOfWeek] = parts

  if (minute.startsWith('*/') && hour === '*' && day === '*' && dayOfWeek === '*') {
    return {
      frequency: 'minute',
      minuteInterval: parseInt(minute.replace('*/', '')) || 5,
      hourInterval: 6,
      startingMinute: 0,
      hour: 2,
      minute: 0,
      selectedDays: [true, false, false, false, false, false, false],
      dayOfMonth: 1,
      customCron: cronExpression,
    }
  }

  if (/^\d+$/.test(minute) && hour.startsWith('*/') && day === '*' && dayOfWeek === '*') {
    return {
      frequency: 'hourly',
      minuteInterval: 5,
      hourInterval: parseInt(hour.replace('*/', '')) || 6,
      startingMinute: parseInt(minute),
      hour: 2,
      minute: 0,
      selectedDays: [true, false, false, false, false, false, false],
      dayOfMonth: 1,
      customCron: cronExpression,
    }
  }

  if (/^\d+$/.test(minute) && /^\d+$/.test(hour) && day === '*' && dayOfWeek === '*') {
    return {
      frequency: 'daily',
      minuteInterval: 5,
      hourInterval: 6,
      startingMinute: 0,
      hour: parseInt(hour),
      minute: parseInt(minute),
      selectedDays: [true, false, false, false, false, false, false],
      dayOfMonth: 1,
      customCron: cronExpression,
    }
  }

  if (/^\d+$/.test(minute) && /^\d+$/.test(hour) && day === '*' && /^[\d,]+$/.test(dayOfWeek)) {
    const selectedDayNums = dayOfWeek.split(',').map((d) => parseInt(d))
    const selectedDays = DAY_NUMBERS.map((dayNum) => selectedDayNums.includes(dayNum))

    return {
      frequency: 'weekly',
      minuteInterval: 5,
      hourInterval: 6,
      startingMinute: 0,
      hour: parseInt(hour),
      minute: parseInt(minute),
      selectedDays,
      dayOfMonth: 1,
      customCron: cronExpression,
    }
  }

  if (/^\d+$/.test(minute) && /^\d+$/.test(hour) && /^\d+$/.test(day) && dayOfWeek === '*') {
    return {
      frequency: 'monthly',
      minuteInterval: 5,
      hourInterval: 6,
      startingMinute: 0,
      hour: parseInt(hour),
      minute: parseInt(minute),
      selectedDays: [true, false, false, false, false, false, false],
      dayOfMonth: parseInt(day),
      customCron: cronExpression,
    }
  }

  return {
    frequency: 'custom',
    minuteInterval: 5,
    hourInterval: 6,
    startingMinute: 0,
    hour: 2,
    minute: 0,
    selectedDays: [true, false, false, false, false, false, false],
    dayOfMonth: 1,
    customCron: cronExpression,
  }
}

const buildCron = (state: CronState): string => {
  switch (state.frequency) {
    case 'minute':
      return `*/${state.minuteInterval} * * * *`
    case 'hourly':
      return `${state.startingMinute} */${state.hourInterval} * * *`
    case 'daily':
      return `${state.minute} ${state.hour} * * *`
    case 'weekly': {
      const selectedDayNums = state.selectedDays
        .map((selected, idx) => (selected ? DAY_NUMBERS[idx] : null))
        .filter((d) => d !== null)
      if (selectedDayNums.length === 0) return `${state.minute} ${state.hour} * * 1`
      return `${state.minute} ${state.hour} * * ${selectedDayNums.join(',')}`
    }
    case 'monthly':
      return `${state.minute} ${state.hour} ${state.dayOfMonth} * *`
    case 'custom':
      return state.customCron
    default:
      return '0 2 * * *'
  }
}

const generatePreview = (state: CronState): string => {
  switch (state.frequency) {
    case 'minute':
      return `Every ${state.minuteInterval} minute${state.minuteInterval > 1 ? 's' : ''}`
    case 'hourly':
      return `Every ${state.hourInterval} hour${state.hourInterval > 1 ? 's' : ''}`
    case 'daily': {
      const hour12 = state.hour === 0 ? 12 : state.hour > 12 ? state.hour - 12 : state.hour
      const ampm = state.hour >= 12 ? 'PM' : 'AM'
      const minuteStr = state.minute.toString().padStart(2, '0')
      return `Daily at ${hour12}:${minuteStr} ${ampm}`
    }
    case 'weekly': {
      // Re-enable DAY_FULL mapping if needed or use shorter
      const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
      const selectedDayNames = dayNames.filter((_, idx) => state.selectedDays[idx])
      if (selectedDayNames.length === 0) return 'No days selected'
      const hour12 = state.hour === 0 ? 12 : state.hour > 12 ? state.hour - 12 : state.hour
      const ampm = state.hour >= 12 ? 'PM' : 'AM'
      const minuteStr = state.minute.toString().padStart(2, '0')
      const daysStr = selectedDayNames.length === 7 ? 'Daily' : selectedDayNames.join(', ')
      return `Every ${daysStr} at ${hour12}:${minuteStr} ${ampm}`
    }
    case 'monthly': {
      const hour12 = state.hour === 0 ? 12 : state.hour > 12 ? state.hour - 12 : state.hour
      const ampm = state.hour >= 12 ? 'PM' : 'AM'
      const minuteStr = state.minute.toString().padStart(2, '0')
      const suffix =
        state.dayOfMonth === 1
          ? 'st'
          : state.dayOfMonth === 2
            ? 'nd'
            : state.dayOfMonth === 3
              ? 'rd'
              : 'th'
      return `Monthly on the ${state.dayOfMonth}${suffix} at ${hour12}:${minuteStr} ${ampm}`
    }
    case 'custom':
      return 'Custom schedule: ' + state.customCron
    default:
      return ''
  }
}

export default function CronBuilder({ value, onChange, label, helperText }: CronBuilderProps) {
  // value is already in local time, no conversion needed
  const [state, setState] = useState<CronState>(parseCron(value))

  useEffect(() => {
    // value is already in local time, no conversion needed
    setState(parseCron(value))
  }, [value])

  const handleStateChange = (newState: Partial<CronState>) => {
    const updatedState = { ...state, ...newState }
    setState(updatedState)

    const localCron = buildCron(updatedState)
    // CronBuilder works entirely in local time - parent handles UTC conversion
    onChange(localCron)
  }

  const hour12 = state.hour === 0 ? 12 : state.hour > 12 ? state.hour - 12 : state.hour
  const ampm = state.hour >= 12 ? 'PM' : 'AM'

  const handleTimeChange = (hour12: number, minute: number, ampm: 'AM' | 'PM') => {
    let hour24 = hour12
    if (ampm === 'AM' && hour12 === 12) hour24 = 0
    else if (ampm === 'PM' && hour12 !== 12) hour24 = hour12 + 12
    handleStateChange({ hour: hour24, minute })
  }

  const handleFrequencyChange = (
    _: React.SyntheticEvent | null,
    newFrequency: Frequency | null
  ) => {
    if (newFrequency !== null) {
      handleStateChange({ frequency: newFrequency })
    }
  }

  // Common time input component
  const TimeInput = () => (
    <Stack direction="row" spacing={0.5} alignItems="center">
      <TextField
        type="number"
        value={hour12}
        onChange={(e) => {
          const newHour12 = Math.max(1, Math.min(12, parseInt(e.target.value) || 1))
          handleTimeChange(newHour12, state.minute, ampm)
        }}
        inputProps={{ min: 1, max: 12 }}
        variant="outlined"
        size="small"
        sx={{
          width: 50,
          '& .MuiInputBase-input': { p: '6px', textAlign: 'center', fontSize: '0.875rem' },
        }}
      />
      <Typography variant="body2" color="text.secondary" fontWeight={500}>
        :
      </Typography>
      <TextField
        type="number"
        value={state.minute.toString().padStart(2, '0')}
        onChange={(e) => {
          const newMinute = Math.max(0, Math.min(59, parseInt(e.target.value) || 0))
          handleTimeChange(hour12, newMinute, ampm)
        }}
        inputProps={{ min: 0, max: 59 }}
        variant="outlined"
        size="small"
        sx={{
          width: 50,
          '& .MuiInputBase-input': { p: '6px', textAlign: 'center', fontSize: '0.875rem' },
        }}
      />
      <Select
        value={ampm}
        onChange={(e) => handleTimeChange(hour12, state.minute, e.target.value as 'AM' | 'PM')}
        variant="outlined"
        size="small"
        sx={{
          width: 65,
          '& .MuiSelect-select': { p: '6px 24px 6px 8px !important', fontSize: '0.875rem' },
        }}
      >
        <MenuItem value="AM" sx={{ fontSize: '0.875rem' }}>
          AM
        </MenuItem>
        <MenuItem value="PM" sx={{ fontSize: '0.875rem' }}>
          PM
        </MenuItem>
      </Select>
    </Stack>
  )

  return (
    <Stack spacing={1.5}>
      {label && (
        <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>
          {label}
        </Typography>
      )}

      <Paper
        variant="outlined"
        sx={{
          p: 0,
          overflow: 'hidden',
          borderRadius: 2,
          borderColor: (theme) => alpha(theme.palette.divider, 0.6),
        }}
      >
        {/* Frequency Selector */}
        <Box
          sx={{ borderBottom: 1, borderColor: 'divider', bgcolor: 'background.default', p: 0.5 }}
        >
          <ToggleButtonGroup
            value={state.frequency}
            exclusive
            onChange={handleFrequencyChange}
            fullWidth
            size="small"
            sx={{
              '& .MuiToggleButton-root': {
                border: 0,
                borderRadius: 1,
                mx: 0.5,
                py: 0.5,
                fontSize: '0.75rem',
                fontWeight: 600,
                color: 'text.secondary',
                textTransform: 'none',
                height: 28, // Fixed height for tabs
                '&.Mui-selected': {
                  bgcolor: 'background.paper',
                  color: 'primary.main',
                  boxShadow: '0 1px 2px 0 rgba(0,0,0,0.05)',
                  '&:hover': {
                    bgcolor: 'background.paper',
                  },
                },
              },
            }}
          >
            <ToggleButton value="minute">
              <Stack direction="row" spacing={0.5} alignItems="center">
                <Timer size={14} /> <span>Minutes</span>
              </Stack>
            </ToggleButton>
            <ToggleButton value="hourly">
              <Stack direction="row" spacing={0.5} alignItems="center">
                <Clock size={14} /> <span>Hourly</span>
              </Stack>
            </ToggleButton>
            <ToggleButton value="daily">
              <Stack direction="row" spacing={0.5} alignItems="center">
                <Calendar size={14} /> <span>Daily</span>
              </Stack>
            </ToggleButton>
            <ToggleButton value="weekly">
              <Stack direction="row" spacing={0.5} alignItems="center">
                <CalendarDays size={14} /> <span>Weekly</span>
              </Stack>
            </ToggleButton>
            <ToggleButton value="monthly">
              <Stack direction="row" spacing={0.5} alignItems="center">
                <CalendarRange size={14} /> <span>Monthly</span>
              </Stack>
            </ToggleButton>
            <ToggleButton value="custom">
              <span>Custom</span>
            </ToggleButton>
          </ToggleButtonGroup>
        </Box>

        {/* Configuration Area */}
        <Box
          sx={{
            p: 2,
            height: 85, // Fixed height to prevent shifting layout
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center', // Center content vertically and horizontally
          }}
        >
          {state.frequency === 'minute' && (
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="body2">Run every</Typography>
              <TextField
                type="number"
                value={state.minuteInterval}
                onChange={(e) =>
                  handleStateChange({ minuteInterval: Math.max(1, parseInt(e.target.value) || 1) })
                }
                inputProps={{ min: 1, max: 59 }}
                variant="outlined"
                size="small"
                sx={{ width: 60, '& input': { textAlign: 'center', p: '6px' } }}
              />
              <Typography variant="body2">minutes.</Typography>
            </Stack>
          )}

          {state.frequency === 'hourly' && (
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
              <Typography variant="body2">Run every</Typography>
              <TextField
                type="number"
                value={state.hourInterval}
                onChange={(e) =>
                  handleStateChange({ hourInterval: Math.max(1, parseInt(e.target.value) || 1) })
                }
                inputProps={{ min: 1, max: 23 }}
                variant="outlined"
                size="small"
                sx={{ width: 60, '& input': { textAlign: 'center', p: '6px' } }}
              />
              <Typography variant="body2">hours at minute</Typography>
              <TextField
                type="number"
                value={state.startingMinute}
                onChange={(e) =>
                  handleStateChange({
                    startingMinute: Math.max(0, Math.min(59, parseInt(e.target.value) || 0)),
                  })
                }
                inputProps={{ min: 0, max: 59 }}
                variant="outlined"
                size="small"
                sx={{ width: 60, '& input': { textAlign: 'center', p: '6px' } }}
              />
              <Typography variant="body2">past the hour.</Typography>
            </Stack>
          )}

          {state.frequency === 'daily' && (
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="body2">Run daily at</Typography>
              <TimeInput />
            </Stack>
          )}

          {state.frequency === 'weekly' && (
            <Stack spacing={1} width="100%" alignItems="center">
              <Stack direction="row" spacing={1} alignItems="center">
                <Typography variant="body2">Run on</Typography>

                {/* ... inside component ... */}

                <ToggleButtonGroup
                  value={state.selectedDays
                    .map((s, i) => (s ? i.toString() : null))
                    .filter(Boolean)}
                  onChange={(_, newValues: string[]) => {
                    const newIndices = newValues.map((v) => parseInt(v))
                    const newSelected = DAYS.map((_, i) => newIndices.includes(i))
                    handleStateChange({ selectedDays: newSelected })
                  }}
                  size="small"
                >
                  {DAYS.map((d, i) => (
                    <Tooltip key={i} title={DAY_NAMES[i]} arrow>
                      <ToggleButton
                        value={i.toString()}
                        sx={{
                          width: 24,
                          height: 24,
                          p: 0,
                          borderRadius: '50% !important',
                          border: 'none',
                          ml: 0.25,
                          fontSize: '0.7rem',
                          '&.Mui-selected': {
                            bgcolor: 'primary.main',
                            color: 'white',
                            '&:hover': { bgcolor: 'primary.dark' },
                          },
                        }}
                      >
                        {d}
                      </ToggleButton>
                    </Tooltip>
                  ))}
                </ToggleButtonGroup>
              </Stack>
              <Stack direction="row" spacing={1} alignItems="center">
                <Typography variant="body2">at</Typography>
                <TimeInput />
              </Stack>
            </Stack>
          )}

          {state.frequency === 'monthly' && (
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="body2">Run on day</Typography>
              <Select
                value={state.dayOfMonth}
                onChange={(e) => handleStateChange({ dayOfMonth: e.target.value as number })}
                variant="outlined"
                size="small"
                sx={{
                  mx: 1,
                  width: 60,
                  '& .MuiSelect-select': {
                    p: '6px 24px 6px 8px !important',
                    textAlign: 'center',
                    fontSize: '0.875rem',
                  },
                }}
                MenuProps={{ PaperProps: { sx: { maxHeight: 300 } } }}
              >
                {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
                  <MenuItem key={d} value={d} sx={{ fontSize: '0.875rem' }}>
                    {d}
                  </MenuItem>
                ))}
              </Select>
              <Typography variant="body2">at</Typography>
              <TimeInput />
            </Stack>
          )}

          {state.frequency === 'custom' && (
            <TextField
              value={state.customCron}
              onChange={(e) => handleStateChange({ customCron: e.target.value })}
              fullWidth
              placeholder="* * * * *"
              variant="outlined"
              size="small"
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Code size={16} />
                  </InputAdornment>
                ),
                sx: { fontFamily: 'monospace', fontSize: '0.875rem' },
              }}
            />
          )}
        </Box>

        {/* Preview Footer */}
        <Divider />
        <Box
          sx={{
            px: 2,
            py: 1,
            bgcolor: (theme) => alpha(theme.palette.primary.main, 0.04),
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography
              variant="body2"
              color="primary"
              sx={{ fontSize: '0.8125rem', fontWeight: 500 }}
            >
              {generatePreview(state)}
            </Typography>
          </Stack>
          <Box
            component="span"
            sx={{
              fontFamily: 'monospace',
              bgcolor: 'background.paper',
              px: 1,
              py: 0.5,
              borderRadius: 1,
              border: 1,
              borderColor: 'divider',
              fontSize: '0.7rem',
            }}
          >
            {buildCron(state)}
          </Box>
        </Box>
      </Paper>
      {helperText && (
        <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>
          {helperText}
        </Typography>
      )}
    </Stack>
  )
}

import { Box, Stack, Typography } from '@mui/material'
import type { ScheduledInstantDisplay } from '../utils/dateUtils'

interface ScheduledInstantTooltipProps {
  display: ScheduledInstantDisplay
}

function TooltipRow({ label, time, timeZone }: { label: string; time: string; timeZone: string }) {
  const compactTime = time.replace(' at ', ', ')

  return (
    <Box sx={{ minWidth: 0 }}>
      <Typography
        component="div"
        sx={{
          color: 'rgba(255,255,255,0.66)',
          fontSize: '0.56rem',
          fontWeight: 650,
          lineHeight: 1.15,
          mb: 0.3,
        }}
      >
        {label}
      </Typography>
      <Typography
        component="div"
        sx={{
          color: '#fff',
          fontSize: '0.68rem',
          fontVariantNumeric: 'tabular-nums',
          fontWeight: 560,
          lineHeight: 1.28,
          overflowWrap: 'anywhere',
        }}
      >
        {compactTime}
      </Typography>
      <Box
        component="span"
        sx={{
          bgcolor: 'rgba(255,255,255,0.09)',
          border: '1px solid rgba(255,255,255,0.18)',
          borderRadius: 0.75,
          color: 'rgba(255,255,255,0.92)',
          display: 'inline-block',
          fontFamily: 'monospace',
          fontSize: '0.58rem',
          fontWeight: 650,
          lineHeight: 1.25,
          mt: 0.36,
          maxWidth: '100%',
          overflowWrap: 'anywhere',
          px: 0.48,
          py: 0.18,
        }}
      >
        {timeZone}
      </Box>
    </Box>
  )
}

export default function ScheduledInstantTooltip({ display }: ScheduledInstantTooltipProps) {
  return (
    <Stack
      spacing={0.72}
      sx={{
        maxWidth: 245,
        minWidth: 178,
        p: 0.15,
        whiteSpace: 'normal',
      }}
    >
      <TooltipRow
        label="Schedule timezone"
        time={display.scheduledTime}
        timeZone={display.scheduledTimeZone}
      />
      {display.localTime && display.localTimeZone && (
        <TooltipRow
          label="Your local timezone"
          time={display.localTime}
          timeZone={display.localTimeZone}
        />
      )}
    </Stack>
  )
}

import type { ReactNode } from 'react'
import { Box, Stack, Typography, alpha, useTheme } from '@mui/material'
import type { LucideIcon } from 'lucide-react'
import { toneColor, type Tone } from './tones'

export interface TintedTileProps {
  testId: string
  label: string
  value: ReactNode
  sub?: ReactNode
  tone: Tone
  icon: LucideIcon
  /** A figure the page cannot give (not measured): drawn quiet. */
  muted?: boolean
}

/** The archive header's stat tile, in the app's tones. */
export default function TintedTile({
  testId,
  label,
  value,
  sub,
  tone,
  icon: Icon,
  muted = false,
}: TintedTileProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const color = toneColor(theme, tone)
  return (
    <Box
      data-testid={testId}
      sx={{
        borderRadius: 2,
        bgcolor: alpha(color, isDark ? 0.1 : 0.07),
        px: 2,
        py: 1.75,
        minWidth: 0,
        height: '100%',
        boxSizing: 'border-box',
        boxShadow: isDark
          ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 2px 8px ${alpha('#000', 0.2)}`
          : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 6px ${alpha('#000', 0.06)}`,
      }}
    >
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography
            variant="caption"
            sx={{
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              fontSize: '0.6rem',
              fontWeight: 700,
              color,
              display: 'block',
              mb: 0.75,
            }}
          >
            {label}
          </Typography>
          <Typography
            variant="h5"
            sx={{
              fontWeight: muted ? 500 : 700,
              lineHeight: 1.2,
              fontSize: muted ? '1rem' : { xs: '1.4rem', lg: '1.5rem' },
              color: muted ? 'text.secondary' : color,
              fontStyle: muted ? 'italic' : 'normal',
              wordBreak: 'break-word',
            }}
          >
            {value}
          </Typography>
          {sub ? (
            <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
              {sub}
            </Typography>
          ) : null}
        </Box>
        <Box sx={{ color, opacity: 0.4, mt: 0.25, flexShrink: 0, display: 'flex' }}>
          <Icon size={32} strokeWidth={1.5} />
        </Box>
      </Stack>
    </Box>
  )
}

import { Box, alpha, useTheme } from '@mui/material'
import { CHANGE_GLYPH, changeColor } from './changeStyle'
import type { ChangeType } from '../../types/archives'

interface ChangeBadgeProps {
  change: ChangeType
  size?: number
}

// A small square glyph, coloured by change type, that leads every change
// row. It is the same mark the tab label counts use.
export default function ChangeBadge({ change, size = 20 }: ChangeBadgeProps) {
  const theme = useTheme()
  const color = changeColor(theme, change)
  return (
    <Box
      aria-hidden
      sx={{
        width: size,
        height: size,
        borderRadius: '5px',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: alpha(color, 0.14),
        color,
        fontWeight: 700,
        fontSize: size * 0.7,
        lineHeight: 1,
        flexShrink: 0,
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
      }}
    >
      {CHANGE_GLYPH[change]}
    </Box>
  )
}

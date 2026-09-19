import { alpha, type Theme } from '@mui/material'

/** The palette keys the stat tiles and chips draw their figures in: red for what
 * goes, green for what stays and what that gives back, amber for what is
 * at risk, blue for the repository's size. */
export type Tone = 'error' | 'success' | 'warning' | 'info' | 'primary' | 'secondary'

export const toneColor = (theme: Theme, tone: Tone) => theme.palette[tone].main

/** A chip in a tone: tinted ground, coloured text. */
export const tintChipSx = (theme: Theme, tone: Tone) => {
  const color = toneColor(theme, tone)
  return {
    color,
    bgcolor: alpha(color, theme.palette.mode === 'dark' ? 0.16 : 0.1),
    fontWeight: 600,
    '& .MuiChip-icon': { color },
  }
}

import { alpha, type Theme } from '@mui/material'

/** The palette keys the stat tiles and chips draw their figures in: red for what
 * goes, green for what stays and what that gives back, amber for what is
 * at risk, blue for the repository's size. */
export type Tone = 'error' | 'success' | 'warning' | 'info' | 'primary' | 'secondary'

/** 'neutral' is for states with no colour of their own, like unknown. */
export const toneColor = (theme: Theme, tone: Tone | 'neutral') =>
  tone === 'neutral' ? theme.palette.text.secondary : theme.palette[tone].main

/** A chip in a tone: tinted ground, coloured text. */
export const tintChipSx = (theme: Theme, tone: Tone) => {
  const color = toneColor(theme, tone)
  const isDark = theme.palette.mode === 'dark'
  return {
    // A chip often sits in a row that is tinted too; on dark, the lighter
    // 300 shade keeps the label at 4.5:1 over the stacked tints.
    color: isDark ? theme.palette[tone].light : color,
    bgcolor: alpha(color, isDark ? 0.16 : 0.1),
    fontWeight: 600,
    '& .MuiChip-icon': { color: isDark ? theme.palette[tone].light : color },
  }
}

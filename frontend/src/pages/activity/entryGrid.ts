import { alpha, type Theme } from '@mui/material'
import type { UmbrellaKind } from './runs'

// The columns every entry's right side shares, so durations and action
// icons line up down the page whatever a given row happens to have. The
// plan run header uses the same grid.
export const ENTRY_COLUMNS = {
  xs: '48px 20px minmax(0, 1fr)',
  md: '60px 20px minmax(0, 1fr)',
} as const

export function metaGridSx(actionCount: number) {
  return {
    // A phone has no room for the columns: the block wraps onto its own
    // line under the title, actions pushed to the right edge.
    width: { xs: '100%', md: 'auto' },
    ml: { md: 'auto' },
    display: { xs: 'flex', md: 'grid' },
    flexWrap: 'wrap',
    gridTemplateColumns: `148px ${Math.max(actionCount, 1) * 34}px`,
    alignItems: 'center',
    columnGap: 1,
    rowGap: 0.5,
    flexShrink: 0,
    '& > :last-child': { ml: { xs: 'auto', md: 0 } },
  } as const
}

// One colour per status, for the dot on the rail and the legend that
// explains it. Anything without a colour of its own (queued, skipped,
// cancelled) is the muted default.
export function statusColor(theme: Theme, status: string): string {
  return (
    {
      completed: theme.palette.success.main,
      completed_with_warnings: theme.palette.warning.main,
      needs_backup: theme.palette.warning.main,
      running: theme.palette.primary.main,
      failed: theme.palette.error.main,
    }[status] ?? alpha(theme.palette.text.primary, 0.25)
  )
}

// One colour per umbrella, so a plan run, a schedule firing, and a manual
// click read differently at a glance.
export function umbrellaColor(theme: Theme, kind: UmbrellaKind): string {
  return {
    plan: theme.palette.secondary.main,
    schedule: theme.palette.info.main,
    manual: theme.palette.text.secondary,
    import: theme.palette.info.dark,
    followup: theme.palette.text.secondary,
    reconcile: theme.palette.primary.main,
    retry: theme.palette.warning.main,
    other: theme.palette.text.secondary,
  }[kind]
}

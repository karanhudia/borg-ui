import type { Theme } from '@mui/material'
import type { ChangeType } from '../../types/archives'

// One mapping from a change type to its colour and glyph, shared by the
// Changes tab, its preview, the tab label counts, and file history.
export function changeColor(theme: Theme, change: ChangeType): string {
  switch (change) {
    case 'added':
      return theme.palette.success.main
    case 'removed':
      return theme.palette.error.main
    case 'modified':
    case 'summary':
      return theme.palette.warning.main
  }
}

export const CHANGE_GLYPH: Record<ChangeType, string> = {
  added: '+',
  removed: '−',
  modified: '~',
  summary: '~',
}

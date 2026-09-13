import { alpha, type Theme } from '@mui/material'
import type { SystemStyleObject } from '@mui/system'

/** The bottom-right column the archive page keeps for floating panels:
 *  restore progress on top, the Files tab's selection bar nearest the
 *  corner. One column, so two panels can never cover each other. */
export const cornerStackSx: SystemStyleObject<Theme> = {
  position: 'fixed',
  right: { xs: 12, sm: 24 },
  bottom: { xs: 12, sm: 24 },
  left: { xs: 12, sm: 'auto' },
  width: { sm: 380 },
  maxWidth: 'calc(100vw - 24px)',
  zIndex: (theme) => theme.zIndex.appBar,
  display: 'flex',
  flexDirection: 'column',
  gap: 1.5,
  pointerEvents: 'none',
  '& > *': { pointerEvents: 'auto' },
}

/** One panel in that column, styled like a Drive upload card. */
export const cornerPanelSx: SystemStyleObject<Theme> = {
  borderRadius: 3,
  overflow: 'hidden',
  color: 'common.white',
  bgcolor: (theme) =>
    theme.palette.mode === 'dark' ? theme.palette.grey[800] : theme.palette.grey[900],
  boxShadow: (theme) =>
    `0 12px 32px ${alpha(theme.palette.common.black, 0.28)}, 0 0 0 1px ${alpha(theme.palette.common.white, 0.08)}`,
  '@keyframes corner-panel-in': {
    from: { opacity: 0, transform: 'translateY(12px)' },
    to: { opacity: 1, transform: 'translateY(0)' },
  },
  animation: 'corner-panel-in 180ms ease-out',
}

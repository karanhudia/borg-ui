import { alpha, type Theme } from '@mui/material'
import type { SystemStyleObject } from '@mui/system'
import { tintChipSx, type Tone } from '../shared/tones'

/** The bottom-right column the archive page keeps for floating panels:
 *  restore progress on top, the Files tab's selection bar nearest the
 *  corner. One column, so two panels can never cover each other. */
export const cornerStackSx: SystemStyleObject<Theme> = {
  position: 'fixed',
  // The column scrolls (see below), which would clip the panels' shadows at
  // its edges. So it is padded by the shadow's full reach (32px, see
  // cornerPanelSx) and sits that much closer to the corner, which puts the
  // panels themselves 12px / 24px in.
  p: 4,
  right: { xs: -20, sm: -8 },
  bottom: { xs: -20, sm: -8 },
  left: { xs: -20, sm: 'auto' },
  width: { sm: 380 + 64 },
  maxWidth: 'calc(100vw + 40px)',
  zIndex: (theme) => theme.zIndex.appBar,
  display: 'flex',
  flexDirection: 'column',
  gap: 1.5,
  // Cards stay until dismissed, so enough restores could climb past the top
  // of the window. The column scrolls instead.
  maxHeight: '100dvh',
  overflowY: 'auto',
  overscrollBehavior: 'contain',
  pointerEvents: 'none',
  '& > *': { pointerEvents: 'auto' },
}

/** One panel in that column: the same paper surface as the page's cards,
 *  lifted by a shadow so it reads as floating in either theme. */
export const cornerPanelSx: SystemStyleObject<Theme> = {
  borderRadius: 3,
  overflow: 'hidden',
  color: 'text.primary',
  bgcolor: 'background.paper',
  // Reaches 32px at most (offset plus blur), which the column's padding
  // covers, so no edge of it is ever clipped.
  boxShadow: (theme) =>
    theme.palette.mode === 'dark'
      ? `0 8px 24px ${alpha(theme.palette.common.black, 0.45)}, 0 0 0 1px ${alpha(theme.palette.common.white, 0.12)}`
      : `0 8px 24px ${alpha(theme.palette.common.black, 0.12)}, 0 1px 2px ${alpha(theme.palette.common.black, 0.06)}, 0 0 0 1px ${theme.palette.divider}`,
  '@keyframes corner-panel-in': {
    from: { opacity: 0, transform: 'translateY(12px)' },
    to: { opacity: 1, transform: 'translateY(0)' },
  },
  animation: 'corner-panel-in 180ms ease-out',
}

/** The panel's title row: the same faintly tinted ground the details pane
 *  gives its header, so the two read as one family. */
export const cornerPanelHeaderSx: SystemStyleObject<Theme> = {
  display: 'flex',
  alignItems: 'center',
  gap: 1.5,
  pl: 1.5,
  pr: 1,
  py: 1.25,
  bgcolor: (theme) => alpha(theme.palette.text.primary, 0.025),
  borderBottom: 1,
  borderColor: 'divider',
}

/** The panel's action row. */
export const cornerPanelFooterSx: SystemStyleObject<Theme> = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'flex-end',
  gap: 1,
  px: 1.5,
  py: 1.25,
  borderTop: 1,
  borderColor: 'divider',
}

/** The 32px tinted square that leads the header, in the panel's tone. */
export const cornerPanelIconSx = (theme: Theme, tone: Tone): SystemStyleObject<Theme> => ({
  ...tintChipSx(theme, tone),
  width: 32,
  height: 32,
  borderRadius: '9px',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  flexShrink: 0,
})

/** Quiet icon button for the header's dismiss and expand controls. */
export const cornerPanelIconButtonSx: SystemStyleObject<Theme> = {
  color: 'text.secondary',
  '&:hover': { color: 'text.primary', bgcolor: 'action.hover' },
}

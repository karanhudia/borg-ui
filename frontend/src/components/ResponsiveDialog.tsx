import { useTheme, useMediaQuery, Dialog, SwipeableDrawer, Box, IconButton } from '@mui/material'
import { Close } from '@mui/icons-material'
import type { DialogProps } from '@mui/material'
import type { ReactNode } from 'react'

type ResponsiveDialogProps = DialogProps & {
  /** On mobile: rendered in a sticky bar above the safe-area inset, outside the scroll area.
   *  On desktop: rendered as a direct child of Dialog (place DialogActions here). */
  footer?: ReactNode
}

export default function ResponsiveDialog({
  open,
  onClose,
  children,
  footer,
  // The following props are desktop-only (spread into <Dialog> via ...rest) — silently ignored on mobile:
  // maxWidth, fullWidth, PaperProps, TransitionProps, and other DialogProps
  maxWidth,
  fullWidth,
  ...rest
}: ResponsiveDialogProps) {
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))

  if (isMobile) {
    return (
      <SwipeableDrawer
        anchor="bottom"
        open={open}
        onClose={onClose ? (e) => onClose(e, 'backdropClick') : () => {}}
        // Note: SwipeableDrawer doesn't expose close reason, so 'backdropClick' is used
        // for all close events (including swipe-to-dismiss). This means dialogs that
        // distinguish 'escapeKeyDown' to prevent accidental close will behave incorrectly
        // on mobile.
        onOpen={() => {}}
        disableSwipeToOpen
        disableDiscovery
        ModalProps={{ keepMounted: false }}
        PaperProps={{
          sx: {
            borderRadius: '16px 16px 0 0',
            maxHeight: '90vh',
            display: 'flex',
            flexDirection: 'column',
          },
        }}
      >
        {/* Drag handle row with X close button */}
        <Box
          data-testid="drag-handle"
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            height: 44,
            flexShrink: 0,
            position: 'relative',
          }}
        >
          <Box sx={{ width: 32, height: 4, borderRadius: 2, bgcolor: 'divider' }} />
          {onClose && (
            <IconButton
              size="small"
              onClick={(e) => onClose(e, 'backdropClick')}
              aria-label="close"
              sx={{ position: 'absolute', right: 8, color: 'text.secondary' }}
            >
              <Close fontSize="small" />
            </IconButton>
          )}
        </Box>

        {/* Scrollable content — overscroll-behavior prevents pull-to-refresh */}
        <Box sx={{ overflowY: 'auto', flex: 1, overscrollBehavior: 'contain' }}>
          {children}
        </Box>

        {/* Sticky footer — always visible above safe area, outside scroll */}
        {footer && (
          <Box
            data-testid="responsive-dialog-footer"
            sx={{
              flexShrink: 0,
              borderTop: 1,
              borderColor: 'divider',
              pb: 'env(safe-area-inset-bottom, 0px)',
            }}
          >
            {footer}
          </Box>
        )}
      </SwipeableDrawer>
    )
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth={maxWidth} fullWidth={fullWidth} {...rest}>
      {children}
      {footer}
    </Dialog>
  )
}

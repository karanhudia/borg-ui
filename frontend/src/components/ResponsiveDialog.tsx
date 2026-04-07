import { useTheme, useMediaQuery, Dialog, SwipeableDrawer, Box, IconButton } from '@mui/material'
import { Close } from '@mui/icons-material'
import type { DialogProps } from '@mui/material'

type ResponsiveDialogProps = DialogProps

export default function ResponsiveDialog({
  open,
  onClose,
  children,
  // maxWidth and fullWidth are desktop-only — silently ignored on mobile
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
        {/* Scrollable content */}
        <Box sx={{ overflowY: 'auto', flex: 1 }}>{children}</Box>
      </SwipeableDrawer>
    )
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth={maxWidth} fullWidth={fullWidth} {...rest}>
      {children}
    </Dialog>
  )
}

import { Box, IconButton, Tooltip } from '@mui/material'
import { alpha } from '@mui/material/styles'
import { Copy } from 'lucide-react'

/**
 * A command in a code block with a copy button in its corner.
 *
 * One visual language for "run this on the endpoint", shared by the enrollment
 * command, the reinstall dialog and the change server URL dialog.
 */
export default function CopyableCodeBlock({
  value,
  copyLabel,
  onCopy,
}: {
  value: string
  copyLabel: string
  onCopy: () => void
}) {
  return (
    <Box sx={{ position: 'relative', minWidth: 0 }}>
      <Box
        component="code"
        sx={{
          display: 'block',
          p: 1.5,
          pr: 5.5,
          borderRadius: 1,
          border: '1px solid',
          borderColor: 'divider',
          bgcolor: 'action.hover',
          color: 'text.primary',
          overflowX: 'auto',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          fontSize: '0.8rem',
          fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
        }}
      >
        {value}
      </Box>
      <Tooltip title={copyLabel}>
        <IconButton
          aria-label={copyLabel}
          size="small"
          onClick={onCopy}
          sx={{
            position: 'absolute',
            top: 8,
            right: 8,
            border: '1px solid',
            color: 'primary.main',
            borderColor: (theme) => alpha(theme.palette.primary.main, 0.45),
            bgcolor: (theme) => alpha(theme.palette.primary.main, 0.08),
            '&:hover': {
              borderColor: 'primary.main',
              bgcolor: (theme) => alpha(theme.palette.primary.main, 0.14),
            },
            '&:focus-visible': {
              outline: '2px solid',
              outlineColor: 'primary.main',
              outlineOffset: 2,
            },
          }}
        >
          <Copy size={16} />
        </IconButton>
      </Tooltip>
    </Box>
  )
}

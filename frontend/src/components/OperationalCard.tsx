import type { ReactNode } from 'react'
import { Box, alpha, useTheme } from '@mui/material'
import type { SxProps, Theme } from '@mui/material/styles'

interface OperationalCardProps {
  children: ReactNode
  dataTestId?: string
  isActive?: boolean
  idleAccent?: string
  activeAccent?: string
  sx?: SxProps<Theme>
}

const DEFAULT_IDLE_ACCENT = '#059669'
const DEFAULT_ACTIVE_ACCENT = '#f59e0b'

export default function OperationalCard({
  children,
  dataTestId,
  isActive = false,
  idleAccent = DEFAULT_IDLE_ACCENT,
  activeAccent = DEFAULT_ACTIVE_ACCENT,
  sx = {},
}: OperationalCardProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  return (
    <Box
      data-testid={dataTestId}
      sx={[
        {
          position: 'relative',
          borderRadius: 2,
          bgcolor: 'background.paper',
          overflow: 'hidden',
          maxWidth: '100%',
          minWidth: 0,
          boxShadow: isActive
            ? `0 0 0 1px ${alpha(activeAccent, 0.4)}, 0 4px 16px ${alpha('#000', 0.2)}, 0 2px 6px ${alpha(activeAccent, 0.1)}`
            : isDark
              ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 4px 16px ${alpha('#000', 0.25)}`
              : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 8px ${alpha('#000', 0.07)}`,
          transition: 'all 200ms cubic-bezier(0.16,1,0.3,1)',
          '&:hover': {
            transform: 'translateY(-2px)',
            boxShadow: isActive
              ? `0 0 0 1px ${alpha(activeAccent, 0.55)}, 0 8px 24px ${alpha('#000', 0.28)}, 0 4px 12px ${alpha(activeAccent, 0.15)}`
              : isDark
                ? `0 0 0 1px ${alpha(idleAccent, 0.4)}, 0 8px 24px ${alpha('#000', 0.3)}, 0 2px 8px ${alpha(idleAccent, 0.1)}`
                : `0 0 0 1px ${alpha(idleAccent, 0.3)}, 0 8px 24px ${alpha('#000', 0.12)}, 0 2px 8px ${alpha(idleAccent, 0.08)}`,
          },
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      {children}
    </Box>
  )
}

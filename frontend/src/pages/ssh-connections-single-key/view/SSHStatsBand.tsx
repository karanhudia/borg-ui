import type { TFunction } from 'i18next'
import type { Theme } from '@mui/material/styles'
import { Box, Typography, alpha } from '@mui/material'
import { CheckCircle, Wifi, XCircle } from 'lucide-react'

interface Stats {
  totalConnections: number
  activeConnections: number
  failedConnections: number
}

interface SSHStatsBandProps {
  t: TFunction
  theme: Theme
  isDark: boolean
  stats: Stats
}

export function SSHStatsBand({ t, theme, isDark, stats }: SSHStatsBandProps) {
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        borderRadius: 2,
        border: '1px solid',
        borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
        overflow: 'hidden',
        mb: 3,
        bgcolor: isDark ? alpha('#fff', 0.025) : alpha('#000', 0.018),
        boxShadow: isDark
          ? `0 0 0 1px ${alpha('#fff', 0.04)}, 0 2px 8px ${alpha('#000', 0.2)}`
          : `0 0 0 1px ${alpha('#000', 0.06)}, 0 2px 6px ${alpha('#000', 0.05)}`,
      }}
    >
      {[
        {
          label: t('sshConnections.stats.totalConnections'),
          value: stats.totalConnections,
          icon: <Wifi size={13} />,
          color: theme.palette.primary.main,
        },
        {
          label: t('sshConnections.stats.active'),
          value: stats.activeConnections,
          icon: <CheckCircle size={13} />,
          color: theme.palette.success.main,
        },
        {
          label: t('sshConnections.stats.failed'),
          value: stats.failedConnections,
          icon: <XCircle size={13} />,
          color: theme.palette.error.main,
        },
      ].map((stat, i) => (
        <Box
          key={stat.label}
          sx={{
            px: { xs: 1.25, sm: 2 },
            py: { xs: 1.5, sm: 1.75 },
            borderRight: i < 2 ? '1px solid' : 0,
            borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: { xs: 0.75, sm: 0.5 } }}>
            <Box
              sx={{
                color: alpha(stat.color, 0.75),
                display: 'flex',
                alignItems: 'center',
                flexShrink: 0,
              }}
            >
              {stat.icon}
            </Box>
            <Typography
              sx={{
                fontSize: { xs: '0.58rem', sm: '0.6rem' },
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
                color: alpha(stat.color, 0.75),
                lineHeight: 1.2,
                whiteSpace: 'nowrap',
              }}
            >
              {stat.label}
            </Typography>
          </Box>
          <Typography
            sx={{
              fontSize: { xs: '1.75rem', sm: '1.5rem' },
              fontWeight: 700,
              lineHeight: 1,
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {stat.value}
          </Typography>
        </Box>
      ))}
    </Box>
  )
}

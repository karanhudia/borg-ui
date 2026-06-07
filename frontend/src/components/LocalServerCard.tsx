import { useTranslation } from 'react-i18next'
import { Box, IconButton, Tooltip, Typography, useTheme, alpha } from '@mui/material'
import { CircleCheck, Monitor, Power } from 'lucide-react'

interface LocalServerCardProps {
  active: boolean
  onUse: () => void
}

export default function LocalServerCard({ active, onUse }: LocalServerCardProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const primary = theme.palette.primary.main
  const builtinAccent = theme.palette.text.secondary

  return (
    <Box
      sx={{
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        borderRadius: 2,
        bgcolor: active ? alpha(primary, isDark ? 0.08 : 0.04) : 'background.paper',
        boxShadow: active
          ? `0 0 0 1.5px ${alpha(primary, isDark ? 0.55 : 0.4)}, 0 4px 16px ${alpha(primary, isDark ? 0.18 : 0.1)}`
          : isDark
            ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 4px 16px ${alpha('#000', 0.25)}`
            : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 8px ${alpha('#000', 0.07)}`,
        transition: 'all 200ms cubic-bezier(0.16,1,0.3,1)',
        '&:hover': {
          transform: 'translateY(-2px)',
          boxShadow: active
            ? `0 0 0 1.5px ${alpha(primary, isDark ? 0.6 : 0.45)}, 0 8px 24px ${alpha(primary, isDark ? 0.22 : 0.14)}`
            : isDark
              ? `0 0 0 1px ${alpha('#fff', 0.16)}, 0 8px 24px ${alpha('#000', 0.3)}`
              : `0 0 0 1px ${alpha('#000', 0.12)}, 0 8px 24px ${alpha('#000', 0.1)}`,
        },
      }}
    >
      <Box
        sx={{
          px: { xs: 1.75, sm: 2 },
          pt: { xs: 1.5, sm: 1.75 },
          pb: { xs: 1.5, sm: 1.75 },
        }}
      >
        {/* Top row: status eyebrow on left, badge OR action on right */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 1,
            mb: 0.5,
            minHeight: 28,
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Box sx={{ color: builtinAccent, display: 'flex', alignItems: 'center' }}>
              <Monitor size={13} />
            </Box>
            <Typography
              sx={{
                fontSize: '0.6rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                color: alpha(builtinAccent, 0.9),
                lineHeight: 1,
              }}
            >
              {t('remoteClients.labels.local')}
            </Typography>
          </Box>

          {active ? (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.4 }}>
              <CircleCheck size={11} style={{ color: primary }} />
              <Typography
                sx={{
                  fontSize: '0.58rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  color: primary,
                  lineHeight: 1,
                }}
              >
                {t('remoteClients.labels.activeTarget')}
              </Typography>
            </Box>
          ) : (
            <Tooltip title={t('remoteClients.actions.use')} arrow>
              <IconButton
                size="small"
                onClick={onUse}
                aria-label={t('remoteClients.actions.useLocalAria')}
                sx={{
                  width: 28,
                  height: 28,
                  borderRadius: 1.5,
                  bgcolor: alpha(primary, isDark ? 0.16 : 0.1),
                  color: primary,
                  '&:hover': {
                    bgcolor: alpha(primary, isDark ? 0.24 : 0.16),
                  },
                }}
              >
                <Power size={14} />
              </IconButton>
            </Tooltip>
          )}
        </Box>

        <Typography variant="subtitle1" fontWeight={700} noWrap sx={{ lineHeight: 1.3, mb: 0.25 }}>
          {t('remoteClients.localBackend.title')}
        </Typography>

        <Typography
          sx={{
            fontSize: '0.7rem',
            color: 'text.disabled',
            lineHeight: 1.4,
          }}
        >
          {active
            ? t('remoteClients.switcher.localHelper')
            : t('remoteClients.localBackend.fallback')}
        </Typography>
      </Box>
    </Box>
  )
}

import { useTranslation } from 'react-i18next'
import { Box, IconButton, Tooltip, Typography, useTheme, alpha } from '@mui/material'
import {
  CheckCircle2,
  CircleAlert,
  CircleCheck,
  Edit,
  Power,
  RefreshCw,
  Server,
  Trash2,
  WifiOff,
} from 'lucide-react'
import type { RemoteBackendClient } from '../services/remoteBackends/types'

interface ClientStatus {
  label: string
  accent: string
  icon: ReturnType<typeof getStatusIconNode>
}

const STATUS_ACCENT = {
  online: '#059669',
  offline: '#ef4444',
  incompatible: '#d97706',
  checking: '#0891b2',
  unknown: '#6b7280',
} as const

type StatusKey = keyof typeof STATUS_ACCENT

function getStatusIconNode(key: StatusKey) {
  switch (key) {
    case 'online':
      return <CheckCircle2 size={13} />
    case 'offline':
      return <WifiOff size={13} />
    case 'incompatible':
      return <CircleAlert size={13} />
    case 'checking':
      return <RefreshCw size={13} />
    default:
      return <Server size={13} />
  }
}

function resolveStatus(
  client: RemoteBackendClient,
  t: (key: string) => string,
  isChecking: boolean
): ClientStatus & { key: StatusKey } {
  if (isChecking) {
    return {
      key: 'checking',
      label: t('remoteClients.status.checking'),
      accent: STATUS_ACCENT.checking,
      icon: getStatusIconNode('checking'),
    }
  }
  if (client.health.compatibility === 'incompatible') {
    return {
      key: 'incompatible',
      label: t('remoteClients.status.incompatible'),
      accent: STATUS_ACCENT.incompatible,
      icon: getStatusIconNode('incompatible'),
    }
  }
  if (client.health.status === 'online') {
    return {
      key: 'online',
      label: t('remoteClients.status.online'),
      accent: STATUS_ACCENT.online,
      icon: getStatusIconNode('online'),
    }
  }
  if (client.health.status === 'offline') {
    return {
      key: 'offline',
      label: t('remoteClients.status.offline'),
      accent: STATUS_ACCENT.offline,
      icon: getStatusIconNode('offline'),
    }
  }
  return {
    key: 'unknown',
    label: t('remoteClients.status.unknown'),
    accent: STATUS_ACCENT.unknown,
    icon: getStatusIconNode('unknown'),
  }
}

function formatDate(value: string | null | undefined, fallback: string): string {
  if (!value) return fallback
  const date = new Date(value)
  if (Number.isNaN(date.valueOf())) return fallback
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

interface RemoteClientCardProps {
  client: RemoteBackendClient
  active: boolean
  checking: boolean
  onCheck: (client: RemoteBackendClient) => void
  onUse: (client: RemoteBackendClient) => void
  onEdit: (client: RemoteBackendClient) => void
  onDelete: (client: RemoteBackendClient) => void
}

export default function RemoteClientCard({
  client,
  active,
  checking,
  onCheck,
  onUse,
  onEdit,
  onDelete,
}: RemoteClientCardProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const status = resolveStatus(client, t, checking)
  const canUse = client.health.compatibility !== 'incompatible'
  const primary = theme.palette.primary.main

  const iconBtnSx = {
    width: { xs: 40, sm: 34 },
    height: { xs: 40, sm: 34 },
    borderRadius: 1.5,
    color: 'text.secondary',
    '&:hover': {
      bgcolor: isDark ? alpha('#fff', 0.07) : alpha('#000', 0.06),
      color: 'text.primary',
    },
    '&.Mui-disabled': { opacity: 0.28 },
  }

  const coloredIconBtnSx = (colorKey: 'primary' | 'success' | 'error' | 'warning' | 'info') => {
    const color = theme.palette[colorKey].main
    return {
      ...iconBtnSx,
      color: alpha(color, isDark ? 0.65 : 0.55),
      '&:hover': {
        bgcolor: alpha(color, isDark ? 0.12 : 0.09),
        color,
      },
    }
  }

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
              ? `0 0 0 1px ${alpha(status.accent, 0.4)}, 0 8px 24px ${alpha('#000', 0.3)}, 0 2px 8px ${alpha(status.accent, 0.1)}`
              : `0 0 0 1px ${alpha(status.accent, 0.3)}, 0 8px 24px ${alpha('#000', 0.12)}, 0 2px 8px ${alpha(status.accent, 0.08)}`,
        },
      }}
    >
      <Box
        sx={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          px: { xs: 1.75, sm: 2 },
          pt: { xs: 1.75, sm: 2 },
          pb: { xs: 1.5, sm: 1.75 },
        }}
      >
        {/* ── Header ── */}
        <Box sx={{ mb: 1.5 }}>
          {/* Status eyebrow + active badge */}
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              mb: 0.5,
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <Box sx={{ color: status.accent, display: 'flex', alignItems: 'center' }}>
                {status.icon}
              </Box>
              <Typography
                sx={{
                  fontSize: '0.6rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  color: alpha(status.accent, 0.9),
                  lineHeight: 1,
                }}
              >
                {status.label}
              </Typography>
            </Box>

            {active && (
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
            )}
          </Box>

          {/* Client name */}
          <Typography
            variant="subtitle1"
            fontWeight={700}
            noWrap
            title={client.name}
            sx={{ lineHeight: 1.3, mb: 0.25 }}
          >
            {client.name}
          </Typography>

          {/* API URL */}
          <Typography
            title={client.apiBaseUrl}
            sx={{
              fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
              fontSize: '0.7rem',
              color: 'text.disabled',
              wordBreak: 'break-all',
              lineHeight: 1.4,
            }}
          >
            {client.apiBaseUrl}
          </Typography>
        </Box>

        {/* ── Metadata band: last check + version ── */}
        <Box
          sx={{
            borderRadius: 1.5,
            border: '1px solid',
            borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
            overflow: 'hidden',
            mb: 1.5,
            bgcolor: isDark ? alpha('#fff', 0.025) : alpha('#000', 0.018),
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
          }}
        >
          {[
            {
              label: t('remoteClients.card.lastCheck', 'Last check'),
              value: formatDate(client.health.checkedAt, t('common.never')),
            },
            {
              label: t('remoteClients.card.version', 'Version'),
              value: client.health.appVersion
                ? t('remoteClients.version', { version: client.health.appVersion })
                : '—',
            },
          ].map((col, i) => (
            <Box
              key={col.label + i}
              sx={{
                px: { xs: 1.25, sm: 1.5 },
                py: { xs: 1, sm: 0.875 },
                borderRight: i === 0 ? '1px solid' : 0,
                borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                minWidth: 0,
              }}
            >
              <Typography
                noWrap
                sx={{
                  fontSize: '0.55rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  color: 'text.disabled',
                  lineHeight: 1,
                  mb: 0.5,
                }}
              >
                {col.label}
              </Typography>
              <Typography
                noWrap
                sx={{
                  fontSize: '0.78rem',
                  fontWeight: 600,
                  fontVariantNumeric: 'tabular-nums',
                  lineHeight: 1.2,
                }}
              >
                {col.value}
              </Typography>
            </Box>
          ))}
        </Box>

        {/* ── Error / incompatibility ── */}
        {client.health.error && (
          <Box
            sx={{
              mb: 1.5,
              px: 1.25,
              py: 0.875,
              bgcolor: alpha(theme.palette.error.main, isDark ? 0.1 : 0.06),
              borderRadius: 1.5,
              border: '1px solid',
              borderColor: alpha(theme.palette.error.main, 0.25),
            }}
          >
            <Typography
              sx={{
                fontSize: '0.7rem',
                color: 'error.main',
                wordBreak: 'break-word',
                lineHeight: 1.4,
              }}
            >
              {client.health.error}
            </Typography>
          </Box>
        )}
        {client.health.compatibility === 'incompatible' && client.health.compatibilityMessage && (
          <Box
            sx={{
              mb: 1.5,
              px: 1.25,
              py: 0.875,
              bgcolor: alpha(theme.palette.warning.main, isDark ? 0.1 : 0.06),
              borderRadius: 1.5,
              border: '1px solid',
              borderColor: alpha(theme.palette.warning.main, 0.25),
            }}
          >
            <Typography
              sx={{
                fontSize: '0.7rem',
                color: 'warning.main',
                wordBreak: 'break-word',
                lineHeight: 1.4,
              }}
            >
              {client.health.compatibilityMessage}
            </Typography>
          </Box>
        )}

        {/* ── Action bar ── */}
        <Box
          sx={{
            mt: 'auto',
            display: 'flex',
            alignItems: 'center',
            gap: { xs: 0.75, sm: 0.5 },
            pt: { xs: 1.5, sm: 1.25 },
            borderTop: '1px solid',
            borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
          }}
        >
          {/* Left cluster: check + use */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 0.5, sm: 0.25 }, flex: 1 }}>
            <Tooltip title={t('remoteClients.actions.check')} arrow>
              <span>
                <IconButton
                  size="small"
                  aria-label={t('remoteClients.actions.checkAria', { name: client.name })}
                  onClick={() => onCheck(client)}
                  disabled={checking}
                  sx={coloredIconBtnSx('info')}
                >
                  <RefreshCw size={16} />
                </IconButton>
              </span>
            </Tooltip>
            <Tooltip
              title={
                active
                  ? ''
                  : canUse
                    ? t('remoteClients.actions.use')
                    : t('remoteClients.status.incompatible')
              }
              arrow
            >
              <span>
                <IconButton
                  size="small"
                  aria-label={t('remoteClients.actions.useAria', { name: client.name })}
                  onClick={() => onUse(client)}
                  disabled={!canUse || active}
                  sx={coloredIconBtnSx('primary')}
                >
                  <Power size={16} />
                </IconButton>
              </span>
            </Tooltip>
          </Box>

          {/* Right cluster: edit / delete */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 0.5, sm: 0.25 } }}>
            <Box
              sx={{
                width: '1px',
                height: 18,
                bgcolor: isDark ? alpha('#fff', 0.1) : alpha('#000', 0.1),
                mx: 0.25,
                flexShrink: 0,
              }}
            />
            <Tooltip title={t('remoteClients.actions.edit')} arrow>
              <IconButton
                size="small"
                aria-label={t('remoteClients.actions.editAria', { name: client.name })}
                onClick={() => onEdit(client)}
                sx={iconBtnSx}
              >
                <Edit size={16} />
              </IconButton>
            </Tooltip>
            <Tooltip title={t('remoteClients.actions.delete')} arrow>
              <IconButton
                size="small"
                aria-label={t('remoteClients.actions.deleteAria', { name: client.name })}
                onClick={() => onDelete(client)}
                sx={{
                  ...iconBtnSx,
                  color: alpha(theme.palette.error.main, 0.6),
                  '&:hover': {
                    color: theme.palette.error.main,
                    bgcolor: alpha(theme.palette.error.main, isDark ? 0.15 : 0.1),
                  },
                }}
              >
                <Trash2 size={16} />
              </IconButton>
            </Tooltip>
          </Box>
        </Box>
      </Box>
    </Box>
  )
}

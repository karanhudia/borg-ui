import { useTranslation } from 'react-i18next'
import {
  Box,
  Typography,
  IconButton,
  Tooltip,
  LinearProgress,
  useTheme,
  alpha,
} from '@mui/material'
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  Edit,
  Trash2,
  RefreshCw,
  HardDrive,
  Network,
  Key,
} from 'lucide-react'

interface StorageInfo {
  total: number
  total_formatted: string
  used: number
  used_formatted: string
  available: number
  available_formatted: string
  percent_used: number
  last_check?: string | null
}

interface RemoteMachine {
  id: number
  ssh_key_id: number
  ssh_key_name: string
  host: string
  username: string
  port: number
  use_sftp_mode: boolean
  use_sudo: boolean
  default_path?: string
  mount_point?: string
  status: string
  last_test?: string
  last_success?: string
  error_message?: string
  storage?: StorageInfo | null
  created_at: string
}

interface RemoteMachineCardProps {
  machine: RemoteMachine
  onEdit: (machine: RemoteMachine) => void
  onDelete: (machine: RemoteMachine) => void
  onRefreshStorage: (machine: RemoteMachine) => void
  onTestConnection: (machine: RemoteMachine) => void
  onDeployKey: (machine: RemoteMachine) => void
  canManageConnections?: boolean
}

const STATUS_ACCENT: Record<string, string> = {
  connected: '#059669',
  failed: '#ef4444',
  testing: '#f59e0b',
}

const getStatusAccent = (status: string) => STATUS_ACCENT[status] ?? '#6b7280'

const getStatusIcon = (status: string) => {
  switch (status) {
    case 'connected':
      return <CheckCircle size={13} />
    case 'failed':
      return <XCircle size={13} />
    default:
      return <AlertTriangle size={13} />
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const getStorageBarColor = (pct: number, theme: any) => {
  if (pct > 90) return theme.palette.error.main
  if (pct > 75) return theme.palette.warning.main
  return theme.palette.success.main
}

export default function RemoteMachineCard({
  machine,
  onEdit,
  onDelete,
  onRefreshStorage,
  onTestConnection,
  onDeployKey,
  canManageConnections = true,
}: RemoteMachineCardProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const accent = getStatusAccent(machine.status)

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

  const hasMeta =
    machine.default_path || (machine.mount_point && machine.mount_point !== machine.host)

  return (
    <Box
      sx={{
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        borderRadius: 2,
        bgcolor: 'background.paper',
        boxShadow: isDark
          ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 4px 16px ${alpha('#000', 0.25)}`
          : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 8px ${alpha('#000', 0.07)}`,
        transition: 'all 200ms cubic-bezier(0.16,1,0.3,1)',
        '&:hover': {
          transform: 'translateY(-2px)',
          boxShadow: isDark
            ? `0 0 0 1px ${alpha(accent, 0.4)}, 0 8px 24px ${alpha('#000', 0.3)}, 0 2px 8px ${alpha(accent, 0.1)}`
            : `0 0 0 1px ${alpha(accent, 0.3)}, 0 8px 24px ${alpha('#000', 0.12)}, 0 2px 8px ${alpha(accent, 0.08)}`,
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
          {/* Status label row */}
          <Box
            sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <Box sx={{ color: accent, display: 'flex', alignItems: 'center' }}>
                {getStatusIcon(machine.status)}
              </Box>
              <Typography
                sx={{
                  fontSize: '0.6rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  color: alpha(accent, 0.9),
                  lineHeight: 1,
                }}
              >
                {machine.status}
              </Typography>
            </Box>

            {/* SSH key badge — right of status row, small */}
            <Typography
              sx={{
                fontSize: '0.58rem',
                fontWeight: 500,
                color: 'text.disabled',
                letterSpacing: '0.02em',
                flexShrink: 0,
              }}
            >
              {machine.ssh_key_name}
            </Typography>
          </Box>

          {/* Machine name — full width, no competing badge */}
          <Typography
            variant="subtitle1"
            fontWeight={700}
            noWrap
            title={machine.mount_point || machine.host}
            sx={{ lineHeight: 1.3, mb: 0.25 }}
          >
            {machine.mount_point || machine.host}
          </Typography>

          {/* Connection string */}
          <Typography
            noWrap
            title={`${machine.username}@${machine.host}:${machine.port}`}
            sx={{
              fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
              fontSize: '0.7rem',
              color: 'text.disabled',
            }}
          >
            {machine.username}@{machine.host}:{machine.port}
          </Typography>
        </Box>

        {/* ── Storage Stats Band ── */}
        {machine.storage ? (
          <Box
            sx={{
              borderRadius: 1.5,
              border: '1px solid',
              borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
              overflow: 'hidden',
              mb: 1.5,
              bgcolor: isDark ? alpha('#fff', 0.025) : alpha('#000', 0.018),
            }}
          >
            {/* Two-column stats: Used + Free (Total shown inline with bar) */}
            <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)' }}>
              {[
                {
                  label: t('remoteMachine.used'),
                  value: machine.storage.used_formatted,
                  color: theme.palette.warning.main,
                },
                {
                  label: t('remoteMachine.free'),
                  value: machine.storage.available_formatted,
                  color: theme.palette.success.main,
                },
              ].map((col, i) => (
                <Box
                  key={col.label}
                  sx={{
                    px: { xs: 1.25, sm: 1.5 },
                    py: { xs: 1.25, sm: 1 },
                    borderRight: i === 0 ? '1px solid' : 0,
                    borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                    minWidth: 0,
                  }}
                >
                  <Typography
                    noWrap
                    sx={{
                      fontSize: '0.6rem',
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      letterSpacing: '0.06em',
                      color: alpha(col.color, 0.75),
                      lineHeight: 1,
                      mb: 0.5,
                    }}
                  >
                    {col.label}
                  </Typography>
                  <Typography
                    noWrap
                    sx={{
                      fontSize: { xs: '0.9rem', sm: '0.85rem' },
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

            {/* Usage bar with total inline */}
            <Box
              sx={{
                px: { xs: 1.25, sm: 1.5 },
                pb: 1,
                borderTop: '1px solid',
                borderColor: isDark ? alpha('#fff', 0.05) : alpha('#000', 0.06),
                pt: 0.75,
              }}
            >
              <Box
                sx={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  mb: 0.5,
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                  <Typography sx={{ fontSize: '0.58rem', color: 'text.disabled', lineHeight: 1 }}>
                    {machine.storage.percent_used.toFixed(1)}% used
                  </Typography>
                </Box>
                <Typography
                  sx={{
                    fontSize: '0.58rem',
                    color: 'text.disabled',
                    lineHeight: 1,
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {machine.storage.total_formatted} total
                </Typography>
              </Box>
              <LinearProgress
                variant="determinate"
                value={machine.storage.percent_used}
                sx={{
                  height: 5,
                  borderRadius: 1,
                  bgcolor: isDark ? alpha('#fff', 0.08) : alpha('#000', 0.08),
                  '& .MuiLinearProgress-bar': {
                    bgcolor: getStorageBarColor(machine.storage.percent_used, theme),
                    borderRadius: 1,
                  },
                }}
              />
            </Box>
          </Box>
        ) : (
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 0.75,
              px: 1.25,
              py: 0.875,
              mb: 1.5,
              borderRadius: 1.5,
              border: '1px solid',
              borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
              bgcolor: isDark ? alpha('#fff', 0.025) : alpha('#000', 0.018),
            }}
          >
            <HardDrive size={14} style={{ opacity: 0.4, flexShrink: 0 }} />
            <Typography noWrap sx={{ fontSize: '0.75rem', color: 'text.disabled', flex: 1 }}>
              {t('remoteMachine.noStorageInfo')}
            </Typography>
            <Tooltip title={t('remoteMachine.refreshStorage')} arrow>
              <IconButton
                aria-label={t('remoteMachine.refreshStorage')}
                onClick={() => onRefreshStorage(machine)}
                sx={{
                  width: { xs: 36, sm: 30 },
                  height: { xs: 36, sm: 30 },
                  flexShrink: 0,
                  color: 'text.disabled',
                  '&:hover': { color: 'text.secondary' },
                }}
              >
                <RefreshCw size={14} />
              </IconButton>
            </Tooltip>
          </Box>
        )}

        {/* ── Secondary Metadata ── */}
        {hasMeta && (
          <Box
            sx={{
              display: 'flex',
              flexDirection: 'column',
              gap: 0.4,
              mb: 1.5,
              px: 0.25,
            }}
          >
            {machine.default_path && (
              <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.5, minWidth: 0 }}>
                <Typography
                  sx={{ fontSize: '0.68rem', color: 'text.disabled', lineHeight: 1, flexShrink: 0 }}
                >
                  {t('remoteMachine.defaultPath')}:
                </Typography>
                <Typography
                  noWrap
                  sx={{
                    fontSize: '0.68rem',
                    fontWeight: 600,
                    color: 'text.secondary',
                    fontFamily: 'monospace',
                    lineHeight: 1,
                    minWidth: 0,
                  }}
                >
                  {machine.default_path}
                </Typography>
              </Box>
            )}
            {machine.mount_point && machine.mount_point !== machine.host && (
              <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.5, minWidth: 0 }}>
                <Typography
                  sx={{ fontSize: '0.68rem', color: 'text.disabled', lineHeight: 1, flexShrink: 0 }}
                >
                  {t('remoteMachineCard.mountPoint')}:
                </Typography>
                <Typography
                  noWrap
                  sx={{
                    fontSize: '0.68rem',
                    fontWeight: 600,
                    color: 'primary.main',
                    fontFamily: 'monospace',
                    lineHeight: 1,
                    minWidth: 0,
                  }}
                >
                  {machine.mount_point}
                </Typography>
              </Box>
            )}
          </Box>
        )}

        {/* ── Error Message ── */}
        {machine.error_message && (
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
              {machine.error_message}
            </Typography>
          </Box>
        )}

        {/* ── Action Bar ── */}
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
          {/* Left cluster */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 0.5, sm: 0.25 }, flex: 1 }}>
            <Tooltip title={t('remoteMachine.actions.testConnection')} arrow>
              <IconButton
                size="small"
                aria-label={t('remoteMachine.actions.testConnection')}
                onClick={() => onTestConnection(machine)}
                sx={coloredIconBtnSx('primary')}
              >
                <Network size={16} />
              </IconButton>
            </Tooltip>
            <Tooltip title={t('remoteMachine.actions.refreshStorage')} arrow>
              <IconButton
                size="small"
                aria-label={t('remoteMachine.actions.refreshStorage')}
                onClick={() => onRefreshStorage(machine)}
                sx={coloredIconBtnSx('info')}
              >
                <RefreshCw size={16} />
              </IconButton>
            </Tooltip>
            {canManageConnections && (
              <Tooltip title={t('remoteMachineCard.actions.deploy')} arrow>
                <IconButton
                  size="small"
                  aria-label={t('remoteMachineCard.actions.deploy')}
                  onClick={() => onDeployKey(machine)}
                  sx={coloredIconBtnSx('success')}
                >
                  <Key size={16} />
                </IconButton>
              </Tooltip>
            )}
          </Box>

          {/* Right cluster — edit / delete */}
          {canManageConnections && (
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
              <Tooltip title={t('remoteMachineCard.actions.edit')} arrow>
                <IconButton size="small" aria-label={t('remoteMachineCard.actions.edit')} onClick={() => onEdit(machine)} sx={iconBtnSx}>
                  <Edit size={16} />
                </IconButton>
              </Tooltip>
              <Tooltip title={t('remoteMachineCard.actions.delete')} arrow>
                <IconButton
                  size="small"
                  aria-label={t('remoteMachineCard.actions.delete')}
                  onClick={() => onDelete(machine)}
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
          )}
        </Box>
      </Box>
    </Box>
  )
}

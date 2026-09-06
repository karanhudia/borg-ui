import { Box, Button, Stack, Tooltip, Typography, alpha, useTheme } from '@mui/material'
import { Database, HardDrive, Layers, RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDistanceToNow } from 'date-fns'
import { formatBytes, parseBackendDate } from '../../utils/dateUtils'
import type { HubTotals } from '../../types/operations'

interface HubSummaryProps {
  totals: HubTotals
  lastReconcileAt: string | null
  reconcileIntervalMinutes: number
  canManage: boolean
  reconciling?: boolean
  onReconcile: () => void
}

function Stat({
  icon,
  primary,
  secondary,
}: {
  icon: React.ReactNode
  primary: string
  secondary?: string
}) {
  const theme = useTheme()
  return (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', minWidth: 0 }}>
      <Box
        aria-hidden
        sx={{
          width: 36,
          height: 36,
          borderRadius: '10px',
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: theme.palette.primary.main,
          bgcolor: alpha(theme.palette.primary.main, theme.palette.mode === 'dark' ? 0.16 : 0.08),
        }}
      >
        {icon}
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <Typography
          variant="subtitle2"
          sx={{ fontWeight: 700, lineHeight: 1.3, fontVariantNumeric: 'tabular-nums' }}
        >
          {primary}
        </Typography>
        {secondary && (
          <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
            {secondary}
          </Typography>
        )}
      </Box>
    </Stack>
  )
}

// What every repository's derived data adds up to, and when the reconcile
// that keeps it honest last ran. The strip sits above the per-repository
// table so the totals and the per-row numbers read as one thing.
export default function HubSummary({
  totals,
  lastReconcileAt,
  reconcileIntervalMinutes,
  canManage,
  reconciling = false,
  onReconcile,
}: HubSummaryProps) {
  const { t } = useTranslation()
  const theme = useTheme()

  const reconcileText =
    reconcileIntervalMinutes <= 0
      ? t('operations.background.hub.reconcileOff')
      : lastReconcileAt
        ? t('operations.background.hub.reconcileEvery', {
            minutes: reconcileIntervalMinutes,
            ago: formatDistanceToNow(parseBackendDate(lastReconcileAt), { addSuffix: true }),
          })
        : t('operations.background.hub.reconcileNever', { minutes: reconcileIntervalMinutes })

  return (
    <Box
      sx={{
        border: `1px solid ${theme.palette.divider}`,
        borderRadius: 2,
        bgcolor: 'background.paper',
        px: 2.5,
        py: 2,
      }}
    >
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, 1fr))' },
          gap: 2,
        }}
      >
        <Stat
          icon={<HardDrive size={18} />}
          primary={t('operations.background.hub.repositories', { count: totals.repositories })}
        />
        <Stat
          icon={<Layers size={18} />}
          primary={t('operations.background.hub.archives', { count: totals.archives })}
        />
        <Stat
          icon={<Database size={18} />}
          primary={t('operations.background.hub.rows', { count: totals.history_rows })}
          secondary={
            totals.history_bytes != null
              ? t('operations.background.hub.bytes', { size: formatBytes(totals.history_bytes) })
              : undefined
          }
        />
      </Box>
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={1.5}
        sx={{
          alignItems: { md: 'center' },
          justifyContent: 'space-between',
          mt: 2,
          pt: 2,
          borderTop: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="body2">{reconcileText}</Typography>
          <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
            {t('operations.background.hub.reconcileHelp')}
          </Typography>
        </Box>
        <Tooltip title={canManage ? '' : t('operations.background.hub.reconcileAdminOnly')}>
          <span>
            <Button
              size="small"
              variant="outlined"
              disabled={!canManage || reconciling}
              startIcon={<RefreshCw size={14} />}
              onClick={onReconcile}
              sx={{ flexShrink: 0, whiteSpace: 'nowrap' }}
            >
              {t('operations.background.hub.reconcileNow')}
            </Button>
          </span>
        </Tooltip>
      </Stack>
    </Box>
  )
}

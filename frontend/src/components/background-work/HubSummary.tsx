import { Box, Button, Chip, Stack, Tooltip, Typography, alpha, useTheme } from '@mui/material'
import { AlertTriangle, Database, HardDrive, Layers, RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDistanceToNow } from 'date-fns'
import { formatBytes, parseBackendDate } from '../../utils/dateUtils'
import type { HubTotals } from '../../types/operations'
import type { AttentionCounts, AttentionReason } from './hubRows'

interface HubSummaryProps {
  totals: HubTotals
  attention: AttentionCounts
  onAttention: (reason: AttentionReason) => void
  lastReconcileAt: string | null
  reconcileIntervalMinutes: number
  canManage: boolean
  reconciling?: boolean
  onReconcile: () => void
}

const ATTENTION_ORDER: AttentionReason[] = ['stale', 'never', 'history', 'running']
const ATTENTION_KEY: Record<AttentionReason, string> = {
  stale: 'operations.background.hub.attentionStale',
  never: 'operations.background.hub.attentionNever',
  history: 'operations.background.hub.attentionHistory',
  running: 'operations.background.hub.attentionRunning',
}

function Stat({
  icon,
  primary,
  secondary,
  tone = 'primary',
}: {
  icon: React.ReactNode
  primary: string
  secondary?: React.ReactNode
  tone?: 'primary' | 'warning'
}) {
  const theme = useTheme()
  const color = theme.palette[tone].main
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
          color,
          bgcolor: alpha(color, theme.palette.mode === 'dark' ? 0.16 : 0.08),
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
        {typeof secondary === 'string' ? (
          <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
            {secondary}
          </Typography>
        ) : (
          secondary
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
  attention,
  onAttention,
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
          gridTemplateColumns: {
            xs: '1fr',
            sm: 'repeat(2, minmax(0, 1fr))',
            lg: 'repeat(4, minmax(0, 1fr))',
          },
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
        <Stat
          icon={<AlertTriangle size={18} />}
          tone={attention.total > 0 ? 'warning' : 'primary'}
          primary={t('operations.background.hub.attention', { count: attention.total })}
          secondary={
            attention.total > 0 ? (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
                {ATTENTION_ORDER.filter((reason) => attention[reason] > 0).map((reason) => (
                  <Chip
                    key={reason}
                    size="small"
                    variant="outlined"
                    clickable
                    onClick={() => onAttention(reason)}
                    label={t(ATTENTION_KEY[reason], { count: attention[reason] })}
                    sx={{ height: 22, fontSize: '0.7rem' }}
                  />
                ))}
              </Box>
            ) : undefined
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

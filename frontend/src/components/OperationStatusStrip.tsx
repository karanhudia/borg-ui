import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Box, Typography, Tooltip, alpha, useTheme } from '@mui/material'
import { AlertTriangle, Check, Loader2, XCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDistanceToNow } from 'date-fns'
import { parseBackendDate } from '../utils/dateUtils'
import { archivesAPI } from '../services/api'
import { useOperationEvents } from '../hooks/useOperationEvents'

interface OperationStatusStripProps {
  repositoryId: number
}

const FAILED_STATUSES = new Set(['failed', 'cancelled'])

export default function OperationStatusStrip({ repositoryId }: OperationStatusStripProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const queryClient = useQueryClient()
  const queryKey = ['status-strip', repositoryId] as const

  const { data } = useQuery({
    queryKey,
    queryFn: () => archivesAPI.getStatusStrip(repositoryId).then((r) => r.data),
    refetchInterval: 30000,
  })

  useOperationEvents(
    (op) => {
      if (op.repository_id === repositoryId) {
        queryClient.invalidateQueries({ queryKey })
      }
    },
    () => {}
  )

  if (!data || data.cells.length === 0) return null

  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, mb: 1.5 }}>
      {data.cells.map((cell) => (
        <Tooltip
          key={cell.cell}
          title={
            cell.completed_at
              ? parseBackendDate(cell.completed_at).toLocaleString()
              : t('operations.background.never')
          }
        >
          <Box
            data-testid={`status-strip-cell-${cell.cell}`}
            data-overdue={cell.overdue === true}
            data-status={cell.status ?? 'none'}
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 0.5,
              px: 1,
              py: 0.5,
              borderRadius: 1,
              bgcolor:
                cell.status && FAILED_STATUSES.has(cell.status)
                  ? alpha(theme.palette.error.main, 0.12)
                  : cell.overdue
                    ? alpha(theme.palette.warning.main, 0.12)
                    : isDark
                      ? alpha('#fff', 0.03)
                      : alpha('#000', 0.02),
            }}
          >
            {cell.running ? (
              <Loader2 size={12} className="animate-spin" />
            ) : cell.status && FAILED_STATUSES.has(cell.status) ? (
              <XCircle size={12} color={theme.palette.error.main} />
            ) : cell.overdue ? (
              <AlertTriangle size={12} color={theme.palette.warning.main} />
            ) : cell.status ? (
              <Check size={12} color={theme.palette.success.main} />
            ) : null}
            <Typography variant="caption" sx={{ fontWeight: 600 }}>
              {t(`operations.strip.${cell.cell}`)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {cell.running
                ? t('operations.background.syncing')
                : cell.completed_at
                  ? formatDistanceToNow(parseBackendDate(cell.completed_at), { addSuffix: true })
                  : t('operations.background.never')}
            </Typography>
          </Box>
        </Tooltip>
      ))}
    </Box>
  )
}

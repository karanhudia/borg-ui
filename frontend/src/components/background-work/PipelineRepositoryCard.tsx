import {
  Box,
  Typography,
  LinearProgress,
  IconButton,
  Tooltip,
  alpha,
  useTheme,
} from '@mui/material'
import { RotateCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatElapsedTime } from '../../utils/dateUtils'
import type { OperationItem } from '../../types/operations'

interface PipelineRepositoryCardProps {
  operation: OperationItem
  onRetry?: (operationId: number) => void
}

export default function PipelineRepositoryCard({
  operation,
  onRetry,
}: PipelineRepositoryCardProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const isFailed = operation.status === 'failed'
  const isRunning = operation.status === 'running'

  return (
    <Box
      sx={{
        border: '1px solid',
        borderColor: isFailed
          ? alpha(theme.palette.error.main, 0.4)
          : isDark
            ? alpha('#fff', 0.08)
            : alpha('#000', 0.08),
        borderRadius: 1.5,
        p: 1,
        mb: 1,
        bgcolor: isDark ? alpha('#fff', 0.02) : alpha('#000', 0.015),
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography variant="body2" fontWeight={600} noWrap>
          {operation.repository ?? t('operations.background.systemRow')}
        </Typography>
        {isFailed && onRetry && (
          <Tooltip title={t('operations.background.retry')}>
            <IconButton
              size="small"
              aria-label={t('operations.background.retry')}
              onClick={() => onRetry(operation.id)}
            >
              <RotateCw size={14} />
            </IconButton>
          </Tooltip>
        )}
      </Box>
      <Typography variant="caption" color="text.secondary">
        {operation.status === 'queued'
          ? t('operations.background.waiting')
          : isRunning && operation.started_at
            ? formatElapsedTime(operation.started_at)
            : isFailed
              ? t('operations.background.failed')
              : t(`operations.status.${operation.status}`)}
      </Typography>
      {isRunning && operation.progress_percent != null && (
        <LinearProgress
          variant="determinate"
          value={operation.progress_percent}
          sx={{ mt: 0.5, height: 4, borderRadius: 2 }}
        />
      )}
    </Box>
  )
}

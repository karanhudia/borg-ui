import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link as RouterLink } from 'react-router-dom'
import {
  Box,
  Button,
  IconButton,
  LinearProgress,
  Stack,
  Tooltip,
  Typography,
  alpha,
} from '@mui/material'
import { AlertTriangle, CheckCircle2, Loader2, RotateCcw, X } from 'lucide-react'
import { restoreAPI } from '../../services/api'
import { translateBackendKey } from '../../utils/translateBackendKey'

export interface RestoreStatus {
  id: number
  status: string
  destination: string
  error_message?: string | null
  progress_details?: {
    nfiles: number
    current_file: string
    progress_percent: number
  }
}

const TERMINAL = new Set(['completed', 'completed_with_warnings', 'failed', 'cancelled'])

interface RestoreProgressPanelProps {
  jobId: number
  repositoryId: number
  onDismiss: () => void
}

/** Bottom-right floating panel, the same slot the Files tab uses for its
 *  selection bar, so a restore never shifts the page. It follows one job
 *  from pending through running to its final state and stays there until
 *  dismissed, so a fast restore does not vanish before anyone reads it. */
export default function RestoreProgressPanel({
  jobId,
  repositoryId,
  onDismiss,
}: RestoreProgressPanelProps) {
  const { data: job, isError } = useQuery({
    queryKey: ['restore-status', jobId],
    queryFn: () => restoreAPI.getRestoreStatus(jobId).then((res) => res.data as RestoreStatus),
    refetchInterval: (query) => (TERMINAL.has(query.state.data?.status ?? '') ? false : 2000),
  })
  return (
    <RestoreProgressPanelView
      job={job}
      statusUnavailable={isError}
      repositoryId={repositoryId}
      onDismiss={onDismiss}
    />
  )
}

interface RestoreProgressPanelViewProps {
  job: RestoreStatus | undefined
  /** The status request itself failed. The job may still be running, so
   *  this is not the same as a failed restore. */
  statusUnavailable?: boolean
  repositoryId: number
  onDismiss: () => void
}

/** The panel without polling, so stories can show each state. */
export function RestoreProgressPanelView({
  job,
  statusUnavailable = false,
  repositoryId,
  onDismiss,
}: RestoreProgressPanelViewProps) {
  const { t } = useTranslation()
  const status = statusUnavailable && !job ? 'unavailable' : (job?.status ?? 'pending')
  const done = TERMINAL.has(status) || status === 'unavailable'
  const failed = status === 'failed' || status === 'cancelled' || status === 'unavailable'
  const percent = job?.progress_details?.progress_percent ?? 0
  const nfiles = job?.progress_details?.nfiles ?? 0

  const title = t(`archives.restorePanel.${status}`, {
    defaultValue: t('archives.restorePanel.running'),
  })
  const Icon = failed ? AlertTriangle : done ? CheckCircle2 : Loader2

  return (
    <Box
      role="status"
      aria-live="polite"
      aria-label={t('archives.restorePanel.label')}
      sx={{
        position: 'fixed',
        right: { xs: 12, sm: 24 },
        bottom: { xs: 12, sm: 24 },
        left: { xs: 12, sm: 'auto' },
        width: { sm: 380 },
        maxWidth: 'calc(100vw - 24px)',
        zIndex: (theme) => theme.zIndex.appBar + 1,
        borderRadius: 3,
        overflow: 'hidden',
        color: 'common.white',
        bgcolor: (theme) =>
          theme.palette.mode === 'dark' ? theme.palette.grey[800] : theme.palette.grey[900],
        boxShadow: (theme) =>
          `0 12px 32px ${alpha(theme.palette.common.black, 0.28)}, 0 0 0 1px ${alpha(theme.palette.common.white, 0.08)}`,
        '@keyframes restore-panel-in': {
          from: { opacity: 0, transform: 'translateY(12px)' },
          to: { opacity: 1, transform: 'translateY(0)' },
        },
        '@keyframes restore-panel-spin': { to: { transform: 'rotate(360deg)' } },
        animation: 'restore-panel-in 180ms ease-out',
      }}
    >
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', pl: 2, pr: 1, py: 1 }}>
        <Box
          component={Icon}
          size={16}
          aria-hidden
          sx={{
            flexShrink: 0,
            color: failed ? 'error.light' : done ? 'success.light' : 'inherit',
            animation: done ? undefined : 'restore-panel-spin 1s linear infinite',
          }}
        />
        <Typography variant="body2" sx={{ fontWeight: 600, flex: 1, minWidth: 0 }} noWrap>
          {title}
        </Typography>
        <Tooltip title={t('archives.restorePanel.dismiss')}>
          <IconButton
            size="small"
            aria-label={t('archives.restorePanel.dismiss')}
            onClick={onDismiss}
            sx={{ color: 'inherit', opacity: 0.8, '&:hover': { opacity: 1 } }}
          >
            <X size={16} />
          </IconButton>
        </Tooltip>
      </Stack>

      {!done && (
        <LinearProgress
          variant={percent > 0 ? 'determinate' : 'indeterminate'}
          value={percent}
          color="primary"
          sx={{ height: 3, bgcolor: (theme) => alpha(theme.palette.common.white, 0.12) }}
        />
      )}

      <Box sx={{ px: 2, pt: 1.5, pb: 1.5 }}>
        {failed ? (
          <Typography variant="body2" sx={{ opacity: 0.85, whiteSpace: 'pre-wrap' }}>
            {status === 'unavailable'
              ? t('archives.restorePanel.unavailableHint')
              : job?.error_message
                ? job.error_message
                    .split('\n')
                    .map((line) => translateBackendKey(line))
                    .join('\n')
                : t('archives.restorePanel.noDetails')}
          </Typography>
        ) : (
          <>
            <Typography
              variant="body2"
              sx={{ opacity: 0.85, fontVariantNumeric: 'tabular-nums' }}
              noWrap
            >
              {done
                ? t('archives.restorePanel.restoredTo', { count: nfiles, path: job?.destination })
                : t('archives.restorePanel.restoringTo', { count: nfiles, path: job?.destination })}
            </Typography>
            {!done && job?.progress_details?.current_file && (
              <Typography
                variant="caption"
                component="div"
                noWrap
                sx={{ opacity: 0.6, fontFamily: 'monospace', mt: 0.5, direction: 'rtl' }}
              >
                {job.progress_details.current_file}
              </Typography>
            )}
          </>
        )}
        {done && (
          <Stack direction="row" spacing={1} sx={{ mt: 1.5, justifyContent: 'flex-end' }}>
            <Button
              size="small"
              component={RouterLink}
              to={`/activity?repository_id=${repositoryId}`}
              startIcon={<RotateCcw size={14} />}
              sx={{ color: 'inherit', opacity: 0.85, '&:hover': { opacity: 1 } }}
            >
              {t('archives.restorePanel.viewActivity')}
            </Button>
          </Stack>
        )}
      </Box>
    </Box>
  )
}

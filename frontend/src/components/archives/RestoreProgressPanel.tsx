import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link as RouterLink } from 'react-router-dom'
import {
  Box,
  Button,
  IconButton,
  LinearProgress,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material'
import { AlertTriangle, CheckCircle2, Loader2, RotateCcw, X } from 'lucide-react'
import { restoreAPI } from '../../services/api'
import { translateBackendKey } from '../../utils/translateBackendKey'
import {
  cornerPanelFooterSx,
  cornerPanelHeaderSx,
  cornerPanelIconButtonSx,
  cornerPanelIconSx,
  cornerPanelSx,
} from './cornerStack'

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

/** One card in the page's bottom-right column, so a restore never shifts
 *  the page. It follows one job from pending through running to its final
 *  state and stays there until dismissed, so a fast restore does not vanish
 *  before anyone reads it. */
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
  /** The status request failed. The job may still be running, so this is
   *  not the same as a failed restore. A job already seen finishing keeps
   *  its outcome: nothing newer can arrive for it. */
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
  const theme = useTheme()
  const settled = job != null && TERMINAL.has(job.status)
  const status = statusUnavailable && !settled ? 'unavailable' : (job?.status ?? 'pending')
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
        ...cornerPanelSx,
        '@keyframes restore-panel-spin': { to: { transform: 'rotate(360deg)' } },
      }}
    >
      <Box sx={cornerPanelHeaderSx}>
        <Box
          sx={cornerPanelIconSx(theme, failed ? 'error' : done ? 'success' : 'primary')}
          aria-hidden
        >
          <Box
            component={Icon}
            size={17}
            sx={{
              display: 'block',
              animation: done ? undefined : 'restore-panel-spin 1s linear infinite',
            }}
          />
        </Box>
        <Typography variant="body2" sx={{ fontWeight: 600, flex: 1, minWidth: 0 }} noWrap>
          {title}
        </Typography>
        <Tooltip title={t('archives.restorePanel.dismiss')}>
          <IconButton
            size="small"
            aria-label={t('archives.restorePanel.dismiss')}
            onClick={onDismiss}
            sx={cornerPanelIconButtonSx}
          >
            <X size={16} />
          </IconButton>
        </Tooltip>
      </Box>

      {!done && (
        <LinearProgress
          variant={percent > 0 ? 'determinate' : 'indeterminate'}
          value={percent}
          color="primary"
          sx={{ height: 3, bgcolor: 'action.hover' }}
        />
      )}

      <Box sx={{ px: 2, pt: 1.5, pb: 1.5 }}>
        {failed ? (
          <Typography variant="body2" sx={{ color: 'text.secondary', whiteSpace: 'pre-wrap' }}>
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
              sx={{ color: 'text.secondary', fontVariantNumeric: 'tabular-nums' }}
              noWrap
            >
              {!job
                ? t('archives.restorePanel.waiting')
                : done
                  ? t('archives.restorePanel.restoredTo', { count: nfiles, path: job.destination })
                  : t('archives.restorePanel.restoringTo', {
                      count: nfiles,
                      path: job.destination,
                    })}
            </Typography>
            {!done && job?.progress_details?.current_file && (
              <Typography
                variant="caption"
                component="div"
                noWrap
                sx={{ color: 'text.secondary', fontFamily: 'monospace', mt: 0.5, direction: 'rtl' }}
              >
                {job.progress_details.current_file}
              </Typography>
            )}
          </>
        )}
      </Box>
      {done && (
        <Box sx={cornerPanelFooterSx}>
          <Button
            size="small"
            component={RouterLink}
            to={`/activity?repository_id=${repositoryId}`}
            startIcon={<RotateCcw size={14} />}
            sx={{ whiteSpace: 'nowrap' }}
          >
            {t('archives.restorePanel.viewActivity')}
          </Button>
        </Box>
      )}
    </Box>
  )
}

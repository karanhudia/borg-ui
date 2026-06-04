import React from 'react'
import { useTranslation } from 'react-i18next'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  LinearProgress,
  Stack,
  TextField,
  Tooltip,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import {
  Archive,
  CheckCircle2,
  Eraser,
  FlaskConical,
  RefreshCw,
  ShieldAlert,
  Terminal,
  Trash2,
  TriangleAlert,
  XCircle,
} from 'lucide-react'
import ResponsiveDialog from './shared/ResponsiveDialog'
import { formatDateShort, formatDateTimeFull } from '../utils/dateUtils'
import type { Repository, RepositoryWipeExecuteRequest, RepositoryWipeJob } from '../types'

interface RepositoryWipeDialogProps {
  open: boolean
  repository: Repository | null
  preview: RepositoryWipeJob | null
  job: RepositoryWipeJob | null
  isPreviewLoading: boolean
  isExecuteLoading: boolean
  onClose: () => void
  onGeneratePreview: (runCompact: boolean) => void
  onExecute: (payload: RepositoryWipeExecuteRequest) => void
  onCancelPreview: (jobId: number) => void
}

const TERMINAL_STATUSES = new Set([
  'completed',
  'completed_compaction_failed',
  'completed_with_warnings',
  'failed',
  'failed_partial',
  'cancelled',
])

function terminalMessage(job: RepositoryWipeJob, t: (key: string) => string) {
  if (job.status === 'completed') return t('dialogs.repositoryWipe.success')
  if (job.status === 'completed_compaction_failed') return t('dialogs.repositoryWipe.compactFailed')
  if (job.status === 'completed_with_warnings') return t('dialogs.repositoryWipe.compactSkipped')
  if (job.status === 'failed_partial') return t('dialogs.repositoryWipe.partialFailed')
  if (job.status === 'cancelled') return t('dialogs.repositoryWipe.cancelled')
  return t('dialogs.repositoryWipe.failed')
}

function statusSeverity(status: string) {
  if (status === 'completed') return 'success' as const
  if (status === 'completed_compaction_failed' || status === 'completed_with_warnings') {
    return 'warning' as const
  }
  if (status === 'cancelled') return 'info' as const
  return 'error' as const
}

export default function RepositoryWipeDialog({
  open,
  repository,
  preview,
  job,
  isPreviewLoading,
  isExecuteLoading,
  onClose,
  onGeneratePreview,
  onExecute,
  onCancelPreview,
}: RepositoryWipeDialogProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const [runCompact, setRunCompact] = React.useState(true)
  const [understood, setUnderstood] = React.useState(false)
  const [confirmationPhrase, setConfirmationPhrase] = React.useState('')

  React.useEffect(() => {
    if (open) {
      setRunCompact(preview?.run_compact ?? true)
      setUnderstood(false)
      setConfirmationPhrase('')
    }
  }, [open, preview?.id, preview?.run_compact, repository?.id])

  if (!repository) return null

  const expectedPhrase = `WIPE ${repository.name}`
  const phraseTouched = confirmationPhrase.length > 0
  const phraseMatches = confirmationPhrase === expectedPhrase
  const previewIsStale = preview?.phase === 'stale'
  const archiveCount = preview?.archive_count ?? repository.archive_count ?? 0
  const isEmptyPreview = Boolean(preview) && archiveCount === 0
  const isBlocked = Boolean(preview?.blocked || preview?.blocking_reason)
  const hasTerminalJob = Boolean(job && TERMINAL_STATUSES.has(job.status))
  const jobIsRunning = Boolean(job && (job.status === 'pending' || job.status === 'running'))
  const canExecute =
    Boolean(preview) &&
    !isEmptyPreview &&
    !isBlocked &&
    !previewIsStale &&
    understood &&
    phraseMatches &&
    !isExecuteLoading &&
    !jobIsRunning

  const borderColor = isDark ? alpha('#fff', 0.09) : alpha('#000', 0.1)
  const warningColor = theme.palette.error.main

  const metadata = [
    {
      label: t('dialogs.repositoryWipe.metadata.borgVersion'),
      value: `Borg ${repository.borg_version ?? 1}`,
    },
    {
      label: t('dialogs.repositoryWipe.metadata.archives'),
      value: String(repository.archive_count ?? 0),
    },
    {
      label: t('dialogs.repositoryWipe.metadata.totalSize'),
      value: repository.total_size || 'N/A',
    },
    {
      label: t('dialogs.repositoryWipe.metadata.lastBackup'),
      value: repository.last_backup ? formatDateShort(repository.last_backup) : t('common.never'),
      title: repository.last_backup ? formatDateTimeFull(repository.last_backup) : undefined,
    },
  ]

  const handleExecute = () => {
    if (!preview || !canExecute) return
    onExecute({
      preview_id: preview.id,
      preview_fingerprint: preview.archive_fingerprint,
      confirmation_phrase: confirmationPhrase,
      understood,
      run_compact: runCompact,
    })
  }

  return (
    <ResponsiveDialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ pb: 1.5 }}>
        <Stack direction="row" spacing={1.5} alignItems="flex-start">
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 38,
              height: 38,
              borderRadius: 1.5,
              bgcolor: alpha(warningColor, isDark ? 0.18 : 0.1),
              color: warningColor,
              flexShrink: 0,
            }}
          >
            <ShieldAlert size={19} />
          </Box>
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography variant="h6" fontWeight={650} lineHeight={1.3}>
              {t('dialogs.repositoryWipe.title')}
            </Typography>
            <Typography
              variant="body2"
              color="text.secondary"
              noWrap
              sx={{ fontFamily: 'ui-monospace, monospace', fontSize: '0.72rem', mt: 0.25 }}
            >
              {repository.name} · {repository.path}
            </Typography>
          </Box>
          {preview && (
            <Chip
              label={t('dialogs.repositoryWipe.previewReady')}
              size="small"
              color={previewIsStale ? 'warning' : isBlocked ? 'error' : 'default'}
              sx={{ height: 22, fontSize: '0.68rem', fontWeight: 700, flexShrink: 0 }}
            />
          )}
        </Stack>
      </DialogTitle>

      <DialogContent sx={{ pt: 0 }}>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            {t('dialogs.repositoryWipe.scopeSummary')}
          </Typography>

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', sm: 'repeat(4, 1fr)' },
              border: '1px solid',
              borderColor,
              borderRadius: 1.5,
              overflow: 'hidden',
            }}
          >
            {metadata.map((item, index) => (
              <Tooltip key={item.label} title={item.title || ''} arrow>
                <Box
                  sx={{
                    px: 1.5,
                    py: 1.1,
                    borderRight: { sm: index === metadata.length - 1 ? 0 : '1px solid' },
                    borderBottom: { xs: index < 2 ? '1px solid' : 0, sm: 0 },
                    borderColor,
                    minWidth: 0,
                  }}
                >
                  <Typography
                    sx={{
                      color: 'text.disabled',
                      fontSize: '0.6rem',
                      fontWeight: 700,
                      letterSpacing: '0.08em',
                      textTransform: 'uppercase',
                      mb: 0.35,
                    }}
                  >
                    {item.label}
                  </Typography>
                  <Typography noWrap sx={{ fontSize: '0.85rem', fontWeight: 650 }}>
                    {item.value}
                  </Typography>
                </Box>
              </Tooltip>
            ))}
          </Box>

          <Box
            sx={{
              display: 'flex',
              gap: 1,
              alignItems: 'flex-start',
              p: 1.5,
              borderRadius: 1.5,
              border: '1px solid',
              borderColor: alpha(warningColor, isDark ? 0.34 : 0.24),
              bgcolor: alpha(warningColor, isDark ? 0.1 : 0.05),
            }}
          >
            <Box sx={{ color: warningColor, display: 'flex', flexShrink: 0, mt: '1px' }}>
              <TriangleAlert size={15} />
            </Box>
            <Typography variant="body2" sx={{ fontSize: '0.8rem', color: 'text.secondary' }}>
              {t('dialogs.repositoryWipe.warningPanel')}
            </Typography>
          </Box>

          <FormControlLabel
            control={
              <Checkbox
                checked={runCompact}
                onChange={(event) => setRunCompact(event.target.checked)}
                disabled={isPreviewLoading || jobIsRunning}
              />
            }
            label={
              <Box>
                <Typography variant="body2" fontWeight={600}>
                  {t('dialogs.repositoryWipe.compactOption')}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.45 }}>
                  {t('dialogs.repositoryWipe.compactHelper')}
                </Typography>
              </Box>
            }
            sx={{ alignItems: 'flex-start', m: 0 }}
          />

          <Button
            variant="outlined"
            onClick={() => onGeneratePreview(runCompact)}
            disabled={isPreviewLoading || jobIsRunning}
            startIcon={
              isPreviewLoading ? (
                <CircularProgress size={15} color="inherit" />
              ) : (
                <FlaskConical size={15} />
              )
            }
            sx={{ alignSelf: 'flex-start' }}
          >
            {isPreviewLoading ? t('status.running') : t('dialogs.repositoryWipe.previewButton')}
          </Button>

          {preview && (
            <Box
              sx={{
                border: '1px solid',
                borderColor,
                borderRadius: 1.5,
                overflow: 'hidden',
              }}
            >
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 1,
                  px: 1.5,
                  py: 1,
                  bgcolor: isDark ? alpha('#fff', 0.035) : alpha('#000', 0.025),
                  borderBottom: '1px solid',
                  borderColor,
                }}
              >
                <Stack direction="row" spacing={0.75} alignItems="center" minWidth={0}>
                  <Archive size={15} />
                  <Typography variant="body2" fontWeight={700}>
                    {t('dialogs.repositoryWipe.previewScope', { count: archiveCount })}
                  </Typography>
                </Stack>
                <Typography
                  variant="caption"
                  color="text.disabled"
                  noWrap
                  sx={{ fontFamily: 'ui-monospace, monospace' }}
                >
                  {preview.archive_fingerprint}
                </Typography>
              </Box>

              <Box sx={{ p: 1.5 }}>
                {isEmptyPreview && (
                  <Alert severity="info" icon={<CheckCircle2 size={18} />}>
                    {t('dialogs.repositoryWipe.emptyState')}
                  </Alert>
                )}

                {previewIsStale && (
                  <Alert severity="warning" icon={<RefreshCw size={18} />}>
                    {t('dialogs.repositoryWipe.staleState')}
                  </Alert>
                )}

                {isBlocked && (
                  <Alert severity="error" icon={<XCircle size={18} />}>
                    <Typography variant="body2" fontWeight={650}>
                      {preview.blocking_reason === 'protected_archives'
                        ? t('dialogs.repositoryWipe.protectedTitle')
                        : t('dialogs.repositoryWipe.blockedTitle')}
                    </Typography>
                    {preview.protected_archives?.length ? (
                      <Typography variant="body2" sx={{ mt: 0.5 }}>
                        {preview.protected_archives.join(', ')}
                      </Typography>
                    ) : null}
                  </Alert>
                )}

                {!isEmptyPreview && (
                  <Stack spacing={1.5} sx={{ mt: isBlocked || previewIsStale ? 1.5 : 0 }}>
                    <Box
                      sx={{
                        display: 'grid',
                        gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' },
                        gap: 1,
                        maxHeight: 220,
                        overflow: 'auto',
                      }}
                    >
                      {(preview.archives || []).map((archive) => (
                        <Box
                          key={archive.identity}
                          sx={{
                            border: '1px solid',
                            borderColor,
                            borderRadius: 1,
                            px: 1.25,
                            py: 0.85,
                            minWidth: 0,
                            bgcolor: isDark ? alpha('#fff', 0.018) : alpha('#000', 0.012),
                          }}
                        >
                          <Typography noWrap variant="body2" fontWeight={650}>
                            {archive.name || archive.identity}
                          </Typography>
                          <Typography
                            noWrap
                            variant="caption"
                            color="text.disabled"
                            sx={{ fontFamily: 'ui-monospace, monospace' }}
                          >
                            {archive.id || archive.identity}
                          </Typography>
                        </Box>
                      ))}
                    </Box>

                    {preview.dry_run_output && (
                      <Box
                        sx={{
                          border: '1px solid',
                          borderColor,
                          borderRadius: 1,
                          overflow: 'hidden',
                          bgcolor: isDark ? alpha('#000', 0.42) : alpha('#000', 0.035),
                        }}
                      >
                        <Stack
                          direction="row"
                          spacing={0.75}
                          alignItems="center"
                          sx={{
                            px: 1.25,
                            py: 0.75,
                            borderBottom: '1px solid',
                            borderColor,
                            color: 'text.disabled',
                          }}
                        >
                          <Terminal size={13} />
                          <Typography
                            variant="caption"
                            sx={{ fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.08em' }}
                          >
                            {t('dialogs.repositoryWipe.dryRunOutput')}
                          </Typography>
                        </Stack>
                        <Box
                          sx={{
                            m: 0,
                            p: 1.25,
                            maxHeight: 160,
                            overflow: 'auto',
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                            fontFamily: 'ui-monospace, "Fira Code", monospace',
                            fontSize: '0.75rem',
                            color: 'text.secondary',
                          }}
                        >
                          {preview.dry_run_output.split('\n').map((line, index) => (
                            <Box key={`${line}-${index}`} component="div">
                              {line}
                            </Box>
                          ))}
                        </Box>
                      </Box>
                    )}
                  </Stack>
                )}
              </Box>
            </Box>
          )}

          {preview && !isEmptyPreview && !isBlocked && !previewIsStale && !hasTerminalJob && (
            <Stack spacing={1.25}>
              <Divider />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={understood}
                    onChange={(event) => setUnderstood(event.target.checked)}
                    disabled={jobIsRunning}
                  />
                }
                label={t('dialogs.repositoryWipe.understandingLabel')}
                sx={{ m: 0 }}
              />
              <TextField
                label={t('dialogs.repositoryWipe.confirmationLabel', {
                  repositoryName: repository.name,
                })}
                value={confirmationPhrase}
                onChange={(event) => setConfirmationPhrase(event.target.value)}
                disabled={jobIsRunning}
                error={phraseTouched && !phraseMatches}
                helperText={
                  phraseTouched && !phraseMatches
                    ? t('dialogs.repositoryWipe.confirmationMismatch')
                    : ' '
                }
                fullWidth
                autoComplete="off"
                inputProps={{ 'aria-describedby': 'repository-wipe-confirmation-helper' }}
                FormHelperTextProps={{ id: 'repository-wipe-confirmation-helper' }}
              />
            </Stack>
          )}

          {job && !hasTerminalJob && (
            <Box
              role="status"
              sx={{
                border: '1px solid',
                borderColor,
                borderRadius: 1.5,
                p: 1.5,
              }}
            >
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                <RefreshCw size={16} className="animate-spin" />
                <Typography variant="body2" fontWeight={700}>
                  {job.progress_message || t('dialogs.repositoryWipe.running')}
                </Typography>
              </Stack>
              <LinearProgress variant="determinate" value={job.progress ?? 10} />
            </Box>
          )}

          {job && hasTerminalJob && (
            <Alert role="status" severity={statusSeverity(job.status)}>
              <Typography variant="body2" fontWeight={650}>
                {terminalMessage(job, t)}
              </Typography>
              {job.error_message && (
                <Typography variant="body2" sx={{ mt: 0.5 }}>
                  {job.error_message}
                </Typography>
              )}
            </Alert>
          )}
        </Stack>
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2.5, gap: 1, flexWrap: 'wrap' }}>
        <Button onClick={onClose}>{t('common.buttons.cancel')}</Button>
        {preview &&
          (preview.status === 'previewed' || preview.status === 'pending') &&
          !jobIsRunning && (
            <Button
              variant="outlined"
              color="inherit"
              onClick={() => onCancelPreview(preview.id)}
              startIcon={<Eraser size={15} />}
            >
              {t('dialogs.repositoryWipe.cancelPreview')}
            </Button>
          )}
        <Button
          variant="contained"
          color="error"
          disabled={!canExecute}
          onClick={handleExecute}
          startIcon={
            isExecuteLoading ? <CircularProgress size={15} color="inherit" /> : <Trash2 size={15} />
          }
          sx={{ ml: 'auto', whiteSpace: 'nowrap' }}
        >
          {isExecuteLoading ? t('status.running') : t('dialogs.repositoryWipe.finalButton')}
        </Button>
      </DialogActions>
    </ResponsiveDialog>
  )
}

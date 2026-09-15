import {
  DialogTitle,
  DialogContent,
  DialogActions,
  Box,
  Typography,
  Button,
  Card,
  CardContent,
  Alert,
  IconButton,
  Tooltip,
  Paper,
  CircularProgress,
} from '@mui/material'
import ResponsiveDialog from './shared/ResponsiveDialog'
import { useEffect, useRef, useState } from 'react'
import CalendarMonth from '@mui/icons-material/CalendarMonth'
import CheckIcon from '@mui/icons-material/Check'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import FileDownload from '@mui/icons-material/FileDownload'
import Lock from '@mui/icons-material/Lock'
import Storage from '@mui/icons-material/Storage'
import { useTranslation } from 'react-i18next'
import { formatDateShort } from '../utils/dateUtils'
import { repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import RepositoryStats from './RepositoryStats'
import PlanGate from './shared/PlanGate'
import UpgradePrompt from './UpgradePrompt'
import type { Repository, RepositoryStorage } from '../types'
import { isV2Repo } from '../utils/repoCapabilities'
import { generateBorgInitCommand } from '../utils/borgUtils'

interface RepositoryInfo {
  encryption?: {
    mode?: string
  }
  repository?: {
    last_modified?: string
    location?: string
  }
  // Borg's live blocks are still accepted (the callers pass the whole
  // `info` payload); the storage statistics no longer read them.
  cache?: {
    stats?: Record<string, number | undefined>
  }
  archives?: unknown[]
}

interface RepositoryInfoDialogProps {
  open: boolean
  repository: Repository | null
  repositoryInfo: RepositoryInfo | null
  /** The repository's stored size figures (#981): `null` when the server
   * could not compute them, `undefined` while they have not been loaded. */
  storage?: RepositoryStorage | null
  /** Index work still pending for the repository (#1063); falls back to
   * the repository row's own list when not given. */
  indexPendingKinds?: string[] | null
  isLoading: boolean
  onClose: () => void
  onRunRecoveryCheck?: (repository: Repository) => void
  canRunRecoveryCheck?: boolean
  isRecoveryCheckStarting?: boolean
  /** The backend's reason for the failure, e.g. borg's stderr from an agent job. */
  errorMessage?: string | null
}

interface RecoveryCommand {
  key: 'check' | 'repair' | 'init'
  label: string
  command: string
}

const SAFE_SHELL_ARG_PATTERN = /^[A-Za-z0-9_@%+=:,./-]+$/

function shellQuote(value: string): string {
  if (value && SAFE_SHELL_ARG_PATTERN.test(value)) {
    return value
  }

  return `'${value.replace(/'/g, "'\\''")}'`
}

function buildCheckCommand(repository: Repository, repair = false): string {
  const borgVersion = repository.borg_version === 2 ? 2 : 1
  const binary = borgVersion === 2 ? 'borg2' : 'borg'
  const remotePath = typeof repository.remote_path === 'string' ? repository.remote_path.trim() : ''
  const remotePathFlag = remotePath ? ` --remote-path ${shellQuote(remotePath)}` : ''
  const repositoryPath = shellQuote(repository.path)

  if (borgVersion === 2) {
    return `${binary} -r ${repositoryPath} check${repair ? ' --repair' : ''}${remotePathFlag}`
  }

  return `${binary} check${repair ? ' --repair' : ''}${remotePathFlag} ${repositoryPath}`
}

function buildRecoveryCommands(
  repository: Repository,
  t: ReturnType<typeof useTranslation>['t']
): RecoveryCommand[] {
  const borgVersion = repository.borg_version === 2 ? 2 : 1
  const remotePath = typeof repository.remote_path === 'string' ? repository.remote_path.trim() : ''
  const remotePathFlag = remotePath ? `--remote-path ${shellQuote(remotePath)} ` : ''
  const encryption =
    typeof repository.encryption === 'string' && repository.encryption.trim()
      ? repository.encryption.trim()
      : borgVersion === 2
        ? 'repokey-aes-ocb'
        : 'repokey'

  return [
    {
      key: 'check',
      label: t('repositoryInfoDialog.recovery.checkCommand'),
      command: buildCheckCommand(repository),
    },
    {
      key: 'repair',
      label: t('repositoryInfoDialog.recovery.repairCommand'),
      command: buildCheckCommand(repository, true),
    },
    {
      key: 'init',
      label: t('repositoryInfoDialog.recovery.initCommand'),
      command: generateBorgInitCommand({
        repositoryPath: shellQuote(repository.path),
        borgVersion,
        encryption,
        remotePathFlag,
      }),
    },
  ]
}

function RecoveryCommandBox({ command }: { command: RecoveryCommand }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const resetCopiedTimeoutRef = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (resetCopiedTimeoutRef.current !== null) {
        window.clearTimeout(resetCopiedTimeoutRef.current)
      }
    }
  }, [])

  const copyLabel = copied
    ? t('repositoryInfoDialog.recovery.copiedCommand', { label: command.label })
    : t('repositoryInfoDialog.recovery.copyCommand', { label: command.label })

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(command.command)
      setCopied(true)
      toast.success(t('repositoryInfoDialog.recovery.commandCopied'))
      if (resetCopiedTimeoutRef.current !== null) {
        window.clearTimeout(resetCopiedTimeoutRef.current)
      }
      resetCopiedTimeoutRef.current = window.setTimeout(() => {
        setCopied(false)
        resetCopiedTimeoutRef.current = null
      }, 2000)
    } catch {
      toast.error(t('repositoryInfoDialog.recovery.copyFailed'))
    }
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
      <Typography
        variant="caption"
        sx={{
          color: 'text.secondary',
          fontWeight: 700,
        }}
      >
        {command.label}
      </Typography>
      <Box
        sx={{
          position: 'relative',
          bgcolor: 'grey.900',
          color: 'grey.100',
          borderRadius: 1,
          px: 1.25,
          py: 1,
          pr: 5,
          fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
          fontSize: '0.78rem',
          lineHeight: 1.45,
          overflowX: 'auto',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
        }}
      >
        {command.command}
        <Tooltip title={copyLabel}>
          <IconButton
            size="small"
            aria-label={copyLabel}
            onClick={handleCopy}
            sx={{
              position: 'absolute',
              top: 4,
              right: 4,
              color: 'grey.400',
              bgcolor: 'rgba(255,255,255,0.08)',
              '&:hover': {
                bgcolor: 'rgba(255,255,255,0.16)',
                color: 'grey.200',
              },
            }}
          >
            {copied ? <CheckIcon fontSize="small" /> : <ContentCopyIcon fontSize="small" />}
          </IconButton>
        </Tooltip>
      </Box>
    </Box>
  )
}

function RecoveryGuidedCheckAction({
  repository,
  canRunRecoveryCheck,
  isRecoveryCheckStarting,
  onRunRecoveryCheck,
}: {
  repository: Repository
  canRunRecoveryCheck: boolean
  isRecoveryCheckStarting: boolean
  onRunRecoveryCheck: (repository: Repository) => void
}) {
  const { t } = useTranslation()
  const actionDisabled = !canRunRecoveryCheck || isRecoveryCheckStarting

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: { xs: 'column', sm: 'row' },
        alignItems: { xs: 'stretch', sm: 'center' },
        justifyContent: 'space-between',
        gap: 1.5,
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 1,
        bgcolor: 'background.paper',
        p: 1.5,
      }}
    >
      <Box sx={{ minWidth: 0 }}>
        <Typography
          variant="body2"
          sx={{
            fontWeight: 700,
          }}
        >
          {t('repositoryInfoDialog.recovery.guidedCheckTitle')}
        </Typography>
        <Typography
          variant="body2"
          sx={{
            color: 'text.secondary',
          }}
        >
          {t('repositoryInfoDialog.recovery.guidedCheckDescription')}
        </Typography>
        {!canRunRecoveryCheck && (
          <Typography
            variant="caption"
            sx={{
              color: 'text.secondary',
              display: 'block',
              mt: 0.5,
            }}
          >
            {t('repositoryInfoDialog.recovery.guidedCheckUnavailable')}
          </Typography>
        )}
      </Box>
      <Button
        variant="contained"
        size="small"
        disabled={actionDisabled}
        onClick={() => onRunRecoveryCheck(repository)}
        startIcon={
          isRecoveryCheckStarting ? <CircularProgress size={14} color="inherit" /> : <CheckIcon />
        }
        sx={{
          alignSelf: { xs: 'stretch', sm: 'center' },
          minWidth: 152,
          whiteSpace: 'nowrap',
        }}
      >
        {isRecoveryCheckStarting
          ? t('repositoryInfoDialog.recovery.guidedCheckStarting')
          : t('repositoryInfoDialog.recovery.guidedCheckButton')}
      </Button>
    </Box>
  )
}

export default function RepositoryInfoDialog({
  open,
  repository,
  repositoryInfo,
  storage,
  indexPendingKinds,
  isLoading,
  onClose,
  onRunRecoveryCheck,
  canRunRecoveryCheck = true,
  isRecoveryCheckStarting = false,
  errorMessage = null,
}: RepositoryInfoDialogProps) {
  const { t } = useTranslation()
  const [displayRepository, setDisplayRepository] = useState<Repository | null>(repository)
  const [displayRepositoryInfo, setDisplayRepositoryInfo] = useState<RepositoryInfo | null>(
    repositoryInfo
  )
  // The storage figures and the pending kinds are kept the way the live
  // info is, so the closing transition does not flip them to "unknown";
  // a different repository opening resets them before its own arrive.
  const [displayStorage, setDisplayStorage] = useState<RepositoryStorage | null | undefined>(
    storage
  )
  const [displayIndexPending, setDisplayIndexPending] = useState<string[] | null | undefined>(
    indexPendingKinds
  )
  const displayedRepositoryId = useRef<number | null>(repository?.id ?? null)

  useEffect(() => {
    if (repository) {
      setDisplayRepository(repository)
      if (displayedRepositoryId.current !== repository.id) {
        displayedRepositoryId.current = repository.id
        setDisplayStorage(undefined)
        setDisplayIndexPending(undefined)
      }
    }
  }, [repository])

  useEffect(() => {
    if (storage !== undefined) setDisplayStorage(storage)
  }, [storage])

  useEffect(() => {
    if (indexPendingKinds !== undefined) setDisplayIndexPending(indexPendingKinds)
  }, [indexPendingKinds])

  useEffect(() => {
    if (repositoryInfo) {
      setDisplayRepositoryInfo(repositoryInfo)
    }
  }, [repositoryInfo])

  useEffect(() => {
    if (!open && !repository) {
      const timeout = window.setTimeout(() => {
        setDisplayRepository(null)
        setDisplayRepositoryInfo(null)
        setDisplayStorage(undefined)
        setDisplayIndexPending(undefined)
        displayedRepositoryId.current = null
      }, 225)

      return () => window.clearTimeout(timeout)
    }
  }, [open, repository])

  const handleDownloadKeyfile = async () => {
    if (!displayRepository) return
    try {
      const response = await repositoriesAPI.downloadKeyfile(displayRepository.id)
      const blob = response.data instanceof Blob ? response.data : new Blob([response.data])
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `borg_keyfile_${displayRepository.name}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      setTimeout(() => URL.revokeObjectURL(url), 100)
    } catch (err: unknown) {
      let message = t('repositoryInfoDialog.failedToDownloadKeyfile')
      const errData = (err as { response?: { data?: unknown } })?.response?.data
      if (errData instanceof Blob) {
        // With responseType:'blob', error bodies also come back as Blob
        try {
          const text = await errData.text()
          const json = JSON.parse(text)
          message = json.detail || message
        } catch {
          // ignore parse errors
        }
      } else if (errData && typeof errData === 'object') {
        message = (errData as { detail?: string }).detail || message
      }
      toast.error(message)
    }
  }

  return (
    <ResponsiveDialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Storage color="primary" />
          <Typography
            variant="h5"
            sx={{
              fontWeight: 600,
            }}
          >
            {displayRepository?.name}
          </Typography>
        </Box>
      </DialogTitle>
      <DialogContent>
        {displayRepository && (
          <>
            {isLoading ? (
              <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
                <Typography
                  variant="body2"
                  sx={{
                    color: 'text.secondary',
                  }}
                >
                  {t('dialogs.repositoryInfo.loadingInfo')}
                </Typography>
              </Box>
            ) : displayRepositoryInfo ? (
              <PlanGate
                feature="borg_v2"
                when={isV2Repo(displayRepository)}
                fallback={
                  <UpgradePrompt
                    requiredPlan="pro"
                    message={t('dialogs.repositoryInfo.v2PlanRequired')}
                  />
                }
              >
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3, mt: 1 }}>
                  {/* Repository Details Cards */}
                  <Box
                    sx={{
                      display: 'grid',
                      gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)' },
                      gap: 2,
                    }}
                  >
                    {/* Encryption */}
                    <Card sx={{ backgroundColor: '#f3e5f5' }}>
                      <CardContent sx={{ py: 2 }}>
                        <Box
                          sx={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            mb: 1,
                          }}
                        >
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                            <Lock sx={{ color: '#7b1fa2', fontSize: 28 }} />
                            <Typography
                              variant="body2"
                              sx={{
                                color: 'text.secondary',
                                fontWeight: 500,
                              }}
                            >
                              {t('dialogs.repositoryInfo.encryption')}
                            </Typography>
                          </Box>
                          {displayRepository?.has_keyfile && (
                            <Tooltip
                              title={t('dialogs.repositoryInfo.exportKeyfileTooltip')}
                              arrow
                              placement="top"
                            >
                              <IconButton
                                onClick={handleDownloadKeyfile}
                                size="small"
                                sx={{
                                  backgroundColor: '#7b1fa2',
                                  color: 'white',
                                  width: 30,
                                  height: 30,
                                  '&:hover': {
                                    backgroundColor: '#4a148c',
                                    transform: 'scale(1.1)',
                                  },
                                  transition: 'all 0.15s ease',
                                }}
                              >
                                <FileDownload sx={{ fontSize: 16 }} />
                              </IconButton>
                            </Tooltip>
                          )}
                        </Box>
                        <Typography
                          variant="h6"
                          sx={{
                            fontWeight: 700,
                            color: '#7b1fa2',
                            ml: 5,
                          }}
                        >
                          {displayRepositoryInfo.encryption?.mode || 'N/A'}
                        </Typography>
                      </CardContent>
                    </Card>

                    {/* Last Modified */}
                    <Card sx={{ backgroundColor: '#e1f5fe' }}>
                      <CardContent sx={{ py: 2 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
                          <CalendarMonth sx={{ color: '#0277bd', fontSize: 28 }} />
                          <Typography
                            variant="body2"
                            sx={{
                              color: 'text.secondary',
                              fontWeight: 500,
                            }}
                          >
                            {t('dialogs.repositoryInfo.lastModified')}
                          </Typography>
                        </Box>
                        <Typography
                          variant="body2"
                          sx={{
                            fontWeight: 600,
                            color: '#0277bd',
                            ml: 5,
                          }}
                        >
                          {displayRepositoryInfo.repository?.last_modified
                            ? formatDateShort(displayRepositoryInfo.repository.last_modified)
                            : 'N/A'}
                        </Typography>
                      </CardContent>
                    </Card>
                  </Box>

                  {/* Location */}
                  <Card variant="outlined">
                    <CardContent sx={{ py: 2 }}>
                      <Typography
                        variant="caption"
                        sx={{
                          color: 'text.secondary',
                          display: 'block',
                          mb: 0.5,
                        }}
                      >
                        {t('dialogs.repositoryInfo.repositoryLocation')}
                      </Typography>
                      <Typography
                        variant="body2"
                        sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}
                      >
                        {displayRepositoryInfo.repository?.location || 'N/A'}
                      </Typography>
                    </CardContent>
                  </Card>

                  {/* Storage Statistics: the stored figures, as the card and the
                      archive header show them, never a live per-version block */}
                  <RepositoryStats
                    variant="detail"
                    storage={displayStorage}
                    borgVersion={displayRepository?.borg_version}
                    indexPendingKinds={
                      displayIndexPending ?? displayRepository?.index_pending_kinds
                    }
                  />
                </Box>
              </PlanGate>
            ) : (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <Alert severity="error">
                  {t('repositoryInfoDialog.failedToLoad')}
                  {errorMessage && (
                    <Box
                      component="pre"
                      sx={{
                        m: 0,
                        mt: 1,
                        fontFamily: 'monospace',
                        fontSize: '0.8rem',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                      }}
                    >
                      {errorMessage}
                    </Box>
                  )}
                </Alert>
                {displayRepository && (
                  <Paper
                    variant="outlined"
                    sx={{
                      p: 2,
                      borderRadius: 1,
                      bgcolor: 'action.hover',
                    }}
                  >
                    <Typography
                      variant="subtitle2"
                      gutterBottom
                      sx={{
                        fontWeight: 700,
                      }}
                    >
                      {t('repositoryInfoDialog.recovery.title')}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        color: 'text.secondary',
                        mb: 1.5,
                      }}
                    >
                      {t('repositoryInfoDialog.recovery.description')}
                    </Typography>
                    {onRunRecoveryCheck && (
                      <Box sx={{ mb: 1.5 }}>
                        <RecoveryGuidedCheckAction
                          repository={displayRepository}
                          canRunRecoveryCheck={canRunRecoveryCheck}
                          isRecoveryCheckStarting={isRecoveryCheckStarting}
                          onRunRecoveryCheck={onRunRecoveryCheck}
                        />
                      </Box>
                    )}
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
                      {buildRecoveryCommands(displayRepository, t).map((command) => (
                        <RecoveryCommandBox key={command.key} command={command} />
                      ))}
                    </Box>
                  </Paper>
                )}
              </Box>
            )}
          </>
        )}
      </DialogContent>
      <DialogActions sx={{ display: { xs: 'none', md: 'flex' } }}>
        <Button onClick={onClose} variant="contained">
          {t('dialogs.repositoryInfo.close')}
        </Button>
      </DialogActions>
    </ResponsiveDialog>
  )
}

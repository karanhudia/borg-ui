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
} from '@mui/material'
import ResponsiveDialog from './shared/ResponsiveDialog'
import { useEffect, useState } from 'react'
import CalendarMonth from '@mui/icons-material/CalendarMonth'
import CheckIcon from '@mui/icons-material/Check'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import FileDownload from '@mui/icons-material/FileDownload'
import Info from '@mui/icons-material/Info'
import Lock from '@mui/icons-material/Lock'
import Storage from '@mui/icons-material/Storage'
import { useTranslation } from 'react-i18next'
import { formatDateShort } from '../utils/dateUtils'
import { repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import RepositoryStatsV1 from './RepositoryStatsV1'
import RepositoryStatsV2, { type ArchiveEntry } from './RepositoryStatsV2'
import type { CacheStats } from './RepositoryStatsV1'
import PlanGate from './shared/PlanGate'
import UpgradePrompt from './UpgradePrompt'
import { Repository } from '../types'
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
  cache?: {
    stats?: CacheStats
  }
  // Borg 2: per-archive stats (from `borg2 info --json`)
  archives?: ArchiveEntry[]
}

interface RepositoryInfoDialogProps {
  open: boolean
  repository: Repository | null
  repositoryInfo: RepositoryInfo | null
  isLoading: boolean
  onClose: () => void
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

  const copyLabel = copied
    ? t('repositoryInfoDialog.recovery.copiedCommand', { label: command.label })
    : t('repositoryInfoDialog.recovery.copyCommand', { label: command.label })

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(command.command)
      setCopied(true)
      toast.success(t('repositoryInfoDialog.recovery.commandCopied'))
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error(t('repositoryInfoDialog.recovery.copyFailed'))
    }
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
      <Typography variant="caption" color="text.secondary" fontWeight={700}>
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

export default function RepositoryInfoDialog({
  open,
  repository,
  repositoryInfo,
  isLoading,
  onClose,
}: RepositoryInfoDialogProps) {
  const { t } = useTranslation()
  const [displayRepository, setDisplayRepository] = useState<Repository | null>(repository)
  const [displayRepositoryInfo, setDisplayRepositoryInfo] = useState<RepositoryInfo | null>(
    repositoryInfo
  )

  useEffect(() => {
    if (repository) {
      setDisplayRepository(repository)
    }
  }, [repository])

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
          <Typography variant="h5" fontWeight={600}>
            {displayRepository?.name}
          </Typography>
        </Box>
      </DialogTitle>
      <DialogContent>
        {displayRepository && (
          <>
            {isLoading ? (
              <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
                <Typography variant="body2" color="text.secondary">
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
                            <Typography variant="body2" color="text.secondary" fontWeight={500}>
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
                        <Typography variant="h6" fontWeight={700} sx={{ color: '#7b1fa2', ml: 5 }}>
                          {displayRepositoryInfo.encryption?.mode || 'N/A'}
                        </Typography>
                      </CardContent>
                    </Card>

                    {/* Last Modified */}
                    <Card sx={{ backgroundColor: '#e1f5fe' }}>
                      <CardContent sx={{ py: 2 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
                          <CalendarMonth sx={{ color: '#0277bd', fontSize: 28 }} />
                          <Typography variant="body2" color="text.secondary" fontWeight={500}>
                            {t('dialogs.repositoryInfo.lastModified')}
                          </Typography>
                        </Box>
                        <Typography
                          variant="body2"
                          fontWeight={600}
                          sx={{ color: '#0277bd', ml: 5 }}
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
                        color="text.secondary"
                        display="block"
                        sx={{ mb: 0.5 }}
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

                  {/* Storage Statistics */}
                  {isV2Repo(displayRepository) ? (
                    <RepositoryStatsV2 archives={displayRepositoryInfo.archives || []} />
                  ) : displayRepositoryInfo.cache?.stats &&
                    (displayRepositoryInfo.cache.stats.total_size ?? 0) > 0 ? (
                    <RepositoryStatsV1 stats={displayRepositoryInfo.cache.stats} />
                  ) : (
                    <Alert severity="info" icon={<Info />}>
                      <Typography variant="body2" fontWeight={600} gutterBottom>
                        {t('dialogs.repositoryInfo.noBackupsYet')}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {t('repositoryInfoDialog.noArchivesDescription')}
                      </Typography>
                    </Alert>
                  )}
                </Box>
              </PlanGate>
            ) : (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <Alert severity="error">{t('repositoryInfoDialog.failedToLoad')}</Alert>
                {displayRepository && (
                  <Paper
                    variant="outlined"
                    sx={{
                      p: 2,
                      borderRadius: 1,
                      bgcolor: 'action.hover',
                    }}
                  >
                    <Typography variant="subtitle2" fontWeight={700} gutterBottom>
                      {t('repositoryInfoDialog.recovery.title')}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                      {t('repositoryInfoDialog.recovery.description')}
                    </Typography>
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

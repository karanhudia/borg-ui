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
} from '@mui/material'
import ResponsiveDialog from './ResponsiveDialog'
import { useEffect, useState } from 'react'
import { Storage, Info, Lock, CalendarMonth, FileDownload } from '@mui/icons-material'
import { useTranslation } from 'react-i18next'
import { formatDateShort } from '../utils/dateUtils'
import { repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import RepositoryStatsV1 from './RepositoryStatsV1'
import RepositoryStatsV2, { type ArchiveEntry } from './RepositoryStatsV2'
import type { CacheStats } from './RepositoryStatsV1'
import PlanGate from './PlanGate'
import UpgradePrompt from './UpgradePrompt'
import { Repository } from '../types'
import { isV2Repo } from '../utils/repoCapabilities'

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
            {isLoading ? (
              <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
                <Typography variant="body2" color="text.secondary">
                  {t('dialogs.repositoryInfo.loadingInfo')}
                </Typography>
              </Box>
            ) : displayRepositoryInfo ? (
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
                      <Typography variant="body2" fontWeight={600} sx={{ color: '#0277bd', ml: 5 }}>
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
            ) : (
              <Alert severity="error">{t('repositoryInfoDialog.failedToLoad')}</Alert>
            )}
          </PlanGate>
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

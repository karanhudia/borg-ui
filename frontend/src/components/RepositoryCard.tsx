import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, CardContent, Box, Typography, Button, Tooltip, Chip } from '@mui/material'
import {
  Info,
  CheckCircle as CheckCircleIcon,
  Refresh,
  Delete,
  PlayArrow,
  FolderOpen,
} from '@mui/icons-material'
import { useMaintenanceJobs } from '../hooks/useMaintenanceJobs'
import BorgVersionChip from './BorgVersionChip'
import { getRepoCapabilities } from '../utils/repoCapabilities'
import {
  formatDateShort,
  formatDateTimeFull,
  formatElapsedTime,
  parseBytes,
} from '../utils/dateUtils'
import { useQueryClient } from '@tanstack/react-query'
import { useMatomo } from '../hooks/useMatomo'
import { Repository } from '../types'

interface RepositoryCardProps {
  repository: Repository
  isInJobsSet: boolean
  onViewInfo: () => void
  onCheck: () => void
  onCompact: () => void
  onPrune: () => void
  onEdit: () => void
  onDelete: () => void
  onBackupNow: () => void
  onViewArchives: () => void
  getCompressionLabel: (compression: string) => string
  isAdmin: boolean
  onJobCompleted?: (repositoryId: number) => void
}

export default function RepositoryCard({
  repository,
  isInJobsSet,
  onViewInfo,
  onCheck,
  onCompact,
  onPrune,
  onEdit,
  onDelete,
  onBackupNow,
  onViewArchives,
  getCompressionLabel,
  isAdmin,
  onJobCompleted,
}: RepositoryCardProps) {
  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const { trackRepository, trackBackup, trackMaintenance, trackArchive, EventAction } = useMatomo()

  // Use maintenance jobs hook - always poll to handle page refreshes
  const capabilities = getRepoCapabilities(repository)

  const { hasRunningJobs, checkJob, compactJob, pruneJob } = useMaintenanceJobs(
    repository.id,
    true // Always enabled to handle page refreshes while jobs are running
  )

  // Determine if maintenance is running
  // Prioritize hasRunningJobs from polling (more up-to-date) over API flag
  const isMaintenanceRunning = hasRunningJobs

  // State to track elapsed time display (updates every second for real-time UX)
  const [elapsedTime, setElapsedTime] = useState('')

  // Update elapsed time in real-time for running jobs (every second for smooth UX)
  useEffect(() => {
    if (!hasRunningJobs) {
      setElapsedTime('')
      return
    }

    // Get the earliest start time from running jobs
    const startTime = checkJob?.started_at || compactJob?.started_at || pruneJob?.started_at
    if (!startTime) return

    // Update immediately
    setElapsedTime(formatElapsedTime(startTime))

    // Update every second for real-time display
    const interval = setInterval(() => {
      setElapsedTime(formatElapsedTime(startTime))
    }, 1000)

    return () => clearInterval(interval)
  }, [hasRunningJobs, checkJob?.started_at, compactJob?.started_at, pruneJob?.started_at])

  // Handle job completion - when polling detects completion, refresh repositories list
  useEffect(() => {
    if (!hasRunningJobs && isInJobsSet) {
      // Jobs have completed according to our polling
      onJobCompleted?.(repository.id)
      // Immediately invalidate to update has_running_maintenance flag
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
    }
  }, [hasRunningJobs, isInJobsSet, repository.id, onJobCompleted, queryClient])

  return (
    <Card
      variant="outlined"
      sx={{
        border: 1,
        borderColor: 'divider',
        '&:hover': {
          borderColor: 'primary.main',
          boxShadow: 1,
        },
      }}
    >
      <CardContent>
        <Box
          sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}
        >
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
              <Typography variant="h6" fontWeight={600}>
                {repository.name}
              </Typography>
              {repository.mode === 'observe' && (
                <Chip
                  label={t('repositoryCard.observeOnly')}
                  size="small"
                  color="info"
                  sx={{ height: '20px', fontSize: '0.7rem' }}
                />
              )}
              <BorgVersionChip borgVersion={repository.borg_version} />
            </Box>
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}
            >
              {repository.path}
            </Typography>
          </Box>
          {isAdmin && (
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button variant="outlined" size="small" onClick={onEdit}>
                {t('repositoryCard.edit')}
              </Button>
            </Box>
          )}
        </Box>

        <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap', mb: 2 }}>
          <Box>
            <Typography variant="caption" color="text.secondary" display="block">
              {t('repositoryCard.archives')}
            </Typography>
            <Typography variant="body2" fontWeight={500}>
              {repository.archive_count}
            </Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" display="block">
              {t('repositoryCard.totalSize')}
            </Typography>
            <Typography variant="body2" fontWeight={500}>
              {repository.total_size || 'N/A'}
            </Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" display="block">
              {t('repositoryCard.lastBackup')}
            </Typography>
            <Tooltip
              title={
                repository.last_backup
                  ? formatDateTimeFull(repository.last_backup)
                  : t('common.never')
              }
              arrow
            >
              <Typography
                variant="body2"
                fontWeight={500}
                sx={{ cursor: repository.last_backup ? 'help' : 'default' }}
              >
                {repository.last_backup
                  ? formatDateShort(repository.last_backup)
                  : t('common.never')}
              </Typography>
            </Tooltip>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" display="block">
              {t('repositoryCard.lastCheck')}
            </Typography>
            <Tooltip
              title={
                repository.last_check
                  ? formatDateTimeFull(repository.last_check)
                  : t('common.never')
              }
              arrow
            >
              <Typography
                variant="body2"
                fontWeight={500}
                sx={{ cursor: repository.last_check ? 'help' : 'default' }}
              >
                {repository.last_check ? formatDateShort(repository.last_check) : t('common.never')}
              </Typography>
            </Tooltip>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" display="block">
              {t('repositoryCard.lastCompact')}
            </Typography>
            <Tooltip
              title={
                repository.last_compact
                  ? formatDateTimeFull(repository.last_compact)
                  : t('common.never')
              }
              arrow
            >
              <Typography
                variant="body2"
                fontWeight={500}
                sx={{ cursor: repository.last_compact ? 'help' : 'default' }}
              >
                {repository.last_compact
                  ? formatDateShort(repository.last_compact)
                  : t('common.never')}
              </Typography>
            </Tooltip>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" display="block">
              {t('repositoryCard.encryption')}
            </Typography>
            <Typography variant="body2" fontWeight={500}>
              {repository.encryption}
            </Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" display="block">
              {t('repositoryCard.compression')}
            </Typography>
            <Typography variant="body2" fontWeight={500}>
              {getCompressionLabel(repository.compression)}
            </Typography>
          </Box>

          {repository.source_directories && repository.source_directories.length > 0 && (
            <Box>
              <Typography variant="caption" color="text.secondary" display="block">
                {t('repositoryCard.sourcePaths')}
              </Typography>
              <Typography variant="body2" fontWeight={500}>
                {repository.source_directories.length}{' '}
                {repository.source_directories.length === 1
                  ? t('repositoryCard.path')
                  : t('repositoryCard.paths')}
              </Typography>
            </Box>
          )}
        </Box>

        {/* Action Buttons */}
        {isAdmin && (
          <Box>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              <Button
                variant="outlined"
                size="small"
                startIcon={<Info />}
                onClick={() => {
                  trackRepository(
                    EventAction.VIEW,
                    repository.name,
                    parseBytes(repository.total_size)
                  )
                  onViewInfo()
                }}
                disabled={isMaintenanceRunning}
                sx={{ textTransform: 'none' }}
              >
                {t('repositoryCard.buttons.info')}
              </Button>
              <Button
                variant="outlined"
                size="small"
                startIcon={checkJob ? <Refresh className="animate-spin" /> : <CheckCircleIcon />}
                onClick={() => {
                  trackMaintenance(EventAction.START, 'Check', repository.name)
                  onCheck()
                }}
                disabled={isMaintenanceRunning}
                sx={{ textTransform: 'none' }}
                color={checkJob ? 'primary' : 'inherit'}
              >
                {t('repositoryCard.buttons.check')}
              </Button>
              {capabilities.canCompact && (
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={compactJob ? <Refresh className="animate-spin" /> : <Refresh />}
                  onClick={() => {
                    trackMaintenance(EventAction.START, 'Compact', repository.name)
                    onCompact()
                  }}
                  disabled={isMaintenanceRunning}
                  color={compactJob ? 'primary' : 'warning'}
                  sx={{ textTransform: 'none' }}
                >
                  {t('repositoryCard.buttons.compact')}
                </Button>
              )}
              {capabilities.canPrune && (
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={pruneJob ? <Refresh className="animate-spin" /> : <Delete />}
                  onClick={() => {
                    trackMaintenance(EventAction.START, 'Prune', repository.name)
                    onPrune()
                  }}
                  disabled={isMaintenanceRunning}
                  color={pruneJob ? 'primary' : 'secondary'}
                  sx={{ textTransform: 'none' }}
                >
                  {t('repositoryCard.buttons.prune')}
                </Button>
              )}
              {repository.mode === 'full' && (
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<PlayArrow />}
                  onClick={() => {
                    trackBackup(
                      EventAction.START,
                      undefined,
                      repository.name,
                      parseBytes(repository.total_size)
                    )
                    onBackupNow()
                  }}
                  disabled={isMaintenanceRunning}
                  color="success"
                  sx={{ textTransform: 'none' }}
                >
                  {t('repositoryCard.buttons.backupNow')}
                </Button>
              )}
              <Button
                variant="outlined"
                size="small"
                startIcon={<FolderOpen />}
                onClick={() => {
                  trackArchive(EventAction.VIEW, repository.name, parseBytes(repository.total_size))
                  onViewArchives()
                }}
                disabled={isMaintenanceRunning}
                sx={{ textTransform: 'none' }}
              >
                {t('repositoryCard.buttons.viewArchives')}
              </Button>
              {capabilities.canDelete && (
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<Delete />}
                  onClick={() => {
                    trackRepository(
                      EventAction.DELETE,
                      repository.name,
                      parseBytes(repository.total_size)
                    )
                    onDelete()
                  }}
                  color="error"
                  sx={{ textTransform: 'none' }}
                >
                  {t('repositoryCard.buttons.delete')}
                </Button>
              )}
            </Box>
            {/* Progress message and elapsed time */}
            {(checkJob?.progress_message || compactJob?.progress_message || elapsedTime) && (
              <Box sx={{ mt: 1.5 }}>
                {(checkJob?.progress_message || compactJob?.progress_message) && (
                  <Typography variant="caption" color="primary" sx={{ display: 'block' }}>
                    {checkJob?.progress_message || compactJob?.progress_message}
                  </Typography>
                )}
                {elapsedTime && (
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ display: 'block', mt: 0.5 }}
                  >
                    {elapsedTime}
                  </Typography>
                )}
              </Box>
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  )
}

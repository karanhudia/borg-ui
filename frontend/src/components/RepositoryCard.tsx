import { useEffect, useState } from 'react'
import { Card, CardContent, Box, Typography, Button, Tooltip, Chip } from '@mui/material'
import { Info, CheckCircle as CheckCircleIcon, Refresh, Delete } from '@mui/icons-material'
import { useMaintenanceJobs } from '../hooks/useMaintenanceJobs'
import { formatDateShort, formatDateTimeFull, formatElapsedTime } from '../utils/dateUtils'
import { useQueryClient } from '@tanstack/react-query'

interface Repository {
  id: number
  name: string
  path: string
  encryption: string
  compression: string
  source_directories: string[]
  exclude_patterns: string[]
  last_backup: string | null
  last_check: string | null
  last_compact: string | null
  total_size: string | null
  archive_count: number
  created_at: string
  updated_at: string | null
  mode: 'full' | 'observe'
  has_running_maintenance?: boolean
}

interface RepositoryCardProps {
  repository: Repository
  isInJobsSet: boolean
  onViewInfo: () => void
  onCheck: () => void
  onCompact: () => void
  onPrune: () => void
  onEdit: () => void
  onDelete: () => void
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
  getCompressionLabel,
  isAdmin,
  onJobCompleted,
}: RepositoryCardProps) {
  const queryClient = useQueryClient()

  // Use maintenance jobs hook - always poll to handle page refreshes
  const { hasRunningJobs, checkJob, compactJob } = useMaintenanceJobs(
    repository.id,
    true  // Always enabled to handle page refreshes while jobs are running
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
    const startTime = checkJob?.started_at || compactJob?.started_at
    if (!startTime) return

    // Update immediately
    setElapsedTime(formatElapsedTime(startTime))

    // Update every second for real-time display
    const interval = setInterval(() => {
      setElapsedTime(formatElapsedTime(startTime))
    }, 1000)

    return () => clearInterval(interval)
  }, [hasRunningJobs, checkJob?.started_at, compactJob?.started_at])

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
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
              <Typography variant="h6" fontWeight={600}>
                {repository.name}
              </Typography>
              {repository.mode === 'observe' && (
                <Chip
                  label="Observe Only"
                  size="small"
                  color="info"
                  sx={{ height: '20px', fontSize: '0.7rem' }}
                />
              )}
            </Box>
            <Typography variant="body2" color="text.secondary" sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
              {repository.path}
            </Typography>
          </Box>
          {isAdmin && (
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button variant="outlined" size="small" onClick={onEdit}>
                Edit
              </Button>
            </Box>
          )}
        </Box>

        <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap', mb: 2 }}>
          <Box>
            <Typography variant="caption" color="text.secondary" display="block">
              Archives
            </Typography>
            <Typography variant="body2" fontWeight={500}>
              {repository.archive_count}
            </Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" display="block">
              Total Size
            </Typography>
            <Typography variant="body2" fontWeight={500}>
              {repository.total_size || 'N/A'}
            </Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" display="block">
              Last Backup
            </Typography>
            <Tooltip title={repository.last_backup ? formatDateTimeFull(repository.last_backup) : 'Never'} arrow>
              <Typography variant="body2" fontWeight={500} sx={{ cursor: repository.last_backup ? 'help' : 'default' }}>
                {repository.last_backup ? formatDateShort(repository.last_backup) : 'Never'}
              </Typography>
            </Tooltip>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" display="block">
              Last Check
            </Typography>
            <Tooltip title={repository.last_check ? formatDateTimeFull(repository.last_check) : 'Never'} arrow>
              <Typography variant="body2" fontWeight={500} sx={{ cursor: repository.last_check ? 'help' : 'default' }}>
                {repository.last_check ? formatDateShort(repository.last_check) : 'Never'}
              </Typography>
            </Tooltip>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" display="block">
              Last Compact
            </Typography>
            <Tooltip title={repository.last_compact ? formatDateTimeFull(repository.last_compact) : 'Never'} arrow>
              <Typography variant="body2" fontWeight={500} sx={{ cursor: repository.last_compact ? 'help' : 'default' }}>
                {repository.last_compact ? formatDateShort(repository.last_compact) : 'Never'}
              </Typography>
            </Tooltip>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" display="block">
              Encryption
            </Typography>
            <Typography variant="body2" fontWeight={500}>
              {repository.encryption}
            </Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" display="block">
              Compression
            </Typography>
            <Typography variant="body2" fontWeight={500}>
              {getCompressionLabel(repository.compression)}
            </Typography>
          </Box>

          {repository.source_directories && repository.source_directories.length > 0 && (
            <Box>
              <Typography variant="caption" color="text.secondary" display="block">
                Source Paths
              </Typography>
              <Typography variant="body2" fontWeight={500}>
                {repository.source_directories.length} {repository.source_directories.length === 1 ? 'path' : 'paths'}
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
                onClick={onViewInfo}
                disabled={isMaintenanceRunning}
                sx={{ textTransform: 'none' }}
              >
                Info
              </Button>
              <Button
                variant="outlined"
                size="small"
                startIcon={checkJob ? <Refresh className="animate-spin" /> : <CheckCircleIcon />}
                onClick={onCheck}
                disabled={isMaintenanceRunning}
                sx={{ textTransform: 'none' }}
                color={checkJob ? 'primary' : 'inherit'}
              >
                Check
              </Button>
              <Button
                variant="outlined"
                size="small"
                startIcon={compactJob ? <Refresh className="animate-spin" /> : <Refresh />}
                onClick={onCompact}
                disabled={isMaintenanceRunning}
                color={compactJob ? 'primary' : 'warning'}
                sx={{ textTransform: 'none' }}
              >
                Compact
              </Button>
              <Button
                variant="outlined"
                size="small"
                startIcon={<Delete />}
                onClick={onPrune}
                disabled={false}
                color="secondary"
                sx={{ textTransform: 'none' }}
              >
                Prune
              </Button>
              <Button
                variant="outlined"
                size="small"
                startIcon={<Delete />}
                onClick={onDelete}
                color="error"
                sx={{ textTransform: 'none' }}
              >
                Delete
              </Button>
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
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
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

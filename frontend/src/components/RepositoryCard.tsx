import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Box, Typography, Button, IconButton, Tooltip, Chip, useTheme, alpha } from '@mui/material'
import { format, isTomorrow, isToday, isThisYear } from 'date-fns'
import {
  Info,
  ShieldCheck,
  Package2,
  Scissors,
  FolderOpen,
  Play,
  Trash2,
  Eraser,
  FolderX,
  SquarePen,
  Archive,
  HardDrive,
  Clock,
  Cloud,
  CloudDownload,
  CloudUpload,
  ScanSearch,
  RefreshCw,
  ClipboardList,
  Bot,
  CalendarClock,
  ListChecks,
  Unlock,
} from 'lucide-react'
import { useMaintenanceJobs } from '../hooks/useMaintenanceJobs'
import BorgVersionChip from './BorgVersionChip'
import { getRepoCapabilities } from '../utils/repoCapabilities'
import { formatDateShort, formatDateTimeFull, formatElapsedTime } from '../utils/dateUtils'
import { formatUploadRatelimit } from '../utils/uploadRatelimit'
import { useQueryClient } from '@tanstack/react-query'
import { useAnalytics } from '../hooks/useAnalytics'
import { Repository } from '../types'
import type { RepoAction } from '../hooks/usePermissions'
import OperationalCard from './OperationalCard'

interface RepositoryCardProps {
  repository: Repository
  isInJobsSet: boolean
  onViewInfo: () => void
  onCheck: () => void
  onCompact: () => void
  onPrune: () => void
  onWipeContents: () => void
  onBreakLock: () => void
  onEdit: () => void
  onDelete: () => void
  onPermanentDelete?: () => void
  onBackupNow: () => void
  onViewArchives: () => void
  onViewBackupPlans?: () => void
  onCreateBackupPlan?: () => void
  onRcloneSync?: () => void
  onRcloneHydrate?: () => void
  getCompressionLabel: (compression: string) => string
  canManageRepository?: boolean
  canBreakLock?: boolean
  canPermanentDeleteRepository?: boolean
  canDo: (action: RepoAction) => boolean
  onJobCompleted?: (repositoryId: number) => void
}

const ACCENT_IDLE = '#059669'
const ACCENT_RUNNING = '#f59e0b'

const STAT_ICONS = [
  <Archive size={11} />,
  <HardDrive size={11} />,
  <Clock size={11} />,
  <ScanSearch size={11} />,
]

const STAT_COLORS = ['primary', 'success', 'warning', 'info'] as const

export default function RepositoryCard({
  repository,
  isInJobsSet,
  onViewInfo,
  onCheck,
  onCompact,
  onPrune,
  onWipeContents,
  onBreakLock,
  onEdit,
  onDelete,
  onPermanentDelete,
  onBackupNow,
  onViewArchives,
  onViewBackupPlans,
  onCreateBackupPlan,
  onRcloneSync,
  onRcloneHydrate,
  getCompressionLabel,
  canManageRepository = false,
  canBreakLock = false,
  canPermanentDeleteRepository = false,
  canDo,
  onJobCompleted,
}: RepositoryCardProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const { trackRepository, trackBackup, trackArchive, EventAction } = useAnalytics()

  const capabilities = getRepoCapabilities(repository)
  const { hasRunningJobs, checkJob, compactJob, pruneJob, wipeJob } = useMaintenanceJobs(
    repository.id,
    true
  )
  const isMaintenanceRunning = hasRunningJobs
  const hasManualBackupSources = Boolean(repository.source_directories?.length)
  const canCreatePlan = Boolean(onCreateBackupPlan) && canDo('backup') && repository.mode === 'full'
  const canRunLegacyBackup = canDo('backup') && repository.mode === 'full' && hasManualBackupSources
  const rcloneStorage = repository.rclone_storage
  const rcloneOperationRunning =
    rcloneStorage?.sync_status === 'syncing' || rcloneStorage?.sync_status === 'hydrating'
  const isSshPrimaryRepository =
    repository.storage_backend === 'ssh' ||
    repository.repository_type === 'ssh' ||
    repository.execution_target === 'ssh' ||
    Boolean(repository.connection_id)
  const isLocalPrimaryRepository =
    repository.storage_backend == null ||
    repository.storage_backend === 'local' ||
    repository.repository_type === 'local'
  const isAgentPrimaryRepository =
    repository.storage_backend === 'agent_local' ||
    repository.execution_target === 'agent' ||
    repository.executor_type === 'agent'
  const agentMachineName =
    typeof repository.agent_machine_name === 'string'
      ? repository.agent_machine_name
      : typeof rcloneStorage?.agent_machine_name === 'string'
        ? rcloneStorage.agent_machine_name
        : null
  const agentMachineStatus =
    typeof repository.agent_machine_status === 'string'
      ? repository.agent_machine_status
      : typeof rcloneStorage?.agent_machine_status === 'string'
        ? rcloneStorage.agent_machine_status
        : null
  const canEnableCloudMirror =
    canManageRepository &&
    !rcloneStorage &&
    repository.repository_type !== 'rclone' &&
    (isLocalPrimaryRepository || isSshPrimaryRepository || isAgentPrimaryRepository)
  const canHydrateRclone =
    Boolean(rcloneStorage) &&
    rcloneStorage?.sync_direction !== 'agent_to_remote' &&
    rcloneStorage?.sync_direction !== 'sshfs_to_remote'
  const canShowDestructiveActions = canManageRepository && capabilities.canDeleteRepository
  const hasSeparatedRepositoryActions = canBreakLock || canShowDestructiveActions
  const uploadRatelimitLabel = formatUploadRatelimit(repository.upload_ratelimit_kib)

  const [elapsedTime, setElapsedTime] = useState('')

  useEffect(() => {
    if (!hasRunningJobs) {
      setElapsedTime('')
      return
    }
    const startTime =
      checkJob?.started_at || compactJob?.started_at || pruneJob?.started_at || wipeJob?.started_at
    if (!startTime) return
    setElapsedTime(formatElapsedTime(startTime))
    const interval = setInterval(() => {
      setElapsedTime(formatElapsedTime(startTime))
    }, 1000)
    return () => clearInterval(interval)
  }, [
    hasRunningJobs,
    checkJob?.started_at,
    compactJob?.started_at,
    pruneJob?.started_at,
    wipeJob?.started_at,
  ])

  useEffect(() => {
    if (!hasRunningJobs && isInJobsSet) {
      onJobCompleted?.(repository.id)
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
    }
  }, [hasRunningJobs, isInJobsSet, repository.id, onJobCompleted, queryClient])

  const keyStats = [
    {
      label: t('repositoryCard.archives'),
      value: String(repository.archive_count ?? 0),
      tooltip: '',
    },
    {
      label: t('repositoryCard.totalSize'),
      value: repository.total_size || 'N/A',
      tooltip: '',
    },
    {
      label: t('repositoryCard.lastBackup'),
      value: repository.last_backup ? formatDateShort(repository.last_backup) : t('common.never'),
      tooltip: repository.last_backup ? formatDateTimeFull(repository.last_backup) : '',
    },
    {
      label: t('repositoryCard.lastCheck'),
      value: repository.last_check ? formatDateShort(repository.last_check) : t('common.never'),
      tooltip: repository.last_check ? formatDateTimeFull(repository.last_check) : '',
    },
  ]

  const metaItems = [
    { label: t('repositoryCard.encryption'), value: repository.encryption },
    {
      label: t('repositoryCard.compression'),
      value: getCompressionLabel(repository.compression ?? ''),
    },
    ...(uploadRatelimitLabel
      ? [
          {
            label: t('repositoryCard.uploadLimit'),
            value: uploadRatelimitLabel,
            tooltip: t('repositoryCard.uploadLimitTooltip'),
          },
        ]
      : []),
    {
      label: t('repositoryCard.lastCompact'),
      value: repository.last_compact ? formatDateShort(repository.last_compact) : t('common.never'),
      tooltip: repository.last_compact ? formatDateTimeFull(repository.last_compact) : '',
    },
    ...(repository.source_directories?.length
      ? [
          {
            label: t('repositoryCard.sourcePaths'),
            value: `${repository.source_directories.length} ${
              repository.source_directories.length === 1
                ? t('repositoryCard.path')
                : t('repositoryCard.paths')
            }`,
            tooltip: '',
          },
        ]
      : []),
    ...(rcloneStorage
      ? [
          {
            label: t('repositoryCard.rcloneMirror'),
            value:
              rcloneStorage.rclone_remote_name && rcloneStorage.rclone_remote_path
                ? `${rcloneStorage.rclone_remote_name}:${rcloneStorage.rclone_remote_path}`
                : rcloneStorage.rclone_target || rcloneStorage.rclone_remote_path,
            tooltip: rcloneStorage.rclone_target || rcloneStorage.rclone_remote_path,
          },
        ]
      : []),
  ]

  const rcloneStatusBadge = (() => {
    if (!rcloneStorage) return null

    const failed = rcloneStorage.sync_status === 'failed'
    const cacheMissing = rcloneStorage.cache_present === false
    const status = cacheMissing ? 'cache_missing' : rcloneStorage.sync_status
    const lastSyncedTitle = rcloneStorage.last_synced_at
      ? t('repositoryCard.rcloneLastSynced', {
          when: formatDateTimeFull(rcloneStorage.last_synced_at),
        })
      : ''

    const byStatus: Record<
      string,
      { label: string; color: string; bg: string; border: string; title: string }
    > = {
      current: {
        label: t('repositoryCard.rcloneSynced'),
        color: theme.palette.success.main,
        bg: alpha(theme.palette.success.main, isDark ? 0.12 : 0.09),
        border: alpha(theme.palette.success.main, isDark ? 0.32 : 0.24),
        title: lastSyncedTitle,
      },
      pending: {
        label: t('repositoryCard.rclonePending'),
        color: theme.palette.warning.main,
        bg: alpha(theme.palette.warning.main, isDark ? 0.12 : 0.09),
        border: alpha(theme.palette.warning.main, isDark ? 0.34 : 0.24),
        title: lastSyncedTitle,
      },
      syncing: {
        label: t('repositoryCard.rcloneSyncing'),
        color: theme.palette.info.main,
        bg: alpha(theme.palette.info.main, isDark ? 0.12 : 0.09),
        border: alpha(theme.palette.info.main, isDark ? 0.34 : 0.24),
        title: rcloneStorage.rclone_target || '',
      },
      failed: {
        label: t('repositoryCard.rcloneFailed'),
        color: theme.palette.error.main,
        bg: alpha(theme.palette.error.main, isDark ? 0.12 : 0.08),
        border: alpha(theme.palette.error.main, isDark ? 0.34 : 0.24),
        title: rcloneStorage.last_sync_error
          ? t('repositoryCard.rcloneError', { message: rcloneStorage.last_sync_error })
          : '',
      },
      hydrating: {
        label: t('repositoryCard.rcloneHydrating'),
        color: theme.palette.info.main,
        bg: alpha(theme.palette.info.main, isDark ? 0.12 : 0.09),
        border: alpha(theme.palette.info.main, isDark ? 0.34 : 0.24),
        title: rcloneStorage.rclone_target || '',
      },
      cache_missing: {
        label: t('repositoryCard.rcloneHydrationRequired'),
        color: theme.palette.warning.main,
        bg: alpha(theme.palette.warning.main, isDark ? 0.12 : 0.09),
        border: alpha(theme.palette.warning.main, isDark ? 0.34 : 0.24),
        title: rcloneStorage.rclone_target || '',
      },
    }

    return (
      byStatus[status] || {
        label: status,
        color: theme.palette.text.secondary,
        bg: alpha(theme.palette.text.secondary, isDark ? 0.12 : 0.08),
        border: alpha(theme.palette.text.secondary, isDark ? 0.28 : 0.2),
        title: failed ? rcloneStorage.last_sync_error || '' : rcloneStorage.rclone_target || '',
      }
    )
  })()

  const rcloneScheduledMirrorBadge = (() => {
    if (!rcloneStorage || rcloneStorage.sync_policy !== 'scheduled') return null

    const timezoneLabel = rcloneStorage.sync_timezone || 'UTC'
    const latestScheduledJob =
      rcloneStorage.latest_sync_job?.triggered_by === 'schedule'
        ? rcloneStorage.latest_sync_job
        : null
    const hasLatestSyncJob = Boolean(rcloneStorage.latest_sync_job)
    const scheduledFailure =
      latestScheduledJob?.status === 'failed' ||
      (!hasLatestSyncJob && rcloneStorage.sync_status === 'failed')
    const failureMessage =
      latestScheduledJob?.error_text ||
      (!hasLatestSyncJob ? rcloneStorage.last_sync_error : undefined)

    if (scheduledFailure) {
      return {
        label: t('repositoryCard.rcloneScheduledFailed'),
        title: failureMessage
          ? t('repositoryCard.rcloneScheduledError', { message: failureMessage })
          : t('repositoryCard.rcloneScheduledFailed'),
        color: theme.palette.error.main,
        bg: alpha(theme.palette.error.main, isDark ? 0.12 : 0.08),
        border: alpha(theme.palette.error.main, isDark ? 0.34 : 0.24),
      }
    }

    if (!rcloneStorage.next_scheduled_sync_at) {
      return {
        label: t('repositoryCard.rcloneScheduled'),
        title: t('repositoryCard.rcloneScheduledNoNextRun', { timezone: timezoneLabel }),
        color: theme.palette.info.main,
        bg: alpha(theme.palette.info.main, isDark ? 0.12 : 0.08),
        border: alpha(theme.palette.info.main, isDark ? 0.32 : 0.24),
      }
    }

    const nextRunDate = new Date(rcloneStorage.next_scheduled_sync_at)
    if (Number.isNaN(nextRunDate.getTime())) {
      return {
        label: t('repositoryCard.rcloneScheduled'),
        title: t('repositoryCard.rcloneScheduledNoNextRun', { timezone: timezoneLabel }),
        color: theme.palette.info.main,
        bg: alpha(theme.palette.info.main, isDark ? 0.12 : 0.08),
        border: alpha(theme.palette.info.main, isDark ? 0.32 : 0.24),
      }
    }
    let whenLabel = format(
      nextRunDate,
      isThisYear(nextRunDate) ? 'MMM d · h:mm a' : 'MMM d, yyyy · h:mm a'
    )
    if (isToday(nextRunDate)) {
      whenLabel = format(nextRunDate, 'h:mm a')
    } else if (isTomorrow(nextRunDate)) {
      whenLabel = `${t('repositoryCard.tomorrow')} · ${format(nextRunDate, 'h:mm a')}`
    }

    return {
      label: t('repositoryCard.rcloneNextSyncBadge', { when: whenLabel }),
      title: t('repositoryCard.rcloneNextSyncWithSchedule', {
        when: formatDateTimeFull(rcloneStorage.next_scheduled_sync_at),
        cron: rcloneStorage.sync_cron_expression || t('repositoryCard.rcloneScheduleUnknown'),
        timezone: timezoneLabel,
      }),
      color: theme.palette.info.main,
      bg: alpha(theme.palette.info.main, isDark ? 0.12 : 0.08),
      border: alpha(theme.palette.info.main, isDark ? 0.32 : 0.24),
    }
  })()

  const agentStatusBadge = (() => {
    if (!isAgentPrimaryRepository) return null
    const normalized = (agentMachineStatus || '').toLowerCase()
    const online = normalized === 'online'
    const disabled = normalized === 'disabled' || normalized === 'revoked'
    const color = online
      ? theme.palette.success.main
      : disabled
        ? theme.palette.error.main
        : theme.palette.warning.main
    const label =
      normalized === 'online'
        ? t('repositoryCard.agentStatusOnline')
        : normalized === 'offline'
          ? t('repositoryCard.agentStatusOffline')
          : normalized === 'disabled'
            ? t('repositoryCard.agentStatusDisabled')
            : normalized === 'revoked'
              ? t('repositoryCard.agentStatusRevoked')
              : t('repositoryCard.agentStatusUnknown')

    return {
      label,
      color,
      bg: alpha(color, isDark ? 0.12 : 0.09),
      border: alpha(color, isDark ? 0.34 : 0.24),
      title: agentMachineName
        ? t('repositoryCard.agentStatusTitle', { name: agentMachineName, status: label })
        : label,
    }
  })()

  const scheduleBadge = (() => {
    if (!repository.has_schedule) return null
    const scheduleTimezone = repository.schedule_timezone || 'UTC'

    if (repository.schedule_enabled === false) {
      return {
        label: t('repositoryCard.schedulePaused'),
        title: repository.schedule_name
          ? `${t('repositoryCard.schedulePausedWithName', { name: repository.schedule_name })} (${scheduleTimezone})`
          : `${t('repositoryCard.schedulePaused')} (${scheduleTimezone})`,
        color: theme.palette.warning.main,
        bg: alpha(theme.palette.warning.main, isDark ? 0.12 : 0.1),
        border: alpha(theme.palette.warning.main, isDark ? 0.34 : 0.28),
      }
    }

    if (!repository.next_run) return null

    const nextRunDate = new Date(repository.next_run)
    let whenLabel = format(
      nextRunDate,
      isThisYear(nextRunDate) ? 'MMM d · h:mm a' : 'MMM d, yyyy · h:mm a'
    )
    if (isToday(nextRunDate)) {
      whenLabel = format(nextRunDate, 'h:mm a')
    } else if (isTomorrow(nextRunDate)) {
      whenLabel = `${t('repositoryCard.tomorrow')} · ${format(nextRunDate, 'h:mm a')}`
    }

    return {
      label: t('repositoryCard.nextBackupBadge', { when: whenLabel }),
      title: repository.schedule_name
        ? `${t('repositoryCard.nextBackupWithName', {
            name: repository.schedule_name,
            when: formatDateTimeFull(repository.next_run),
          })} (${scheduleTimezone})`
        : `${t('repositoryCard.nextBackupBadge', {
            when: formatDateTimeFull(repository.next_run),
          })} (${scheduleTimezone})`,
      color: theme.palette.success.main,
      bg: alpha(theme.palette.success.main, isDark ? 0.12 : 0.09),
      border: alpha(theme.palette.success.main, isDark ? 0.32 : 0.24),
    }
  })()

  const iconBtnSx = {
    width: 32,
    height: 32,
    borderRadius: 1.5,
    color: 'text.secondary',
    '&:hover': {
      bgcolor: isDark ? alpha('#fff', 0.07) : alpha('#000', 0.06),
      color: 'text.primary',
    },
    '&.Mui-disabled': { opacity: 0.28 },
  }

  const activeIconBtnSx = {
    ...iconBtnSx,
    color: theme.palette.primary.main,
    bgcolor: alpha(theme.palette.primary.main, 0.1),
    '&:hover': {
      bgcolor: alpha(theme.palette.primary.main, 0.18),
      color: theme.palette.primary.main,
    },
  }

  const coloredIconBtnSx = (colorKey: 'primary' | 'success' | 'secondary' | 'warning' | 'info') => {
    const color = (theme.palette[colorKey] as { main: string }).main
    return {
      ...iconBtnSx,
      color: alpha(color, isDark ? 0.65 : 0.55),
      '&:hover': {
        bgcolor: alpha(color, isDark ? 0.12 : 0.09),
        color: color,
      },
      '&.Mui-disabled': { opacity: 0.28 },
    }
  }

  return (
    <OperationalCard
      isActive={isMaintenanceRunning}
      idleAccent={ACCENT_IDLE}
      activeAccent={ACCENT_RUNNING}
    >
      {/* Subtle ambient glow — only visible when maintenance is running */}
      {isMaintenanceRunning && (
        <Box
          sx={{
            position: 'absolute',
            top: -30,
            left: -30,
            width: 160,
            height: 100,
            borderRadius: '50%',
            bgcolor: alpha(ACCENT_RUNNING, isDark ? 0.18 : 0.1),
            filter: 'blur(48px)',
            pointerEvents: 'none',
            animation: 'blobPulse 2s ease-in-out infinite',
            '@keyframes blobPulse': {
              '0%, 100%': { opacity: 1 },
              '50%': { opacity: 0.35 },
            },
          }}
        />
      )}

      <Box sx={{ px: { xs: 1.75, sm: 2 }, pt: { xs: 1.75, sm: 2 }, pb: { xs: 1.5, sm: 1.75 } }}>
        {/* ── Header ── */}
        <Box sx={{ mb: 1.5 }}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 1,
              mb: 0.4,
            }}
          >
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap' }}>
                <Typography variant="subtitle1" fontWeight={700} noWrap sx={{ lineHeight: 1.3 }}>
                  {repository.name}
                </Typography>
                {repository.mode === 'observe' && (
                  <Chip
                    label={t('repositoryCard.observeOnly')}
                    size="small"
                    color="info"
                    sx={{ height: 18, fontSize: '0.65rem', '& .MuiChip-label': { px: 0.75 } }}
                  />
                )}
                <BorgVersionChip borgVersion={repository.borg_version} />
                {isAgentPrimaryRepository && (
                  <Tooltip
                    title={
                      agentMachineName
                        ? t('repositoryCard.agentTitle', { name: agentMachineName })
                        : t('repositoryCard.agentUnknown')
                    }
                    arrow
                  >
                    <Chip
                      icon={<Bot size={12} />}
                      label={t('repositoryCard.agentLabel', {
                        name: agentMachineName || t('repositoryCard.agentUnknown'),
                      })}
                      size="small"
                      sx={{
                        height: 20,
                        maxWidth: { xs: 150, sm: 200 },
                        bgcolor: isDark ? alpha('#fff', 0.05) : alpha('#000', 0.035),
                        color: 'text.secondary',
                        border: '1px solid',
                        borderColor: isDark ? alpha('#fff', 0.12) : alpha('#000', 0.1),
                        fontSize: '0.64rem',
                        fontWeight: 700,
                        '& .MuiChip-icon': {
                          ml: 0.75,
                          color: 'inherit',
                        },
                        '& .MuiChip-label': {
                          px: 0.75,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        },
                      }}
                    />
                  </Tooltip>
                )}
                {agentStatusBadge && (
                  <Tooltip title={agentStatusBadge.title} arrow>
                    <Chip
                      label={agentStatusBadge.label}
                      size="small"
                      sx={{
                        height: 20,
                        maxWidth: { xs: 110, sm: 140 },
                        bgcolor: agentStatusBadge.bg,
                        color: agentStatusBadge.color,
                        border: '1px solid',
                        borderColor: agentStatusBadge.border,
                        fontSize: '0.64rem',
                        fontWeight: 700,
                        '& .MuiChip-label': {
                          px: 0.75,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        },
                      }}
                    />
                  </Tooltip>
                )}
                {rcloneStatusBadge && (
                  <Tooltip title={rcloneStatusBadge.title} arrow>
                    <Chip
                      icon={<Cloud size={12} />}
                      label={rcloneStatusBadge.label}
                      size="small"
                      sx={{
                        height: 20,
                        maxWidth: { xs: 140, sm: 180 },
                        bgcolor: rcloneStatusBadge.bg,
                        color: rcloneStatusBadge.color,
                        border: '1px solid',
                        borderColor: rcloneStatusBadge.border,
                        fontSize: '0.64rem',
                        fontWeight: 700,
                        '& .MuiChip-icon': {
                          ml: 0.75,
                          color: 'inherit',
                        },
                        '& .MuiChip-label': {
                          px: 0.75,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        },
                      }}
                    />
                  </Tooltip>
                )}
                {rcloneScheduledMirrorBadge && (
                  <Tooltip title={rcloneScheduledMirrorBadge.title} arrow>
                    <Chip
                      icon={<CalendarClock size={12} />}
                      label={rcloneScheduledMirrorBadge.label}
                      size="small"
                      sx={{
                        height: 20,
                        maxWidth: { xs: 150, sm: 190 },
                        bgcolor: rcloneScheduledMirrorBadge.bg,
                        color: rcloneScheduledMirrorBadge.color,
                        border: '1px solid',
                        borderColor: rcloneScheduledMirrorBadge.border,
                        fontSize: '0.64rem',
                        fontWeight: 700,
                        '& .MuiChip-icon': {
                          ml: 0.75,
                          color: 'inherit',
                        },
                        '& .MuiChip-label': {
                          px: 0.75,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        },
                      }}
                    />
                  </Tooltip>
                )}
              </Box>
            </Box>

            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'flex-end',
                gap: 0.75,
                flexShrink: 0,
                minWidth: 0,
                maxWidth: { xs: '46%', sm: '42%' },
              }}
            >
              {scheduleBadge && (
                <Tooltip title={scheduleBadge.title} arrow placement="left">
                  <Chip
                    label={scheduleBadge.label}
                    size="small"
                    sx={{
                      height: 20,
                      maxWidth: { xs: 140, sm: 170 },
                      flexShrink: 1,
                      minWidth: 0,
                      bgcolor: scheduleBadge.bg,
                      color: scheduleBadge.color,
                      border: '1px solid',
                      borderColor: scheduleBadge.border,
                      fontSize: '0.64rem',
                      fontWeight: 700,
                      '& .MuiChip-label': {
                        px: 0.9,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      },
                    }}
                  />
                </Tooltip>
              )}

              {canManageRepository && (
                <Tooltip title={t('repositoryCard.edit')} arrow placement="left">
                  <IconButton
                    size="small"
                    onClick={onEdit}
                    aria-label={t('repositoryCard.edit')}
                    sx={{
                      width: 28,
                      height: 28,
                      borderRadius: 1,
                      flexShrink: 0,
                      color: 'text.disabled',
                      '&:hover': {
                        color: 'text.primary',
                        bgcolor: isDark ? alpha('#fff', 0.07) : alpha('#000', 0.06),
                      },
                    }}
                  >
                    <SquarePen size={14} />
                  </IconButton>
                </Tooltip>
              )}
            </Box>
          </Box>

          <Typography
            variant="body2"
            title={repository.path}
            sx={{
              fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
              fontSize: '0.7rem',
              color: 'text.disabled',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {repository.path}
          </Typography>
        </Box>

        {/* ── Key Stats Band ── */}
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: 'repeat(2, 1fr)', sm: 'repeat(4, 1fr)' },
            borderRadius: 1.5,
            border: '1px solid',
            borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
            overflow: 'hidden',
            mb: 1.5,
            bgcolor: isDark ? alpha('#fff', 0.025) : alpha('#000', 0.018),
          }}
        >
          {keyStats.map((stat, i) => {
            const isRightColXs = i % 2 === 1
            const isLastSm = i === keyStats.length - 1
            const isFirstRowXs = i < 2
            const colorKey = STAT_COLORS[i]
            const statColor = (theme.palette[colorKey] as { main: string }).main
            return (
              <Tooltip key={stat.label} title={stat.tooltip} arrow>
                <Box
                  sx={{
                    px: 1.5,
                    py: 1.1,
                    cursor: stat.tooltip ? 'help' : 'default',
                    borderRight: isLastSm ? 0 : '1px solid',
                    borderBottom: { xs: isFirstRowXs ? '1px solid' : 0, sm: 0 },
                    borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                    ...(isRightColXs && {
                      borderRight: { xs: 0, sm: isLastSm ? 0 : '1px solid' },
                    }),
                  }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.35 }}>
                    <Box
                      sx={{
                        color: alpha(statColor, 0.7),
                        display: 'flex',
                        alignItems: 'center',
                      }}
                    >
                      {STAT_ICONS[i]}
                    </Box>
                    <Typography
                      sx={{
                        fontSize: '0.58rem',
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        letterSpacing: '0.07em',
                        color: alpha(statColor, 0.7),
                        lineHeight: 1,
                      }}
                    >
                      {stat.label}
                    </Typography>
                  </Box>
                  <Typography
                    variant="body2"
                    fontWeight={600}
                    noWrap
                    sx={{ fontVariantNumeric: 'tabular-nums', fontSize: '0.85rem' }}
                  >
                    {stat.value}
                  </Typography>
                </Box>
              </Tooltip>
            )
          })}
        </Box>

        {/* ── Secondary Metadata ── */}
        <Box
          sx={{
            display: 'flex',
            gap: { xs: 1.25, sm: 1.75 },
            flexWrap: 'wrap',
            mb: 1.5,
            px: 0.25,
          }}
        >
          {metaItems.map((m) => (
            <Tooltip key={m.label} title={m.tooltip || ''} arrow>
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 0.4,
                  cursor: m.tooltip ? 'help' : 'default',
                }}
              >
                <Typography sx={{ fontSize: '0.68rem', color: 'text.disabled', lineHeight: 1 }}>
                  {m.label}:
                </Typography>
                <Typography
                  sx={{
                    fontSize: '0.68rem',
                    fontWeight: 600,
                    color: 'text.secondary',
                    lineHeight: 1,
                  }}
                >
                  {m.value}
                </Typography>
              </Box>
            </Tooltip>
          ))}
        </Box>

        {hasManualBackupSources && canCreatePlan && (
          <Box
            sx={{
              display: 'flex',
              alignItems: { xs: 'stretch', sm: 'center' },
              justifyContent: 'space-between',
              flexDirection: { xs: 'column', sm: 'row' },
              gap: 1,
              mb: 1.5,
              px: 1.25,
              py: 1,
              borderRadius: 1.5,
              border: '1px solid',
              borderColor: alpha(theme.palette.primary.main, isDark ? 0.28 : 0.2),
              bgcolor: alpha(theme.palette.primary.main, isDark ? 0.1 : 0.06),
            }}
          >
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="caption" fontWeight={700} color="primary.main">
                {t('repositoryCard.legacySources.title')}
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block">
                {t('repositoryCard.legacySources.description')}
              </Typography>
            </Box>
          </Box>
        )}

        {/* ── Action Bar ── */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            columnGap: 1,
            rowGap: 0.75,
            flexWrap: 'wrap',
            justifyContent: 'space-between',
            pt: 1.25,
            borderTop: '1px solid',
            borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
          }}
        >
          {/* Secondary icon actions — left cluster */}
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 0.25,
              flex: '1 1 260px',
              flexWrap: 'wrap',
              minWidth: 0,
            }}
          >
            {canDo('view') && (
              <Tooltip title={t('repositoryCard.buttons.info')} arrow>
                <span>
                  <IconButton
                    size="small"
                    onClick={() => {
                      trackRepository(EventAction.VIEW, repository)
                      onViewInfo()
                    }}
                    aria-label={t('repositoryCard.buttons.info')}
                    disabled={isMaintenanceRunning}
                    sx={coloredIconBtnSx('primary')}
                  >
                    <Info size={16} />
                  </IconButton>
                </span>
              </Tooltip>
            )}

            {canDo('maintenance') && (
              <Tooltip title={t('repositoryCard.buttons.check')} arrow>
                <span>
                  <IconButton
                    size="small"
                    onClick={onCheck}
                    aria-label={t('repositoryCard.buttons.check')}
                    disabled={isMaintenanceRunning}
                    sx={checkJob ? activeIconBtnSx : coloredIconBtnSx('success')}
                  >
                    {checkJob ? (
                      <RefreshCw size={16} className="animate-spin" />
                    ) : (
                      <ShieldCheck size={16} />
                    )}
                  </IconButton>
                </span>
              </Tooltip>
            )}

            {canDo('maintenance') && capabilities.canCompact && (
              <Tooltip title={t('repositoryCard.buttons.compact')} arrow>
                <span>
                  <IconButton
                    size="small"
                    onClick={onCompact}
                    aria-label={t('repositoryCard.buttons.compact')}
                    disabled={isMaintenanceRunning}
                    sx={compactJob ? activeIconBtnSx : coloredIconBtnSx('secondary')}
                  >
                    {compactJob ? (
                      <RefreshCw size={16} className="animate-spin" />
                    ) : (
                      <Package2 size={16} />
                    )}
                  </IconButton>
                </span>
              </Tooltip>
            )}

            {canDo('maintenance') && capabilities.canPrune && (
              <Tooltip title={t('repositoryCard.buttons.prune')} arrow>
                <span>
                  <IconButton
                    size="small"
                    onClick={onPrune}
                    aria-label={t('repositoryCard.buttons.prune')}
                    disabled={isMaintenanceRunning}
                    sx={pruneJob ? activeIconBtnSx : coloredIconBtnSx('warning')}
                  >
                    {pruneJob ? (
                      <RefreshCw size={16} className="animate-spin" />
                    ) : (
                      <Scissors size={16} />
                    )}
                  </IconButton>
                </span>
              </Tooltip>
            )}

            {canDo('view') && (
              <Tooltip title={t('repositoryCard.buttons.viewArchives')} arrow>
                <span>
                  <IconButton
                    size="small"
                    onClick={() => {
                      trackArchive(EventAction.VIEW, repository)
                      onViewArchives()
                    }}
                    aria-label={t('repositoryCard.buttons.viewArchives')}
                    disabled={isMaintenanceRunning}
                    sx={coloredIconBtnSx('info')}
                  >
                    <FolderOpen size={16} />
                  </IconButton>
                </span>
              </Tooltip>
            )}

            {canDo('view') && onViewBackupPlans && (
              <Tooltip title={t('repositoryCard.buttons.viewBackupPlans')} arrow>
                <span>
                  <IconButton
                    size="small"
                    onClick={() => {
                      trackRepository(EventAction.VIEW, repository, {
                        destination: 'backup_plans',
                      })
                      onViewBackupPlans()
                    }}
                    aria-label={t('repositoryCard.buttons.viewBackupPlans')}
                    disabled={isMaintenanceRunning}
                    sx={coloredIconBtnSx('primary')}
                  >
                    <ListChecks size={16} />
                  </IconButton>
                </span>
              </Tooltip>
            )}

            {rcloneStorage && canDo('maintenance') && (
              <>
                <Tooltip title={t('repositoryCard.buttons.rcloneSync')} arrow>
                  <span>
                    <IconButton
                      size="small"
                      onClick={onRcloneSync}
                      aria-label={t('repositoryCard.buttons.rcloneSync')}
                      disabled={!onRcloneSync || isMaintenanceRunning || rcloneOperationRunning}
                      sx={coloredIconBtnSx('info')}
                    >
                      <CloudUpload size={16} />
                    </IconButton>
                  </span>
                </Tooltip>
                {canHydrateRclone && (
                  <Tooltip title={t('repositoryCard.buttons.rcloneHydrate')} arrow>
                    <span>
                      <IconButton
                        size="small"
                        onClick={onRcloneHydrate}
                        aria-label={t('repositoryCard.buttons.rcloneHydrate')}
                        disabled={
                          !onRcloneHydrate || isMaintenanceRunning || rcloneOperationRunning
                        }
                        sx={coloredIconBtnSx('primary')}
                      >
                        <CloudDownload size={16} />
                      </IconButton>
                    </span>
                  </Tooltip>
                )}
              </>
            )}

            {/* Separated repository actions */}
            {hasSeparatedRepositoryActions && (
              <>
                <Box
                  sx={{
                    width: '1px',
                    height: 18,
                    bgcolor: isDark ? alpha('#fff', 0.1) : alpha('#000', 0.1),
                    mx: 0.25,
                    flexShrink: 0,
                  }}
                />
                {canBreakLock && (
                  <Tooltip title={t('repositoryCard.buttons.breakLock')} arrow>
                    <span>
                      <IconButton
                        size="small"
                        onClick={onBreakLock}
                        aria-label={t('repositoryCard.buttons.breakLock')}
                        disabled={isMaintenanceRunning}
                        sx={coloredIconBtnSx('warning')}
                      >
                        <Unlock size={16} />
                      </IconButton>
                    </span>
                  </Tooltip>
                )}
                {canShowDestructiveActions && (
                  <>
                    <Tooltip title={t('repositoryCard.buttons.wipeContents')} arrow>
                      <IconButton
                        size="small"
                        onClick={onWipeContents}
                        aria-label={t('repositoryCard.buttons.wipeContents')}
                        disabled={isMaintenanceRunning}
                        sx={{
                          ...iconBtnSx,
                          color: alpha(theme.palette.error.main, 0.56),
                          '&:hover': {
                            color: theme.palette.error.main,
                            bgcolor: alpha(theme.palette.error.main, 0.09),
                          },
                        }}
                      >
                        <Eraser size={16} />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title={t('repositoryCard.buttons.delete')} arrow>
                      <IconButton
                        size="small"
                        onClick={onDelete}
                        aria-label={t('repositoryCard.buttons.delete')}
                        sx={{
                          ...iconBtnSx,
                          color: alpha(theme.palette.error.main, 0.6),
                          '&:hover': {
                            color: theme.palette.error.main,
                            bgcolor: alpha(theme.palette.error.main, 0.1),
                          },
                        }}
                      >
                        <Trash2 size={16} />
                      </IconButton>
                    </Tooltip>
                    {canPermanentDeleteRepository && onPermanentDelete && (
                      <Tooltip title={t('repositoryCard.buttons.permanentDelete')} arrow>
                        <IconButton
                          size="small"
                          onClick={onPermanentDelete}
                          aria-label={t('repositoryCard.buttons.permanentDelete')}
                          disabled={isMaintenanceRunning}
                          sx={{
                            ...iconBtnSx,
                            color: alpha(theme.palette.error.main, 0.72),
                            '&:hover': {
                              color: theme.palette.error.dark,
                              bgcolor: alpha(theme.palette.error.main, 0.13),
                            },
                          }}
                        >
                          <FolderX size={16} />
                        </IconButton>
                      </Tooltip>
                    )}
                  </>
                )}
              </>
            )}
          </Box>

          {(canEnableCloudMirror || canCreatePlan || canRunLegacyBackup) && (
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 0.75,
                flex: '1 1 260px',
                flexWrap: 'wrap',
                justifyContent: { xs: 'flex-start', sm: 'flex-end' },
                minWidth: 0,
              }}
            >
              {canEnableCloudMirror && (
                <Tooltip title={t('repositoryCard.buttons.enableCloudMirror')} arrow>
                  <span>
                    <Button
                      variant="outlined"
                      size="small"
                      startIcon={<Cloud size={13} />}
                      onClick={onEdit}
                      disabled={isMaintenanceRunning}
                      sx={{
                        fontSize: '0.76rem',
                        height: 30,
                        flexShrink: 0,
                        px: { xs: 0.85, sm: 1.25 },
                        minWidth: 'unset',
                        '& .MuiButton-startIcon': {
                          mr: { xs: 0, sm: 0.5 },
                          ml: { xs: 0, sm: '-2px' },
                        },
                      }}
                    >
                      <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>
                        {t('repositoryCard.buttons.enableCloudMirror')}
                      </Box>
                    </Button>
                  </span>
                </Tooltip>
              )}

              {canRunLegacyBackup && (
                <Tooltip title={t('repositoryCard.buttons.legacyBackupTooltip')} arrow>
                  <span>
                    <Button
                      variant="outlined"
                      size="small"
                      color="success"
                      startIcon={<Play size={13} />}
                      onClick={() => {
                        trackBackup(EventAction.START, 'legacy_repository', repository)
                        onBackupNow()
                      }}
                      disabled={isMaintenanceRunning}
                      sx={{
                        fontSize: '0.76rem',
                        height: 30,
                        flexShrink: 0,
                        px: { xs: 0.85, sm: 1.25 },
                        minWidth: 'unset',
                        '& .MuiButton-startIcon': {
                          mr: { xs: 0, sm: 0.5 },
                          ml: { xs: 0, sm: '-2px' },
                        },
                      }}
                    >
                      <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>
                        {t('repositoryCard.buttons.legacyBackup')}
                      </Box>
                    </Button>
                  </span>
                </Tooltip>
              )}

              {canCreatePlan && (
                <Tooltip title={t('repositoryCard.buttons.createBackupPlan')} arrow>
                  <span>
                    <Button
                      variant="contained"
                      size="small"
                      startIcon={<ClipboardList size={13} />}
                      onClick={onCreateBackupPlan}
                      disabled={isMaintenanceRunning}
                      sx={{
                        fontSize: '0.78rem',
                        height: 30,
                        flexShrink: 0,
                        px: { xs: 0.85, sm: 1.5 },
                        minWidth: 'unset',
                        '& .MuiButton-startIcon': {
                          mr: { xs: 0, sm: 0.5 },
                          ml: { xs: 0, sm: '-2px' },
                        },
                      }}
                    >
                      <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>
                        {t('repositoryCard.buttons.createBackupPlan')}
                      </Box>
                    </Button>
                  </span>
                </Tooltip>
              )}
            </Box>
          )}
        </Box>

        {/* ── Running State Message ── */}
        {(checkJob?.progress_message || compactJob?.progress_message || elapsedTime) && (
          <Box
            sx={{
              mt: 1.25,
              px: 1.5,
              py: 0.875,
              borderRadius: 1,
              bgcolor: alpha(ACCENT_RUNNING, 0.07),
              border: '1px solid',
              borderColor: alpha(ACCENT_RUNNING, 0.22),
            }}
          >
            {(checkJob?.progress_message || compactJob?.progress_message) && (
              <Typography
                variant="caption"
                sx={{
                  display: 'block',
                  color: ACCENT_RUNNING,
                  fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
                  fontSize: '0.72rem',
                }}
              >
                {checkJob?.progress_message || compactJob?.progress_message}
              </Typography>
            )}
            {elapsedTime && (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: 'block', mt: 0.25 }}
              >
                {elapsedTime}
              </Typography>
            )}
          </Box>
        )}
      </Box>
    </OperationalCard>
  )
}

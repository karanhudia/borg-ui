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
  Pencil,
  Archive,
  HardDrive,
  Clock,
  ScanSearch,
  RefreshCw,
} from 'lucide-react'
import { useMaintenanceJobs } from '../hooks/useMaintenanceJobs'
import BorgVersionChip from './BorgVersionChip'
import { getRepoCapabilities } from '../utils/repoCapabilities'
import { formatDateShort, formatDateTimeFull, formatElapsedTime } from '../utils/dateUtils'
import { useQueryClient } from '@tanstack/react-query'
import { useAnalytics } from '../hooks/useAnalytics'
import { Repository } from '../types'
import type { RepoAction } from '../hooks/usePermissions'

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
  canManageRepository?: boolean
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
  onEdit,
  onDelete,
  onBackupNow,
  onViewArchives,
  getCompressionLabel,
  canManageRepository = false,
  canDo,
  onJobCompleted,
}: RepositoryCardProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const { trackRepository, trackBackup, trackArchive, EventAction } = useAnalytics()

  const capabilities = getRepoCapabilities(repository)
  const { hasRunningJobs, checkJob, compactJob, pruneJob } = useMaintenanceJobs(repository.id, true)
  const isMaintenanceRunning = hasRunningJobs

  const [elapsedTime, setElapsedTime] = useState('')

  useEffect(() => {
    if (!hasRunningJobs) {
      setElapsedTime('')
      return
    }
    const startTime = checkJob?.started_at || compactJob?.started_at || pruneJob?.started_at
    if (!startTime) return
    setElapsedTime(formatElapsedTime(startTime))
    const interval = setInterval(() => {
      setElapsedTime(formatElapsedTime(startTime))
    }, 1000)
    return () => clearInterval(interval)
  }, [hasRunningJobs, checkJob?.started_at, compactJob?.started_at, pruneJob?.started_at])

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
  ]

  const scheduleBadge = (() => {
    if (!repository.has_schedule) return null

    if (repository.schedule_enabled === false) {
      return {
        label: t('repositoryCard.schedulePaused'),
        title: repository.schedule_name
          ? t('repositoryCard.schedulePausedWithName', { name: repository.schedule_name })
          : t('repositoryCard.schedulePaused'),
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
        ? t('repositoryCard.nextBackupWithName', {
            name: repository.schedule_name,
            when: formatDateTimeFull(repository.next_run),
          })
        : t('repositoryCard.nextBackupBadge', { when: formatDateTimeFull(repository.next_run) }),
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
    <Box
      sx={{
        position: 'relative',
        borderRadius: 2,
        bgcolor: 'background.paper',
        overflow: 'hidden',
        maxWidth: '100%',
        minWidth: 0,
        boxShadow: isMaintenanceRunning
          ? `0 0 0 1px ${alpha(ACCENT_RUNNING, 0.4)}, 0 4px 16px ${alpha('#000', 0.2)}, 0 2px 6px ${alpha(ACCENT_RUNNING, 0.1)}`
          : isDark
            ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 4px 16px ${alpha('#000', 0.25)}`
            : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 8px ${alpha('#000', 0.07)}`,
        transition: 'all 200ms cubic-bezier(0.16,1,0.3,1)',
        '&:hover': {
          transform: 'translateY(-2px)',
          boxShadow: isMaintenanceRunning
            ? `0 0 0 1px ${alpha(ACCENT_RUNNING, 0.55)}, 0 8px 24px ${alpha('#000', 0.28)}, 0 4px 12px ${alpha(ACCENT_RUNNING, 0.15)}`
            : isDark
              ? `0 0 0 1px ${alpha(ACCENT_IDLE, 0.4)}, 0 8px 24px ${alpha('#000', 0.3)}, 0 2px 8px ${alpha(ACCENT_IDLE, 0.1)}`
              : `0 0 0 1px ${alpha(ACCENT_IDLE, 0.3)}, 0 8px 24px ${alpha('#000', 0.12)}, 0 2px 8px ${alpha(ACCENT_IDLE, 0.08)}`,
        },
      }}
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
                    <Pencil size={14} />
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

        {/* ── Action Bar ── */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 0.5,
            pt: 1.25,
            borderTop: '1px solid',
            borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
          }}
        >
          {/* Secondary icon actions — left cluster */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25, flex: 1 }}>
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

            {/* Delete — separated with a vertical rule */}
            {canManageRepository && capabilities.canDelete && (
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
              </>
            )}
          </Box>

          {/* Primary action — Backup Now */}
          {canDo('backup') && repository.mode === 'full' && (
            <Tooltip
              title={isMaintenanceRunning ? '' : t('repositoryCard.buttons.backupNow')}
              arrow
            >
              <span>
                <Button
                  variant="contained"
                  size="small"
                  startIcon={<Play size={13} />}
                  onClick={() => {
                    trackBackup(EventAction.START, undefined, repository)
                    onBackupNow()
                  }}
                  disabled={isMaintenanceRunning}
                  sx={{
                    bgcolor: ACCENT_IDLE,
                    color: '#fff',
                    fontSize: '0.78rem',
                    height: 30,
                    flexShrink: 0,
                    px: { xs: 0.85, sm: 1.5 },
                    minWidth: 'unset',
                    boxShadow: `0 2px 10px ${alpha(ACCENT_IDLE, 0.38)}`,
                    '& .MuiButton-startIcon': { mr: { xs: 0, sm: 0.5 }, ml: { xs: 0, sm: '-2px' } },
                    '&:hover': {
                      bgcolor: '#047857',
                      boxShadow: `0 4px 18px ${alpha(ACCENT_IDLE, 0.5)}`,
                    },
                    '&.Mui-disabled': {
                      bgcolor: isDark ? alpha('#fff', 0.08) : alpha('#000', 0.08),
                      color: 'text.disabled',
                      boxShadow: 'none',
                    },
                  }}
                >
                  <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>
                    {t('repositoryCard.buttons.backupNow')}
                  </Box>
                </Button>
              </span>
            </Tooltip>
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
    </Box>
  )
}

import {
  alpha,
  Box,
  Button,
  Chip,
  CircularProgress,
  IconButton,
  Switch,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material'
import { CalendarClock, Database, Folder, History, Play, SquarePen, Trash2 } from 'lucide-react'
import type { TFunction } from 'i18next'

import BackupPlanScheduleBadge from '../../../components/BackupPlanScheduleBadge'
import { formatRelativeTime, formatTimeRange } from '../../../utils/dateUtils'
import type { BackupPlan, BackupPlanRun } from '../../../types'
import { RunStatusLeadIcon } from './RunStatusLeadIcon'
import { runStatusIconColor } from './runStatusIconColor'

const PLAN_STAT_COLORS = ['primary', 'success', 'warning', 'info'] as const

interface BackupPlanIdleCardProps {
  plan: BackupPlan
  latestRun: BackupPlanRun | undefined
  isHighlighted: boolean
  planUsesProFeatures: boolean
  planBlockedByLicense: boolean
  planIsStarting: boolean
  runDisabled: boolean
  runTooltip: string
  sourceTypeLabel: string
  hasRunHistory: boolean
  onRun: () => void
  onToggle: () => void
  onEdit: () => void
  onDelete: () => void
  onViewHistory: () => void
  onViewRepositories: () => void
  planIsToggling: boolean
  t: TFunction
  formatStatusLabel: (status?: string) => string
}

export function BackupPlanIdleCard({
  plan,
  latestRun,
  isHighlighted,
  planUsesProFeatures,
  planBlockedByLicense,
  planIsStarting,
  runDisabled,
  runTooltip,
  sourceTypeLabel,
  hasRunHistory,
  onRun,
  onToggle,
  onEdit,
  onDelete,
  onViewHistory,
  onViewRepositories,
  planIsToggling,
  t,
  formatStatusLabel,
}: BackupPlanIdleCardProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  const ACCENT_IDLE = theme.palette.success.main
  const ACCENT_HIGHLIGHT = theme.palette.primary.main

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

  const coloredIconBtnSx = (colorKey: 'primary' | 'success' | 'secondary' | 'warning' | 'info') => {
    const color = (theme.palette[colorKey] as { main: string }).main
    return {
      ...iconBtnSx,
      color: alpha(color, isDark ? 0.65 : 0.55),
      '&:hover': {
        bgcolor: alpha(color, isDark ? 0.12 : 0.09),
        color,
      },
      '&.Mui-disabled': { opacity: 0.28 },
    }
  }

  const lastRunStartedAt = latestRun?.started_at || latestRun?.created_at
  const lastRunValue = lastRunStartedAt ? formatRelativeTime(lastRunStartedAt) : t('common.never')
  const lastRunTooltip = lastRunStartedAt
    ? `${formatStatusLabel(latestRun?.status)} · ${formatTimeRange(
        latestRun?.started_at ?? null,
        latestRun?.completed_at ?? null,
        latestRun?.status
      )}`
    : ''

  const scheduledValue = plan.schedule_enabled
    ? plan.next_run
      ? formatRelativeTime(plan.next_run)
      : t('backupPlans.status.scheduledBadge', { defaultValue: 'Scheduled' })
    : t('backupPlans.status.manualOnly')

  const keyStats = [
    {
      label: t('backupPlans.wizard.review.sources'),
      value: t('backupPlans.status.sourcePathCount', {
        count: plan.source_directories.length,
      }),
      icon: <Folder size={11} />,
      tooltip: '',
    },
    {
      label: t('backupPlans.wizard.review.repositories'),
      value: t('backupPlans.status.repositoryCount', {
        count: plan.repository_count,
      }),
      icon: <Database size={11} />,
      tooltip: '',
    },
    {
      label: t('backupPlans.status.lastRunLabel', { defaultValue: 'Last run' }),
      value: lastRunValue,
      icon: latestRun ? <RunStatusLeadIcon status={latestRun.status} /> : <History size={11} />,
      iconColor: latestRun ? runStatusIconColor(latestRun.status) : undefined,
      tooltip: lastRunTooltip,
    },
    {
      label: t('backupPlans.status.nextRunLabel', { defaultValue: 'Next run' }),
      value: scheduledValue,
      icon: <CalendarClock size={11} />,
      tooltip: plan.schedule_enabled && plan.cron_expression ? plan.cron_expression : '',
    },
  ]

  const metaItems: Array<{ label: string; value: string }> = [
    { label: t('backupPlans.wizard.review.sourceLocation'), value: sourceTypeLabel },
  ]
  if (plan.repository_count > 1) {
    metaItems.push({
      label: t('backupPlans.wizard.review.runMode'),
      value:
        plan.repository_run_mode === 'parallel'
          ? t('backupPlans.status.parallel')
          : t('backupPlans.status.series'),
    })
  }
  metaItems.push({
    label: t('backupPlans.wizard.review.compression'),
    value: plan.compression,
  })

  return (
    <Box
      id={`backup-plan-${plan.id}`}
      sx={{
        position: 'relative',
        borderRadius: 2,
        bgcolor: 'background.paper',
        overflow: 'hidden',
        maxWidth: '100%',
        minWidth: 0,
        opacity: plan.enabled ? 1 : 0.65,
        boxShadow: isHighlighted
          ? `0 0 0 1px ${alpha(ACCENT_HIGHLIGHT, 0.6)}, 0 4px 16px ${alpha('#000', 0.2)}, 0 2px 8px ${alpha(ACCENT_HIGHLIGHT, 0.18)}`
          : isDark
            ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 4px 16px ${alpha('#000', 0.25)}`
            : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 8px ${alpha('#000', 0.07)}`,
        transition: 'all 200ms cubic-bezier(0.16,1,0.3,1)',
        '&:hover': {
          transform: 'translateY(-2px)',
          boxShadow: isDark
            ? `0 0 0 1px ${alpha(ACCENT_IDLE, 0.4)}, 0 8px 24px ${alpha('#000', 0.3)}, 0 2px 8px ${alpha(ACCENT_IDLE, 0.1)}`
            : `0 0 0 1px ${alpha(ACCENT_IDLE, 0.3)}, 0 8px 24px ${alpha('#000', 0.12)}, 0 2px 8px ${alpha(ACCENT_IDLE, 0.08)}`,
        },
      }}
    >
      <Box sx={{ px: { xs: 1.75, sm: 2 }, pt: { xs: 1.75, sm: 2 }, pb: { xs: 1.5, sm: 1.75 } }}>
        <Box sx={{ mb: 1.5 }}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 1,
              mb: plan.description ? 0.4 : 0,
            }}
          >
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap' }}>
                <Typography variant="subtitle1" fontWeight={700} noWrap sx={{ lineHeight: 1.3 }}>
                  {plan.name}
                </Typography>
                {planUsesProFeatures && (
                  <Chip
                    size="small"
                    color={planBlockedByLicense ? 'warning' : 'primary'}
                    variant={planBlockedByLicense ? 'filled' : 'outlined'}
                    label={
                      planBlockedByLicense
                        ? t('backupPlans.status.proRequired')
                        : t('backupPlans.status.pro')
                    }
                    sx={{
                      height: 18,
                      fontSize: '0.65rem',
                      '& .MuiChip-label': { px: 0.75 },
                    }}
                  />
                )}
                {isHighlighted && (
                  <Chip
                    size="small"
                    label={t('backupPlans.status.created')}
                    color="primary"
                    sx={{
                      height: 18,
                      fontSize: '0.65rem',
                      '& .MuiChip-label': { px: 0.75 },
                    }}
                  />
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
              }}
            >
              <BackupPlanScheduleBadge
                scheduleEnabled={plan.schedule_enabled}
                nextRun={plan.next_run}
                cronExpression={plan.cron_expression}
                timezone={plan.timezone}
              />
              <Tooltip title={t('backupPlans.actions.edit')} arrow placement="left">
                <IconButton
                  size="small"
                  onClick={onEdit}
                  aria-label={t('backupPlans.actions.edit')}
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
            </Box>
          </Box>

          {plan.description && (
            <Typography
              variant="body2"
              sx={{
                fontSize: '0.7rem',
                color: 'text.disabled',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
              title={plan.description}
            >
              {plan.description}
            </Typography>
          )}
        </Box>

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
            const colorKey = PLAN_STAT_COLORS[i]
            const statColor = (theme.palette[colorKey] as { main: string }).main
            const iconColor = stat.iconColor || alpha(statColor, 0.7)
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
                        color: iconColor,
                        display: 'flex',
                        alignItems: 'center',
                      }}
                    >
                      {stat.icon}
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
            <Box
              key={m.label}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 0.4,
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
          ))}
        </Box>

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
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25, flex: 1 }}>
            <Tooltip
              title={
                plan.enabled
                  ? t('backupPlans.status.clickToDisable')
                  : t('backupPlans.status.clickToEnable')
              }
              arrow
            >
              <Box
                component="label"
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 0.25,
                  cursor: planIsToggling ? 'default' : 'pointer',
                  userSelect: 'none',
                  pr: 0.75,
                }}
              >
                <Switch
                  checked={plan.enabled}
                  size="small"
                  color="success"
                  disabled={planIsToggling}
                  onChange={onToggle}
                  inputProps={{
                    'aria-label': `${
                      plan.enabled
                        ? t('backupPlans.status.clickToDisable')
                        : t('backupPlans.status.clickToEnable')
                    }: ${plan.name}`,
                  }}
                />
                <Typography
                  variant="caption"
                  sx={{
                    fontWeight: 600,
                    fontSize: '0.7rem',
                    color: plan.enabled ? 'success.main' : 'text.disabled',
                    lineHeight: 1,
                  }}
                >
                  {plan.enabled
                    ? t('backupPlans.status.enabled')
                    : t('backupPlans.status.disabled')}
                </Typography>
              </Box>
            </Tooltip>

            <Box
              sx={{
                width: '1px',
                height: 18,
                bgcolor: isDark ? alpha('#fff', 0.1) : alpha('#000', 0.1),
                mx: 0.25,
                flexShrink: 0,
              }}
            />

            <Tooltip title={t('backupPlans.actions.history', { defaultValue: 'History' })} arrow>
              <span>
                <IconButton
                  size="small"
                  onClick={onViewHistory}
                  disabled={!hasRunHistory}
                  aria-label={t('backupPlans.actions.history', { defaultValue: 'History' })}
                  sx={coloredIconBtnSx('info')}
                >
                  <History size={16} />
                </IconButton>
              </span>
            </Tooltip>

            <Tooltip
              title={t('backupPlans.actions.viewRepositories', {
                defaultValue: 'View repositories',
              })}
              arrow
            >
              <IconButton
                size="small"
                onClick={onViewRepositories}
                aria-label={t('backupPlans.actions.viewRepositories', {
                  defaultValue: 'View repositories',
                })}
                sx={coloredIconBtnSx('primary')}
              >
                <Database size={16} />
              </IconButton>
            </Tooltip>

            <Box
              sx={{
                width: '1px',
                height: 18,
                bgcolor: isDark ? alpha('#fff', 0.1) : alpha('#000', 0.1),
                mx: 0.25,
                flexShrink: 0,
              }}
            />
            <Tooltip title={t('backupPlans.actions.delete')} arrow>
              <IconButton
                size="small"
                onClick={onDelete}
                aria-label={t('backupPlans.actions.delete')}
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
          </Box>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexShrink: 0 }}>
            <Tooltip title={runTooltip} placement="top">
              <span>
                <Button
                  variant="contained"
                  size="small"
                  color="success"
                  startIcon={
                    planIsStarting ? (
                      <CircularProgress size={12} color="inherit" />
                    ) : (
                      <Play size={13} />
                    )
                  }
                  disabled={runDisabled}
                  onClick={onRun}
                  sx={{
                    fontSize: '0.78rem',
                    height: 30,
                    flexShrink: 0,
                    px: { xs: 0.85, sm: 1.5 },
                    minWidth: 'unset',
                    textTransform: 'none',
                    '& .MuiButton-startIcon': {
                      mr: { xs: 0, sm: 0.5 },
                      ml: { xs: 0, sm: '-2px' },
                    },
                  }}
                >
                  <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>
                    {t('backupPlans.actions.run')}
                  </Box>
                </Button>
              </span>
            </Tooltip>
          </Box>
        </Box>
      </Box>
    </Box>
  )
}

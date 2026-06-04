import React, { useState } from 'react'
import {
  Box,
  Button,
  Chip,
  Collapse,
  IconButton,
  Stack,
  Tooltip,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import {
  Archive,
  ChevronDown,
  ChevronRight,
  Database,
  Plus,
  Scissors,
  ShieldCheck,
  SquarePen,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatCronHuman } from '../utils/dateUtils'
import type { BackupPlan, Repository } from '../types'
import RepoScheduleRow from './RepoScheduleRow'

export interface RepoScheduleData {
  checkCron: string | null
  checkTimezone?: string | null
  checkEnabled?: boolean
  restoreCron: string | null
  restoreTimezone?: string | null
  restoreEnabled?: boolean
}

interface PlanScheduleCardProps {
  plan: BackupPlan
  repositories: Repository[]
  repoSchedules: Record<number, RepoScheduleData>
  onEditPlan: (planId: number) => void
  onEditRepoCheck: (repoId: number) => void
  onEditRepoRestore: (repoId: number) => void
  canManageRepo: (repoId: number) => boolean
  canManagePlan: boolean
}

const PlanScheduleCard: React.FC<PlanScheduleCardProps> = ({
  plan,
  repositories,
  repoSchedules,
  onEditPlan,
  onEditRepoCheck,
  onEditRepoRestore,
  canManageRepo,
  canManagePlan,
}) => {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const [expanded, setExpanded] = useState(false)

  const backupColor = theme.palette.success.main

  const planRepos: Repository[] = (plan.repositories || [])
    .map((link) => link.repository ?? repositories.find((r) => r.id === link.repository_id) ?? null)
    .filter((r): r is Repository => r !== null)

  const backupCron = plan.cron_expression
  const hasBackupSchedule = plan.schedule_enabled && Boolean(backupCron)

  return (
    <Box
      sx={{
        borderRadius: 2,
        bgcolor: 'background.paper',
        border: '1px solid',
        borderColor: isDark ? alpha('#fff', 0.08) : alpha('#000', 0.08),
        overflow: 'hidden',
        opacity: plan.enabled ? 1 : 0.65,
        transition: 'all 200ms cubic-bezier(0.16,1,0.3,1)',
        '&:hover': {
          transform: 'translateY(-2px)',
          boxShadow: isDark
            ? `0 0 0 1px ${alpha(backupColor, 0.4)}, 0 8px 24px ${alpha('#000', 0.3)}, 0 2px 8px ${alpha(backupColor, 0.1)}`
            : `0 0 0 1px ${alpha(backupColor, 0.3)}, 0 8px 24px ${alpha('#000', 0.12)}, 0 2px 8px ${alpha(backupColor, 0.08)}`,
        },
      }}
    >
      {/* Header — the entire row toggles expand/collapse */}
      <Box
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        aria-label={`${expanded ? 'Collapse' : 'Expand'} ${plan.name}`}
        onClick={() => setExpanded((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            setExpanded((v) => !v)
          }
        }}
        sx={{
          px: { xs: 1.75, sm: 2 },
          py: 1.5,
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          cursor: 'pointer',
          userSelect: 'none',
          transition: 'background-color 150ms ease',
          '&:hover': {
            bgcolor: isDark ? alpha('#fff', 0.03) : alpha('#000', 0.025),
          },
          '&:focus-visible': {
            outline: `2px solid ${alpha(backupColor, 0.6)}`,
            outlineOffset: -2,
          },
        }}
      >
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 24,
            height: 24,
            color: 'text.secondary',
            flexShrink: 0,
          }}
          aria-hidden
        >
          {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        </Box>
        <Box
          sx={{
            width: 26,
            height: 26,
            borderRadius: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            bgcolor: alpha(backupColor, isDark ? 0.16 : 0.1),
            color: backupColor,
            flexShrink: 0,
          }}
          aria-hidden
        >
          <Database size={14} />
        </Box>
        <Typography variant="subtitle1" fontWeight={700} sx={{ flex: 1, minWidth: 0 }} noWrap>
          {plan.name}
        </Typography>
        {!plan.enabled && (
          <Chip
            size="small"
            label={t('schedule.byPlan.paused', { defaultValue: 'Paused' })}
            sx={{
              height: 20,
              fontSize: '0.65rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              bgcolor: alpha(theme.palette.warning.main, isDark ? 0.16 : 0.1),
              color: theme.palette.warning.main,
            }}
          />
        )}
        {canManagePlan && (
          <Tooltip
            title={t('schedule.byPlan.editPlan', { defaultValue: 'Edit plan' })}
            arrow
            placement="left"
          >
            <IconButton
              size="small"
              onClick={(e) => {
                e.stopPropagation()
                onEditPlan(plan.id)
              }}
              aria-label={t('schedule.byPlan.editPlan', { defaultValue: 'Edit plan' })}
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

      {/* Backup row */}
      <Box
        sx={{
          px: { xs: 1.75, sm: 2 },
          pb: 1.25,
          display: 'flex',
          alignItems: 'center',
          gap: 1,
        }}
      >
        <Box
          sx={{
            width: 9,
            height: 9,
            borderRadius: '50%',
            bgcolor: hasBackupSchedule ? backupColor : 'transparent',
            border: hasBackupSchedule ? 'none' : '1px dashed',
            borderColor: isDark ? alpha('#fff', 0.25) : alpha('#000', 0.25),
            flexShrink: 0,
            boxShadow: hasBackupSchedule ? `0 0 0 3px ${alpha(backupColor, 0.18)}` : 'none',
          }}
        />
        <Typography
          variant="caption"
          sx={{
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
            fontSize: '0.65rem',
            color: hasBackupSchedule ? backupColor : 'text.secondary',
            width: 56,
            flexShrink: 0,
          }}
        >
          {t('schedule.byPlan.backup', { defaultValue: 'Backup' })}
        </Typography>
        {hasBackupSchedule ? (
          <Typography variant="body2" sx={{ flex: 1, minWidth: 0 }} noWrap>
            {formatCronHuman(backupCron as string)}
            {plan.timezone && (
              <Typography
                component="span"
                variant="caption"
                color="text.secondary"
                sx={{ ml: 0.75 }}
              >
                {plan.timezone}
              </Typography>
            )}
          </Typography>
        ) : (
          <Box sx={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 0.75 }}>
            <Typography variant="body2" sx={{ fontStyle: 'italic' }} color="text.disabled" noWrap>
              {plan.schedule_enabled
                ? t('schedule.byPlan.notScheduled', { defaultValue: 'Not scheduled' })
                : t('schedule.byPlan.scheduleDisabled', {
                    defaultValue: 'Schedule disabled',
                  })}
            </Typography>
            {canManagePlan && (
              <Button
                size="small"
                variant="text"
                startIcon={<Plus size={12} />}
                onClick={() => onEditPlan(plan.id)}
                sx={{
                  fontSize: '0.7rem',
                  fontWeight: 600,
                  py: 0.15,
                  px: 0.75,
                  minWidth: 'auto',
                  color: backupColor,
                  '&:hover': {
                    bgcolor: alpha(backupColor, isDark ? 0.12 : 0.08),
                  },
                }}
              >
                {t('schedule.byPlan.setSchedule', { defaultValue: 'Set schedule' })}
              </Button>
            )}
          </Box>
        )}
      </Box>

      {/* Post-backup actions: prune / compact / check that run inline after
          each scheduled backup. Each chip carries its own semantic color so
          the three actions are distinguishable at a glance (not just by
          icon). */}
      {(plan.run_prune_after || plan.run_compact_after || plan.run_check_after) &&
        (() => {
          const chipSxFor = (chipColor: string) =>
            ({
              height: 22,
              fontSize: '0.65rem',
              fontWeight: 600,
              bgcolor: alpha(chipColor, isDark ? 0.16 : 0.1),
              color: chipColor,
              '& .MuiChip-label': { px: 0.75 },
              '& .MuiChip-icon': { color: 'inherit', ml: 0.5 },
            }) as const

          const pruneColor = theme.palette.secondary.main
          const compactColor = theme.palette.info.main
          const checkColor = theme.palette.warning.main

          return (
            <Box
              sx={{
                px: { xs: 1.75, sm: 2 },
                pb: 1.25,
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                flexWrap: 'wrap',
              }}
            >
              <Typography
                variant="caption"
                sx={{
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                  fontSize: '0.65rem',
                  color: 'text.secondary',
                  flexShrink: 0,
                }}
              >
                {t('schedule.byPlan.afterLabel', { defaultValue: 'After backup' })}
              </Typography>
              <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                {plan.run_prune_after && (
                  <Tooltip
                    title={t('schedule.byPlan.runPruneTip', {
                      defaultValue: 'Old archives are pruned after each backup',
                    })}
                    arrow
                  >
                    <Chip
                      size="small"
                      icon={<Scissors size={11} aria-hidden />}
                      label={t('schedule.byPlan.runPrune', { defaultValue: 'Prune' })}
                      sx={chipSxFor(pruneColor)}
                    />
                  </Tooltip>
                )}
                {plan.run_compact_after && (
                  <Tooltip
                    title={t('schedule.byPlan.runCompactTip', {
                      defaultValue: 'Repository is compacted after each backup',
                    })}
                    arrow
                  >
                    <Chip
                      size="small"
                      icon={<Archive size={11} aria-hidden />}
                      label={t('schedule.byPlan.runCompact', { defaultValue: 'Compact' })}
                      sx={chipSxFor(compactColor)}
                    />
                  </Tooltip>
                )}
                {plan.run_check_after && (
                  <Tooltip
                    title={t('schedule.byPlan.runCheckTip', {
                      defaultValue:
                        'Integrity check runs after each backup (in addition to any scheduled check below)',
                    })}
                    arrow
                  >
                    <Chip
                      size="small"
                      icon={<ShieldCheck size={11} aria-hidden />}
                      label={t('schedule.byPlan.runCheck', { defaultValue: 'Check' })}
                      sx={chipSxFor(checkColor)}
                    />
                  </Tooltip>
                )}
              </Box>
            </Box>
          )
        })()}

      {/* Repos */}
      <Collapse in={expanded} unmountOnExit>
        {planRepos.length === 0 ? (
          <Box
            sx={{
              px: { xs: 1.75, sm: 2 },
              py: 1.5,
              borderTop: '1px solid',
              borderColor: 'divider',
            }}
          >
            <Typography variant="body2" color="text.secondary">
              {t('schedule.byPlan.noRepos', {
                defaultValue: 'No repositories attached to this plan.',
              })}
            </Typography>
          </Box>
        ) : (
          <Box
            sx={{
              borderTop: '1px solid',
              borderColor: 'divider',
              bgcolor: isDark ? alpha('#fff', 0.02) : alpha('#000', 0.02),
            }}
          >
            <Stack divider={<Box />} sx={{ px: { xs: 1, sm: 1.5 } }}>
              {planRepos.map((repo) => {
                const sched = repoSchedules[repo.id]
                return (
                  <RepoScheduleRow
                    key={repo.id}
                    repositoryId={repo.id}
                    repositoryName={repo.name}
                    repositoryPath={repo.path}
                    checkCron={sched?.checkCron ?? null}
                    checkTimezone={sched?.checkTimezone}
                    checkEnabled={sched?.checkEnabled ?? true}
                    restoreCron={sched?.restoreCron ?? null}
                    restoreTimezone={sched?.restoreTimezone}
                    restoreEnabled={sched?.restoreEnabled ?? true}
                    onEditCheck={onEditRepoCheck}
                    onEditRestore={onEditRepoRestore}
                    canManage={canManageRepo(repo.id)}
                  />
                )
              })}
            </Stack>
          </Box>
        )}
      </Collapse>
    </Box>
  )
}

export default PlanScheduleCard

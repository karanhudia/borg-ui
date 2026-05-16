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
import { Archive, ChevronDown, ChevronRight, Pencil, Scissors, ShieldCheck } from 'lucide-react'
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
      }}
    >
      {/* Header */}
      <Box
        sx={{
          px: { xs: 1.75, sm: 2 },
          py: 1.5,
          display: 'flex',
          alignItems: 'center',
          gap: 1,
        }}
      >
        <IconButton
          size="small"
          onClick={() => setExpanded((v) => !v)}
          sx={{ ml: -0.5 }}
          aria-label={expanded ? 'Collapse' : 'Expand'}
        >
          {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        </IconButton>
        <Typography variant="subtitle1" fontWeight={700} sx={{ flex: 1, minWidth: 0 }} noWrap>
          {plan.name}
        </Typography>
        <Chip
          size="small"
          label={
            plan.enabled
              ? t('schedule.byPlan.enabled', { defaultValue: 'Enabled' })
              : t('schedule.byPlan.disabled', { defaultValue: 'Disabled' })
          }
          sx={{
            height: 20,
            fontSize: '0.65rem',
            fontWeight: 700,
            bgcolor: plan.enabled
              ? alpha(theme.palette.success.main, isDark ? 0.16 : 0.1)
              : alpha(theme.palette.text.secondary, isDark ? 0.16 : 0.1),
            color: plan.enabled ? theme.palette.success.main : theme.palette.text.secondary,
          }}
        />
        {canManagePlan && (
          <Button
            size="small"
            variant="text"
            startIcon={<Pencil size={13} />}
            onClick={() => onEditPlan(plan.id)}
            sx={{ fontSize: '0.7rem', fontWeight: 600, py: 0.25, px: 1, minWidth: 'auto' }}
          >
            {t('schedule.byPlan.editPlan', { defaultValue: 'Edit plan' })}
          </Button>
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
            width: 7,
            height: 7,
            borderRadius: '50%',
            bgcolor: hasBackupSchedule ? backupColor : 'transparent',
            border: hasBackupSchedule ? 'none' : '1px dashed',
            borderColor: isDark ? alpha('#fff', 0.25) : alpha('#000', 0.25),
            flexShrink: 0,
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
          <Typography
            variant="body2"
            sx={{ flex: 1, minWidth: 0, fontStyle: 'italic' }}
            color="text.disabled"
            noWrap
          >
            {plan.schedule_enabled
              ? t('schedule.byPlan.notScheduled', { defaultValue: 'Not scheduled' })
              : t('schedule.byPlan.scheduleDisabled', {
                  defaultValue: 'Schedule disabled',
                })}
          </Typography>
        )}
      </Box>

      {/* Post-backup actions: prune / compact / check that run inline after
          each scheduled backup. Hidden when none are enabled. */}
      {(plan.run_prune_after || plan.run_compact_after || plan.run_check_after) && (
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
              width: 56,
              flexShrink: 0,
            }}
          >
            {t('schedule.byPlan.afterLabel', { defaultValue: 'Then' })}
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
                  icon={<Scissors size={11} />}
                  label={t('schedule.byPlan.runPrune', { defaultValue: 'Prune' })}
                  sx={{
                    height: 22,
                    fontSize: '0.65rem',
                    fontWeight: 600,
                    bgcolor: alpha(theme.palette.primary.main, isDark ? 0.14 : 0.08),
                    color: theme.palette.primary.main,
                    '& .MuiChip-icon': { color: 'inherit', ml: 0.5 },
                  }}
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
                  icon={<Archive size={11} />}
                  label={t('schedule.byPlan.runCompact', { defaultValue: 'Compact' })}
                  sx={{
                    height: 22,
                    fontSize: '0.65rem',
                    fontWeight: 600,
                    bgcolor: alpha(theme.palette.primary.main, isDark ? 0.14 : 0.08),
                    color: theme.palette.primary.main,
                    '& .MuiChip-icon': { color: 'inherit', ml: 0.5 },
                  }}
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
                  icon={<ShieldCheck size={11} />}
                  label={t('schedule.byPlan.runCheck', { defaultValue: 'Check' })}
                  sx={{
                    height: 22,
                    fontSize: '0.65rem',
                    fontWeight: 600,
                    bgcolor: alpha(theme.palette.warning.main, isDark ? 0.14 : 0.08),
                    color: theme.palette.warning.main,
                    '& .MuiChip-icon': { color: 'inherit', ml: 0.5 },
                  }}
                />
              </Tooltip>
            )}
          </Box>
        </Box>
      )}

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

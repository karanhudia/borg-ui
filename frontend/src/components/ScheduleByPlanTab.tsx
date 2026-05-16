import React, { useMemo } from 'react'
import { Alert, Box, Skeleton, Stack, Typography, alpha, useTheme } from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Calendar } from 'lucide-react'
import { backupPlansAPI, repositoriesAPI } from '../services/api'
import type { BackupPlan, Repository } from '../types'
import PlanScheduleCard, { type RepoScheduleData } from './PlanScheduleCard'
import UnassignedReposSection from './UnassignedReposSection'

interface ScheduleByPlanTabProps {
  plans: BackupPlan[]
  repositories: Repository[]
  isLoading: boolean
  onEditPlan: (planId: number) => void
  onEditRepoCheck: (repoId: number) => void
  onEditRepoRestore: (repoId: number) => void
  canManageRepo: (repoId: number) => boolean
  canManagePlan: (plan: BackupPlan) => boolean
  /**
   * Optional render slot for the deprecated legacy schedules table, rendered
   * at the bottom of the tab. Parent should pass `null` when empty so the
   * section disappears entirely.
   */
  legacySection?: React.ReactNode
}

type RepoScheduleMap = Record<number, RepoScheduleData>

const ScheduleByPlanTab: React.FC<ScheduleByPlanTabProps> = ({
  plans,
  repositories,
  isLoading,
  onEditPlan,
  onEditRepoCheck,
  onEditRepoRestore,
  canManageRepo,
  canManagePlan,
  legacySection,
}) => {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  // The list endpoint returns summary plans only — the repositories[] array and
  // post-backup flags (run_prune_after etc.) require detail=true. Fetch each
  // plan in parallel so per-repo rows and post-backup chips can render.
  const planIds = useMemo(() => plans.map((p) => p.id).sort((a, b) => a - b), [plans])
  const { data: detailedPlans, isLoading: loadingDetailed } = useQuery({
    queryKey: ['backup-plans-detailed', planIds],
    queryFn: async () => {
      const results = await Promise.all(
        plans.map((p) =>
          backupPlansAPI.get(p.id).then(
            (r) => r.data as BackupPlan,
            () => null
          )
        )
      )
      const map = new Map<number, BackupPlan>()
      for (const detail of results) {
        if (detail) map.set(detail.id, detail)
      }
      return map
    },
    enabled: plans.length > 0,
    staleTime: 30000,
  })

  const resolvedPlans = useMemo(
    () => plans.map((p) => detailedPlans?.get(p.id) ?? p),
    [plans, detailedPlans]
  )

  // Fetch per-repo check + restore-check schedules in parallel. The backend
  // doesn't include these on the repo list endpoint, but the per-repo
  // endpoints return cron + timezone even when no schedule is configured.
  const repoIds = useMemo(() => repositories.map((r) => r.id).sort((a, b) => a - b), [repositories])
  const { data: repoSchedules, isLoading: loadingSchedules } = useQuery({
    queryKey: ['repo-schedules', repoIds],
    queryFn: async () => {
      const map: RepoScheduleMap = {}
      await Promise.all(
        repositories.map(async (repo) => {
          const entry: RepoScheduleData = {
            checkCron: null,
            restoreCron: null,
          }
          try {
            const res = await repositoriesAPI.getCheckSchedule(repo.id)
            entry.checkCron = res.data?.check_cron_expression ?? null
            entry.checkTimezone = res.data?.check_timezone ?? res.data?.timezone ?? null
            entry.checkEnabled =
              typeof res.data?.check_schedule_enabled === 'boolean'
                ? res.data.check_schedule_enabled
                : true
          } catch {
            // leave defaults
          }
          try {
            const res = await repositoriesAPI.getRestoreCheckSchedule(repo.id)
            entry.restoreCron = res.data?.restore_check_cron_expression ?? null
            entry.restoreTimezone = res.data?.restore_check_timezone ?? res.data?.timezone ?? null
            entry.restoreEnabled =
              typeof res.data?.restore_check_schedule_enabled === 'boolean'
                ? res.data.restore_check_schedule_enabled
                : true
          } catch {
            // leave defaults
          }
          map[repo.id] = entry
        })
      )
      return map
    },
    enabled: repositories.length > 0,
    refetchInterval: 30000,
  })

  const schedules = repoSchedules ?? {}

  // Compute which repositories are not attached to any plan
  const planRepoIds = useMemo(() => {
    const ids = new Set<number>()
    for (const plan of resolvedPlans) {
      for (const link of plan.repositories || []) {
        if (link.repository_id) ids.add(link.repository_id)
      }
    }
    return ids
  }, [resolvedPlans])

  const unassignedRepos = useMemo(
    () => repositories.filter((r) => !planRepoIds.has(r.id)),
    [repositories, planRepoIds]
  )

  if (isLoading || loadingSchedules || loadingDetailed) {
    // Mirror the collapsed PlanScheduleCard shape: same border/radius, header
    // row (chevron + title + chip + edit button) + backup row (dot + label +
    // cron). Generic height={180} skeletons read as the expanded card and feel
    // jarring once the real, collapsed cards swap in.
    return (
      <Stack spacing={2}>
        {[0, 1].map((i) => (
          <Box
            key={i}
            sx={{
              borderRadius: 2,
              bgcolor: 'background.paper',
              border: '1px solid',
              borderColor: isDark ? alpha('#fff', 0.08) : alpha('#000', 0.08),
              overflow: 'hidden',
              opacity: Math.max(0.5, 1 - i * 0.25),
            }}
          >
            <Box
              sx={{
                px: { xs: 1.75, sm: 2 },
                py: 1.5,
                display: 'flex',
                alignItems: 'center',
                gap: 1,
              }}
            >
              <Skeleton variant="circular" width={20} height={20} sx={{ ml: -0.5 }} />
              <Skeleton variant="text" width={160} sx={{ fontSize: '1rem' }} />
              <Box sx={{ flex: 1 }} />
              <Skeleton variant="rounded" width={64} height={20} sx={{ borderRadius: 10 }} />
              <Skeleton variant="rounded" width={72} height={22} />
            </Box>
            <Box
              sx={{
                px: { xs: 1.75, sm: 2 },
                pb: 1.25,
                display: 'flex',
                alignItems: 'center',
                gap: 1,
              }}
            >
              <Skeleton variant="circular" width={7} height={7} />
              <Skeleton variant="text" width={48} sx={{ fontSize: '0.65rem' }} />
              <Skeleton variant="text" width="42%" sx={{ fontSize: '0.875rem' }} />
            </Box>
          </Box>
        ))}
      </Stack>
    )
  }

  if (plans.length === 0 && repositories.length === 0) {
    return (
      <Alert severity="info">
        {t('schedule.byPlan.empty', {
          defaultValue:
            'No backup plans or repositories yet. Create a plan to see its full schedule here.',
        })}
      </Alert>
    )
  }

  return (
    <Stack spacing={2}>
      {plans.length === 0 ? (
        <Box
          sx={{
            py: 5,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            color: 'text.secondary',
            textAlign: 'center',
            px: 2,
          }}
        >
          <Calendar size={36} style={{ opacity: 0.25, marginBottom: 10 }} />
          <Typography variant="body1" gutterBottom>
            {t('schedule.byPlan.noPlansTitle', { defaultValue: 'No backup plans yet' })}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('schedule.byPlan.noPlansDesc', {
              defaultValue:
                'Repository check and restore-check schedules below run independently of any plan.',
            })}
          </Typography>
        </Box>
      ) : (
        resolvedPlans.map((plan) => (
          <PlanScheduleCard
            key={plan.id}
            plan={plan}
            repositories={repositories}
            repoSchedules={schedules}
            onEditPlan={onEditPlan}
            onEditRepoCheck={onEditRepoCheck}
            onEditRepoRestore={onEditRepoRestore}
            canManageRepo={canManageRepo}
            canManagePlan={canManagePlan(plan)}
          />
        ))
      )}

      <UnassignedReposSection
        repositories={unassignedRepos}
        repoSchedules={schedules}
        onEditRepoCheck={onEditRepoCheck}
        onEditRepoRestore={onEditRepoRestore}
        canManageRepo={canManageRepo}
      />

      {legacySection}
    </Stack>
  )
}

export default ScheduleByPlanTab

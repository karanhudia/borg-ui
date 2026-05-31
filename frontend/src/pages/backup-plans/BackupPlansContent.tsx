import type { Dispatch, SetStateAction } from 'react'
import { alpha, Box, Button, Chip, Divider, Stack, Typography, useTheme } from '@mui/material'
import FilterListIcon from '@mui/icons-material/FilterList'
import { Database, ListChecks, Plus, RefreshCw } from 'lucide-react'
import type { TFunction } from 'i18next'

import EmptyStateCard from '../../components/EmptyStateCard'
import ActiveBackupPlanRunCard from '../../components/ActiveBackupPlanRunCard'
import PageHeader from '../../components/PageHeader'
import ListToolbar from '../../components/ListToolbar'
import { type BackupPlanRunLogJob } from '../../components/BackupPlanRunsPanel'
import type { BackupPlan, BackupPlanRun } from '../../types'
import { BackupPlanCardSkeleton } from './BackupPlanCardSkeleton'
import { BackupPlanIdleCard } from './PlanRunComponents'
import { isActiveRun } from './runStatus'
import { useAnalytics } from '../../hooks/useAnalytics'

const BACKUP_PLANS_ANALYTICS_SECTION = 'backup_plans'

interface ProcessedBackupPlans {
  groups: Array<{ name: string | null; plans: BackupPlan[] }>
}

interface BackupPlansContentProps {
  loadingPlans: boolean
  backupPlans: BackupPlan[]
  processedPlans: ProcessedBackupPlans
  latestRunByPlan: Map<number, BackupPlanRun>
  backupPlanRuns: BackupPlanRun[]
  searchQuery: string
  setSearchQuery: Dispatch<SetStateAction<string>>
  sortBy: string
  setSortBy: Dispatch<SetStateAction<string>>
  groupBy: string
  setGroupBy: Dispatch<SetStateAction<string>>
  repositoryFilter: { id: number; name: string } | null
  onClearRepositoryFilter: () => void
  startingPlanId: number | null
  highlightedPlanId: number | null
  canUseMultiRepository: boolean
  cancellingRunId: number | null
  runPending: boolean
  togglePending: boolean
  toggleVariables: number | undefined
  openCreateWizard: () => void
  onRunPlan: (planId: number) => void
  onCancelRun: (runId: number) => void
  onViewLogs: (job: BackupPlanRunLogJob) => void
  onTogglePlan: (planId: number) => void
  onEditPlan: (plan: BackupPlan) => void
  onDeletePlan: (planId: number) => void
  onViewHistory: (planId: number) => void
  onViewRepositories: (planId: number) => void
  formatStatusLabel: (status?: string) => string
  t: TFunction
}

export function BackupPlansContent({
  loadingPlans,
  backupPlans,
  processedPlans,
  latestRunByPlan,
  backupPlanRuns,
  searchQuery,
  setSearchQuery,
  sortBy,
  setSortBy,
  groupBy,
  setGroupBy,
  repositoryFilter,
  onClearRepositoryFilter,
  startingPlanId,
  highlightedPlanId,
  canUseMultiRepository,
  cancellingRunId,
  runPending,
  togglePending,
  toggleVariables,
  openCreateWizard,
  onRunPlan,
  onCancelRun,
  onViewLogs,
  onTogglePlan,
  onEditPlan,
  onDeletePlan,
  onViewHistory,
  onViewRepositories,
  formatStatusLabel,
  t,
}: BackupPlansContentProps) {
  const theme = useTheme()
  const { track, EventCategory, EventAction } = useAnalytics()
  const isDark = theme.palette.mode === 'dark'
  // Plans currently running are pulled into a top "Currently running" section
  // so the user can find live state in one glance. The idle plan card down in
  // the list still gets a small "Running" pulse-dot chip on its header so the
  // parent-child link is not lost.
  const runningEntries = backupPlans
    .map((plan) => ({ plan, run: latestRunByPlan.get(plan.id) }))
    .filter(
      (entry): entry is { plan: BackupPlan; run: BackupPlanRun } =>
        Boolean(entry.run) && isActiveRun(entry.run!.status)
    )

  const resultCount = processedPlans.groups.reduce((sum, group) => sum + group.plans.length, 0)
  const trackBackupPlan = (action: string, data: Record<string, unknown>) => {
    track(EventCategory.BACKUP, action, {
      entity: 'backup_plan',
      section: BACKUP_PLANS_ANALYTICS_SECTION,
      ...data,
    })
  }
  const trackBackupPlanSearch = (value: string) => {
    setSearchQuery(value)
    const trimmed = value.trim()
    if (!trimmed) return

    trackBackupPlan(EventAction.SEARCH, {
      operation: 'search_plans',
      query_length: trimmed.length,
      sort_by: sortBy,
      group_by: groupBy,
      result_count: resultCount,
    })
  }
  const trackBackupPlanSort = (value: string) => {
    setSortBy(value)
    trackBackupPlan(EventAction.FILTER, {
      operation: 'change_sort',
      sort_by: value,
      group_by: groupBy,
      query_length: searchQuery.trim().length,
      result_count: resultCount,
    })
  }
  const trackBackupPlanGroup = (value: string) => {
    setGroupBy(value)
    trackBackupPlan(EventAction.FILTER, {
      operation: 'change_group',
      sort_by: sortBy,
      group_by: value,
      query_length: searchQuery.trim().length,
      result_count: resultCount,
    })
  }

  return (
    <>
      <PageHeader
        title={t('backupPlans.title')}
        subtitle={t('backupPlans.subtitle')}
        actions={
          backupPlans.length > 0 ? (
            <Button
              variant="contained"
              startIcon={<Plus size={18} />}
              onClick={() => {
                trackBackupPlan(EventAction.VIEW, { operation: 'open_create_plan_wizard' })
                openCreateWizard()
              }}
              sx={{ width: { xs: '100%', md: 'auto' } }}
            >
              {t('backupPlans.actions.create')}
            </Button>
          ) : null
        }
      />

      {runningEntries.length > 0 && (
        <Box component="section" aria-labelledby="backup-plans-running-heading" sx={{ mb: 3 }}>
          <Stack
            direction="row"
            spacing={1.5}
            alignItems="center"
            sx={{ mb: 1, color: 'text.secondary' }}
          >
            <Box sx={{ display: 'flex', color: 'success.main' }}>
              <RefreshCw size={20} className="animate-spin" />
            </Box>
            <Typography id="backup-plans-running-heading" variant="h6" fontWeight={600}>
              {t('backupPlans.runsPanel.activeTitle')}
            </Typography>
            <Chip
              size="small"
              color="primary"
              label={t('backupPlans.runsPanel.activeCount', { count: runningEntries.length })}
            />
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {t('backupPlans.runsPanel.activeSubtitle')}
          </Typography>
          <Stack spacing={2}>
            {runningEntries.map(({ plan, run }) => (
              <ActiveBackupPlanRunCard
                key={run.id}
                run={run}
                plan={plan}
                cancelling={cancellingRunId === run.id}
                onCancel={(runId) => {
                  track(EventCategory.BACKUP, EventAction.STOP, {
                    entity: 'backup_plan_run',
                    section: BACKUP_PLANS_ANALYTICS_SECTION,
                    operation: 'cancel_run',
                    status: run.status,
                    trigger: run.trigger,
                  })
                  onCancelRun(runId)
                }}
                onViewLogs={(job) => {
                  track(EventCategory.BACKUP, EventAction.VIEW, {
                    entity: 'backup_plan_run',
                    section: BACKUP_PLANS_ANALYTICS_SECTION,
                    operation: 'view_run_logs',
                    status: job.status,
                    job_type: 'type' in job ? job.type : 'backup',
                  })
                  onViewLogs(job)
                }}
              />
            ))}
          </Stack>
        </Box>
      )}

      {(loadingPlans || backupPlans.length > 0) && (
        <ListToolbar
          searchValue={searchQuery}
          onSearchChange={trackBackupPlanSearch}
          searchPlaceholder={t('backupPlans.search', {
            defaultValue: 'Search backup plans...',
          })}
          sortValue={sortBy}
          onSortChange={trackBackupPlanSort}
          sortOptions={[
            {
              value: 'name-asc',
              label: t('backupPlans.sort.nameAZ', { defaultValue: 'Name A → Z' }),
            },
            {
              value: 'name-desc',
              label: t('backupPlans.sort.nameZA', { defaultValue: 'Name Z → A' }),
            },
            {
              value: 'last-run-recent',
              label: t('backupPlans.sort.lastRunRecent', {
                defaultValue: 'Last run (most recent)',
              }),
            },
            {
              value: 'last-run-oldest',
              label: t('backupPlans.sort.lastRunOldest', { defaultValue: 'Last run (oldest)' }),
            },
            {
              value: 'next-run-soonest',
              label: t('backupPlans.sort.nextRunSoonest', { defaultValue: 'Next run (soonest)' }),
            },
            {
              value: 'created-newest',
              label: t('backupPlans.sort.createdNewest', { defaultValue: 'Created (newest)' }),
            },
            {
              value: 'created-oldest',
              label: t('backupPlans.sort.createdOldest', { defaultValue: 'Created (oldest)' }),
            },
          ]}
          groupValue={groupBy}
          onGroupChange={trackBackupPlanGroup}
          groupOptions={[
            { value: 'none', label: t('backupPlans.group.none', { defaultValue: 'No grouping' }) },
            {
              value: 'status',
              label: t('backupPlans.group.status', { defaultValue: 'By status' }),
            },
            {
              value: 'schedule',
              label: t('backupPlans.group.schedule', { defaultValue: 'By schedule' }),
            },
            {
              value: 'source',
              label: t('backupPlans.group.source', { defaultValue: 'By source' }),
            },
          ]}
        />
      )}

      {repositoryFilter && (
        <Box
          role="status"
          sx={{
            display: 'flex',
            alignItems: { xs: 'stretch', sm: 'center' },
            justifyContent: 'space-between',
            flexDirection: { xs: 'column', sm: 'row' },
            gap: 1,
            mb: 2,
            px: 1.5,
            py: 1.25,
            borderRadius: 1.5,
            border: '1px solid',
            borderColor: alpha(theme.palette.primary.main, isDark ? 0.32 : 0.24),
            bgcolor: alpha(theme.palette.primary.main, isDark ? 0.1 : 0.06),
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
            <Box sx={{ display: 'flex', color: 'primary.main', flexShrink: 0 }}>
              <Database size={16} />
            </Box>
            <Typography
              variant="body2"
              sx={{ color: 'text.secondary', fontWeight: 600, minWidth: 0 }}
            >
              {t('backupPlans.filters.linkedRepository', { name: repositoryFilter.name })}
            </Typography>
          </Box>
          <Button
            variant="outlined"
            size="small"
            onClick={() => {
              trackBackupPlan(EventAction.FILTER, {
                operation: 'clear_repository_filter',
                repository_filter_present: true,
                result_count: resultCount,
              })
              onClearRepositoryFilter()
            }}
            sx={{ flexShrink: 0, alignSelf: { xs: 'flex-start', sm: 'center' } }}
          >
            {t('backupPlans.filters.clearRepository')}
          </Button>
        </Box>
      )}

      {loadingPlans ? (
        <Stack spacing={2} aria-label={t('backupPlans.loading')}>
          {[0, 1, 2].map((index) => (
            <BackupPlanCardSkeleton key={index} index={index} />
          ))}
        </Stack>
      ) : backupPlans.length === 0 && !repositoryFilter ? (
        <EmptyStateCard
          icon={<ListChecks size={36} />}
          title={t('backupPlans.empty.title')}
          description={t('backupPlans.empty.description')}
          actions={
            <Button
              variant="contained"
              startIcon={<Plus size={16} />}
              onClick={() => {
                trackBackupPlan(EventAction.VIEW, { operation: 'open_create_plan_wizard' })
                openCreateWizard()
              }}
            >
              {t('backupPlans.actions.create')}
            </Button>
          }
        />
      ) : backupPlans.length === 0 || processedPlans.groups.every((g) => g.plans.length === 0) ? (
        <EmptyStateCard
          icon={<ListChecks size={36} />}
          title={t('backupPlans.noMatch.title', { defaultValue: 'No matching backup plans' })}
          description={
            searchQuery
              ? t('backupPlans.noMatch.message', {
                  search: searchQuery,
                  defaultValue: `No backup plans match "${searchQuery}".`,
                })
              : repositoryFilter
                ? t('backupPlans.noMatch.repositoryFilter', {
                    name: repositoryFilter.name,
                    defaultValue: `No backup plans are linked to ${repositoryFilter.name}.`,
                  })
                : t('backupPlans.noMatch.fallback', {
                    defaultValue: 'No backup plans match the current filters.',
                  })
          }
          actions={
            searchQuery ? (
              <Button
                variant="outlined"
                onClick={() => {
                  trackBackupPlan(EventAction.FILTER, {
                    operation: 'clear_search',
                    query_length: searchQuery.trim().length,
                    result_count: backupPlans.length,
                  })
                  setSearchQuery('')
                }}
              >
                {t('backupPlans.noMatch.clearSearch', { defaultValue: 'Clear search' })}
              </Button>
            ) : repositoryFilter ? (
              <Button
                variant="outlined"
                onClick={() => {
                  trackBackupPlan(EventAction.FILTER, {
                    operation: 'clear_repository_filter',
                    repository_filter_present: true,
                    result_count: resultCount,
                  })
                  onClearRepositoryFilter()
                }}
              >
                {t('backupPlans.filters.clearRepository')}
              </Button>
            ) : undefined
          }
        />
      ) : (
        <Stack spacing={3}>
          {processedPlans.groups.map((group, groupIndex) => (
            <Box key={group.name ?? `group-${groupIndex}`}>
              {group.name && (
                <Box sx={{ mb: 2 }}>
                  <Typography
                    variant="h6"
                    sx={{
                      fontSize: '1rem',
                      fontWeight: 600,
                      color: 'primary.main',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 1,
                    }}
                  >
                    <FilterListIcon fontSize="small" />
                    {group.name}
                    <Typography
                      component="span"
                      sx={{ ml: 0.5, fontSize: '0.875rem', color: 'text.secondary' }}
                    >
                      ({group.plans.length})
                    </Typography>
                  </Typography>
                  <Divider sx={{ mt: 1 }} />
                </Box>
              )}

              <Stack spacing={2}>
                {group.plans.map((plan) => {
                  const latestRun = latestRunByPlan.get(plan.id)
                  const planIsRunning = isActiveRun(latestRun?.status)
                  const planIsStarting = startingPlanId === plan.id && runPending
                  const isHighlighted = highlightedPlanId === plan.id
                  const planUsesProFeatures =
                    plan.repository_count > 1 || plan.repository_run_mode === 'parallel'
                  const planBlockedByLicense = planUsesProFeatures && !canUseMultiRepository
                  const runDisabled =
                    planIsStarting || planIsRunning || !plan.enabled || planBlockedByLicense
                  const runTooltip = planBlockedByLicense ? t('backupPlans.runTooltipPro') : ''
                  const sourceTypeLabel =
                    plan.source_type === 'remote'
                      ? t('backupPlans.status.remoteSource')
                      : plan.source_type === 'agent'
                        ? t('backupPlans.sourceChooser.managedAgent')
                        : plan.source_type === 'mixed'
                          ? t('backupPlans.sourceChooser.mixedSources')
                          : t('backupPlans.status.localSource')

                  return (
                    <BackupPlanIdleCard
                      key={plan.id}
                      plan={plan}
                      latestRun={latestRun}
                      isHighlighted={isHighlighted}
                      planUsesProFeatures={planUsesProFeatures}
                      planBlockedByLicense={planBlockedByLicense}
                      planIsStarting={planIsStarting}
                      runDisabled={runDisabled}
                      runTooltip={runTooltip}
                      sourceTypeLabel={sourceTypeLabel}
                      hasRunHistory={backupPlanRuns.some(
                        (r) => r.backup_plan_id === plan.id && !isActiveRun(r.status)
                      )}
                      onRun={() => {
                        trackBackupPlan(EventAction.START, {
                          operation: 'run_plan',
                          schedule_enabled: plan.schedule_enabled,
                          source_type: plan.source_type,
                          repository_count: plan.repository_count,
                        })
                        onRunPlan(plan.id)
                      }}
                      onToggle={() => {
                        trackBackupPlan(EventAction.EDIT, {
                          operation: 'toggle_plan',
                          enabled_before: plan.enabled,
                        })
                        onTogglePlan(plan.id)
                      }}
                      onEdit={() => {
                        trackBackupPlan(EventAction.VIEW, {
                          operation: 'open_edit_plan_wizard',
                          schedule_enabled: plan.schedule_enabled,
                          source_type: plan.source_type,
                          repository_count: plan.repository_count,
                        })
                        onEditPlan(plan)
                      }}
                      onDelete={() => {
                        if (
                          window.confirm(
                            t('backupPlans.actions.deleteConfirm', { name: plan.name })
                          )
                        ) {
                          trackBackupPlan(EventAction.DELETE, {
                            operation: 'delete_plan',
                            schedule_enabled: plan.schedule_enabled,
                            source_type: plan.source_type,
                            repository_count: plan.repository_count,
                          })
                          onDeletePlan(plan.id)
                        }
                      }}
                      onViewHistory={() => {
                        trackBackupPlan(EventAction.VIEW, {
                          operation: 'view_plan_history',
                          has_run_history: backupPlanRuns.some(
                            (r) => r.backup_plan_id === plan.id && !isActiveRun(r.status)
                          ),
                        })
                        onViewHistory(plan.id)
                      }}
                      onViewRepositories={() => {
                        trackBackupPlan(EventAction.VIEW, {
                          operation: 'view_linked_repositories',
                          repository_count: plan.repository_count,
                        })
                        onViewRepositories(plan.id)
                      }}
                      planIsToggling={togglePending && toggleVariables === plan.id}
                      t={t}
                      formatStatusLabel={formatStatusLabel}
                    />
                  )
                })}
              </Stack>
            </Box>
          ))}
        </Stack>
      )}
    </>
  )
}

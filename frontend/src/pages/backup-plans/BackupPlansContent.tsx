import type { Dispatch, SetStateAction } from 'react'
import {
  alpha,
  Box,
  Button,
  Divider,
  InputBase,
  MenuItem,
  Select,
  Stack,
  Typography,
} from '@mui/material'
import SearchIcon from '@mui/icons-material/Search'
import FilterListIcon from '@mui/icons-material/FilterList'
import { ListChecks, Plus } from 'lucide-react'
import type { TFunction } from 'i18next'

import EmptyStateCard from '../../components/EmptyStateCard'
import ActiveBackupPlanRunCard from '../../components/ActiveBackupPlanRunCard'
import { type BackupPlanRunLogJob } from '../../components/BackupPlanRunsPanel'
import type { BackupPlan, BackupPlanRun } from '../../types'
import { BackupPlanCardSkeleton } from './BackupPlanCardSkeleton'
import { BackupPlanIdleCard } from './PlanRunComponents'
import { isActiveRun } from './runStatus'

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
  isDark: boolean
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
  isDark,
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
  return (
    <>
      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Box
          sx={{
            display: 'flex',
            flexDirection: { xs: 'column', md: 'row' },
            justifyContent: 'space-between',
            alignItems: { xs: 'stretch', md: 'flex-start' },
            gap: 2,
            mb: 2,
          }}
        >
          <Box sx={{ flex: 1, mr: { md: 2 } }}>
            <Typography variant="h4" fontWeight={600} gutterBottom>
              {t('backupPlans.title')}
            </Typography>
            <Typography variant="body2" color="text.secondary" paragraph>
              {t('backupPlans.subtitle')}
            </Typography>
          </Box>
          {backupPlans.length > 0 && (
            <Button
              variant="contained"
              startIcon={<Plus size={18} />}
              onClick={openCreateWizard}
              sx={{ width: { xs: '100%', md: 'auto' } }}
            >
              {t('backupPlans.actions.create')}
            </Button>
          )}
        </Box>
      </Box>

      {/* Search / Sort / Group bar */}
      {(loadingPlans || backupPlans.length > 0) && (
        <Box
          sx={{
            mb: 3,
            display: 'flex',
            flexWrap: 'wrap',
            gap: 1.5,
            alignItems: 'center',
          }}
        >
          <Box
            sx={{
              flex: '1 1 100%',
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              px: 1.5,
              height: 40,
              borderRadius: 1.5,
              border: '1px solid',
              borderColor: isDark ? alpha('#fff', 0.1) : alpha('#000', 0.12),
              bgcolor: isDark ? alpha('#fff', 0.04) : alpha('#000', 0.02),
              '&:focus-within': {
                borderColor: isDark ? alpha('#fff', 0.2) : alpha('#000', 0.25),
              },
            }}
          >
            <SearchIcon sx={{ fontSize: 16, color: 'text.disabled', flexShrink: 0 }} />
            <InputBase
              placeholder={t('backupPlans.search', {
                defaultValue: 'Search backup plans...',
              })}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              sx={{ flex: 1, fontSize: '0.875rem', minWidth: 0 }}
            />
          </Box>

          <Select
            size="small"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            sx={{
              flex: 1,
              minWidth: 180,
              fontSize: '0.8rem',
              fontWeight: 600,
              borderRadius: 1.5,
              '& .MuiOutlinedInput-notchedOutline': {
                borderColor: isDark ? alpha('#fff', 0.1) : alpha('#000', 0.12),
              },
              '&:hover .MuiOutlinedInput-notchedOutline': {
                borderColor: isDark ? alpha('#fff', 0.2) : alpha('#000', 0.25),
              },
            }}
          >
            <MenuItem value="name-asc">
              {t('backupPlans.sort.nameAZ', { defaultValue: 'Name A → Z' })}
            </MenuItem>
            <MenuItem value="name-desc">
              {t('backupPlans.sort.nameZA', { defaultValue: 'Name Z → A' })}
            </MenuItem>
            <MenuItem value="last-run-recent">
              {t('backupPlans.sort.lastRunRecent', {
                defaultValue: 'Last run (most recent)',
              })}
            </MenuItem>
            <MenuItem value="last-run-oldest">
              {t('backupPlans.sort.lastRunOldest', { defaultValue: 'Last run (oldest)' })}
            </MenuItem>
            <MenuItem value="next-run-soonest">
              {t('backupPlans.sort.nextRunSoonest', { defaultValue: 'Next run (soonest)' })}
            </MenuItem>
            <MenuItem value="created-newest">
              {t('backupPlans.sort.createdNewest', { defaultValue: 'Created (newest)' })}
            </MenuItem>
            <MenuItem value="created-oldest">
              {t('backupPlans.sort.createdOldest', { defaultValue: 'Created (oldest)' })}
            </MenuItem>
          </Select>

          <Select
            size="small"
            value={groupBy}
            onChange={(e) => setGroupBy(e.target.value)}
            sx={{
              flex: 1,
              minWidth: 140,
              fontSize: '0.8rem',
              fontWeight: 600,
              borderRadius: 1.5,
              '& .MuiOutlinedInput-notchedOutline': {
                borderColor: isDark ? alpha('#fff', 0.1) : alpha('#000', 0.12),
              },
              '&:hover .MuiOutlinedInput-notchedOutline': {
                borderColor: isDark ? alpha('#fff', 0.2) : alpha('#000', 0.25),
              },
            }}
          >
            <MenuItem value="none">
              {t('backupPlans.group.none', { defaultValue: 'No grouping' })}
            </MenuItem>
            <MenuItem value="status">
              {t('backupPlans.group.status', { defaultValue: 'By status' })}
            </MenuItem>
            <MenuItem value="schedule">
              {t('backupPlans.group.schedule', { defaultValue: 'By schedule' })}
            </MenuItem>
            <MenuItem value="source">
              {t('backupPlans.group.source', { defaultValue: 'By source' })}
            </MenuItem>
          </Select>
        </Box>
      )}

      {loadingPlans ? (
        <Stack spacing={2} aria-label={t('backupPlans.loading')}>
          {[0, 1, 2].map((index) => (
            <BackupPlanCardSkeleton key={index} index={index} />
          ))}
        </Stack>
      ) : backupPlans.length === 0 ? (
        <EmptyStateCard
          icon={<ListChecks size={36} />}
          title={t('backupPlans.empty.title')}
          description={t('backupPlans.empty.description')}
          actions={
            <Button variant="contained" startIcon={<Plus size={16} />} onClick={openCreateWizard}>
              {t('backupPlans.actions.create')}
            </Button>
          }
        />
      ) : processedPlans.groups.every((g) => g.plans.length === 0) ? (
        <EmptyStateCard
          icon={<ListChecks size={36} />}
          title={t('backupPlans.noMatch.title', { defaultValue: 'No matching backup plans' })}
          description={
            searchQuery
              ? t('backupPlans.noMatch.message', {
                  search: searchQuery,
                  defaultValue: `No backup plans match "${searchQuery}".`,
                })
              : t('backupPlans.noMatch.fallback', {
                  defaultValue: 'No backup plans match the current filters.',
                })
          }
          actions={
            searchQuery ? (
              <Button variant="outlined" onClick={() => setSearchQuery('')}>
                {t('backupPlans.noMatch.clearSearch', { defaultValue: 'Clear search' })}
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
                      : t('backupPlans.status.localSource')

                  return (
                    <Stack key={plan.id} spacing={1.25}>
                      <BackupPlanIdleCard
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
                        onRun={() => onRunPlan(plan.id)}
                        onToggle={() => onTogglePlan(plan.id)}
                        onEdit={() => onEditPlan(plan)}
                        onDelete={() => {
                          if (
                            window.confirm(
                              t('backupPlans.actions.deleteConfirm', { name: plan.name })
                            )
                          ) {
                            onDeletePlan(plan.id)
                          }
                        }}
                        onViewHistory={() => onViewHistory(plan.id)}
                        onViewRepositories={() => onViewRepositories(plan.id)}
                        planIsToggling={togglePending && toggleVariables === plan.id}
                        t={t}
                        formatStatusLabel={formatStatusLabel}
                      />
                      {planIsRunning && latestRun && (
                        <ActiveBackupPlanRunCard
                          run={latestRun}
                          plan={plan}
                          cancelling={cancellingRunId === latestRun.id}
                          onCancel={(runId) => onCancelRun(runId)}
                          onViewLogs={(job) => onViewLogs(job)}
                        />
                      )}
                    </Stack>
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

import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { Box, IconButton, Skeleton, Typography } from '@mui/material'
import { History, RefreshCw } from 'lucide-react'
import { activityAPI, repositoriesAPI } from '../services/api'
import { useAnalytics } from '../hooks/useAnalytics'
import { useAuth } from '../hooks/useAuth'
import { useLockBreakPermissions } from '../hooks/useLockBreakPermissions'
import { useOperationEvents } from '../hooks/useOperationEvents'
import { useJobActions } from '../components/jobs/useJobActions'
import RepositoryScopeSelect from '../components/activity/RepositoryScopeSelect'
import { CATEGORIES } from '../components/activity/categories'
import { ActivityFilters } from './activity/ActivityFilters'
import ActivityTimeline from './activity/ActivityTimeline'
import RepositoryHeader from './activity/RepositoryHeader'
import StatusLegend from './activity/StatusLegend'
import { activityKey, repositoryCount } from './activity/runs'
import type {
  OperationCategory,
  OperationProgressEvent,
  OperationTrigger,
} from '../types/operations'
import type { Repository } from '@/types'

export interface ActivityItem {
  activity_key?: string | null
  id: number
  type: string
  status: string
  started_at: string | null
  completed_at: string | null
  error_message: string | null
  repository: string | null
  repository_id?: number | null
  log_file_path: string | null
  archive_name: string | null
  package_name: string | null
  repository_path: string | null // Full repository path
  triggered_by?: string // 'manual' or 'schedule'
  schedule_id?: number | null
  schedule_name?: string | null // Schedule name if triggered by schedule
  backup_plan_id?: number | null
  backup_plan_run_id?: number | null
  backup_plan_name?: string | null
  skip_reason?: 'minimum_interval_not_elapsed' | 'source_unavailable' | null
  has_logs?: boolean
  execution_mode?: string | null
  route_strategy?: string | null
  kind?: string | null
  category?: OperationCategory | null
  trigger?: OperationTrigger | null
  depends_on_id?: number | null
  operation_id?: number | null
  hook_type?: string | null
  sort_at?: string | null
  progress_percent?: number | null
  progress_current?: number | null
  progress_total?: number | null
  progress_message?: string | null
  followups?: ActivityItem[]
}

type Progress = OperationProgressEvent['data']

const PAGE_SIZE = 50

function withProgress(item: ActivityItem, progress: Progress): ActivityItem {
  const patched =
    item.id === progress.id && (item.kind || item.type) !== 'script_execution'
      ? {
          ...item,
          progress_percent: progress.progress_percent,
          progress_current: progress.progress_current,
          progress_total: progress.progress_total,
          progress_message: progress.progress_message,
        }
      : item
  if (!patched.followups?.length) return patched
  return { ...patched, followups: patched.followups.map((step) => withProgress(step, progress)) }
}

/** Display the filterable, cursor-paginated activity feed. */
const Activity: React.FC = () => {
  const { t } = useTranslation()
  const { track, EventCategory, EventAction } = useAnalytics()
  const { hasGlobalPermission } = useAuth()
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()

  const repositoryIdParam = Number(searchParams.get('repository_id'))
  const repositoryId =
    Number.isInteger(repositoryIdParam) && repositoryIdParam > 0 ? repositoryIdParam : null
  // Links such as "View index runs" from the Background work tab open the
  // page with the category already chosen.
  const urlCategory = searchParams
    .getAll('category')
    .filter((value): value is OperationCategory => CATEGORIES.includes(value as OperationCategory))
  const urlCategoryKey = urlCategory.join(',')

  const [typeFilter, setTypeFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [categoryFilter, setCategoryFilter] = useState<OperationCategory[]>(urlCategory)
  const [triggerFilter, setTriggerFilter] = useState('all')
  useEffect(() => {
    setCategoryFilter(urlCategoryKey ? (urlCategoryKey.split(',') as OperationCategory[]) : [])
  }, [urlCategoryKey])

  const canManageActivityJobs = hasGlobalPermission('repositories.manage_all')

  const {
    data: activities,
    isLoading,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['activity', repositoryId, typeFilter, statusFilter, categoryFilter, triggerFilter],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) => {
      // The route filters by repository in SQL, per source, before each
      // source's own limit. Filtering here instead would hide a quiet
      // repository behind whatever the rest of the install did lately.
      const params: Record<string, unknown> = { limit: PAGE_SIZE }
      if (pageParam) params.before = pageParam
      if (repositoryId !== null) params.repository_id = repositoryId
      if (typeFilter !== 'all') params.job_type = typeFilter
      if (statusFilter !== 'all') params.status = statusFilter
      if (categoryFilter.length > 0) params.category = categoryFilter
      if (triggerFilter !== 'all') params.trigger = [triggerFilter]
      const response = await activityAPI.list(params)
      return response.data as ActivityItem[]
    },
    // The cursor is the sort key the route paged by, not started_at: a
    // skipped plan run sorts by when it was decided, not when it began.
    // `Z` rather than `+00:00`, which a query string reads back as a space.
    // The route never ends a page inside a group of rows sharing one
    // timestamp, so the next page can start strictly before this one.
    getNextPageParam: (lastPage) =>
      lastPage.length < PAGE_SIZE
        ? undefined
        : (lastPage[lastPage.length - 1]?.sort_at?.replace('+00:00', 'Z') ?? undefined),
    // History does not change, so stop polling once the user pages into it.
    // Live rows keep arriving over SSE either way.
    refetchInterval: (query) => ((query.state.data?.pages.length ?? 1) > 1 ? false : 3000),
  })
  // A run whose parent sat just past a page edge is pulled into that page as
  // an ancestor and comes back at the head of the next one. Keep the first
  // copy, which is the one carrying its follow-up chain.
  const items = useMemo(() => {
    const seen = new Set<string>()
    return (activities?.pages ?? []).flat().filter((item) => {
      const key = activityKey(item)
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
  }, [activities])

  const { data: repositoriesData } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })
  const repositories: Repository[] = useMemo(
    () => repositoriesData?.data?.repositories ?? [],
    [repositoriesData?.data?.repositories]
  )
  const pinnedRepository = repositories.find((repo) => repo.id === repositoryId)
  const { canBreakLock, lockBreakingEnabled } = useLockBreakPermissions({ repositories })

  // Progress arrives once a second over SSE; the list refetches every
  // three. Patching the cache in between keeps bars moving without a
  // request per tick. Status changes are rarer and get a full refetch.
  const onProgress = useCallback(
    (progress: Progress) => {
      queryClient.setQueriesData<{ pages: ActivityItem[][] }>({ queryKey: ['activity'] }, (old) =>
        old?.pages
          ? {
              ...old,
              pages: old.pages.map((page) => page.map((item) => withProgress(item, progress))),
            }
          : old
      )
    },
    [queryClient]
  )
  const onUpdated = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['activity'] })
  }, [queryClient])
  useOperationEvents(onUpdated, onProgress)

  const { actionButtons, dialogs } = useJobActions<ActivityItem>({
    actions: { viewLogs: true, downloadLogs: true, errorInfo: true, breakLock: true, delete: true },
    canBreakLocks: canBreakLock,
    lockBreakingEnabled,
    canDeleteJobs: canManageActivityJobs,
  })

  const trackFilter = (kind: string, value: string) =>
    track(EventCategory.NAVIGATION, EventAction.FILTER, {
      filter_kind: kind,
      filter_value: value,
    })

  const summary = [
    t('activity.summary.runs', { count: items.length }),
    repositoryId === null &&
      items.length > 0 &&
      t('activity.summary.repositories', { count: repositoryCount(items) }),
    categoryFilter.length === 0 && t('activity.summary.indexHidden'),
  ]
    .filter(Boolean)
    .join(' · ')
  const refreshLabel = t('activity.actions.refresh')

  return (
    <Box>
      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', sm: 'row' },
          justifyContent: 'space-between',
          alignItems: { xs: 'flex-start', sm: 'center' },
          gap: 2,
          mb: 3,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <History size={32} />
          <Box>
            <Typography variant="h4" component="h1">
              {t('activity.title')}
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              {t('activity.subtitle')}
            </Typography>
          </Box>
        </Box>
        <Box
          sx={{ display: 'flex', alignItems: 'center', gap: 1, width: { xs: '100%', sm: 'auto' } }}
        >
          <Box sx={{ width: { xs: '100%', sm: 320 } }}>
            <RepositoryScopeSelect value={repositoryId} />
          </Box>
          <IconButton onClick={() => refetch()} aria-label={refreshLabel} title={refreshLabel}>
            <RefreshCw size={20} />
          </IconButton>
        </Box>
      </Box>

      {repositoryId !== null && (
        <RepositoryHeader repositoryId={repositoryId} repository={pinnedRepository} />
      )}

      <ActivityFilters
        typeFilter={typeFilter}
        statusFilter={statusFilter}
        onTypeFilterChange={(value) => {
          setTypeFilter(value)
          trackFilter('type', value)
        }}
        onStatusFilterChange={(value) => {
          setStatusFilter(value)
          trackFilter('status', value)
        }}
        categoryFilter={categoryFilter}
        onCategoryFilterChange={(categories) => {
          setCategoryFilter(categories)
          trackFilter('category', categories.join(','))
        }}
        triggerFilter={triggerFilter}
        onTriggerFilterChange={(value) => {
          setTriggerFilter(value)
          trackFilter('trigger', value)
        }}
      />
      <Box
        sx={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 1,
          mt: -1.5,
          mb: 3,
        }}
      >
        <Typography data-testid="activity-summary" variant="body2" sx={{ color: 'text.secondary' }}>
          {isLoading && items.length === 0 ? <Skeleton width={220} /> : summary}
        </Typography>
        <StatusLegend />
      </Box>

      <ActivityTimeline
        items={items}
        loading={isLoading}
        actions={actionButtons}
        showRepository={repositoryId === null}
        getKey={activityKey}
        hasMore={hasNextPage}
        loadingMore={isFetchingNextPage}
        onLoadMore={() => fetchNextPage()}
      />
      {dialogs}
    </Box>
  )
}

export default Activity

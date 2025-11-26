import { useQuery } from '@tanstack/react-query'
import { repositoriesAPI } from '../services/api'

interface MaintenanceJob {
  id: number
  progress: number
  progress_message: string | null
  started_at: string | null
}

interface RunningJobsResponse {
  has_running_jobs: boolean
  check_job: MaintenanceJob | null
  compact_job: MaintenanceJob | null
}

/**
 * Hook to track running maintenance jobs (check/compact) for a repository
 * Polls every 3 seconds when there are active jobs
 */
export function useMaintenanceJobs(repositoryId: number | null, enabled: boolean = true) {
  const { data, isLoading } = useQuery({
    queryKey: ['running-jobs', repositoryId],
    queryFn: async () => {
      const response = await repositoriesAPI.getRunningJobs(repositoryId!)
      return response.data as RunningJobsResponse
    },
    enabled: enabled && repositoryId !== null,
    // Poll every 3 seconds when enabled, continue polling if there are running jobs
    refetchInterval: (query) => {
      if (!enabled) return false
      // Keep polling if we have running jobs, or if we haven't fetched data yet
      const data = query.state.data
      return !data || data?.has_running_jobs ? 3000 : false
    },
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: true, // Refetch when returning to tab
    refetchOnMount: true, // Refetch when component mounts
    staleTime: 0, // Always consider data stale
    gcTime: 0, // Don't cache results (was cacheTime in v3)
    retry: false,
  })

  return {
    hasRunningJobs: data?.has_running_jobs ?? false,
    checkJob: data?.check_job ?? null,
    compactJob: data?.compact_job ?? null,
    isLoading,
  }
}

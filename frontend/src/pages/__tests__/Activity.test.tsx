import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import Activity from '../Activity'
import { activityAPI } from '../../services/api'

const { activityData } = vi.hoisted(() => ({
  activityData: {
    current: [
      {
        id: 7,
        type: 'backup',
        status: 'completed',
        started_at: '2026-04-01T10:00:00Z',
        completed_at: '2026-04-01T10:05:00Z',
        error_message: null,
        repository: '/backup/repo7',
        log_file_path: '/logs/job7.log',
        archive_name: null,
        package_name: null,
        repository_path: '/backup/repo7',
        has_logs: true,
      },
    ] as Array<Record<string, unknown>>,
  },
}))
const track = vi.fn()
const refetchSpy = vi.fn()
const jobsTablePropsSpy = vi.fn()

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    track,
    EventCategory: {
      NAVIGATION: 'Navigation',
    },
    EventAction: {
      FILTER: 'Filter',
    },
  }),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    hasGlobalPermission: (permission: string) => permission === 'repositories.manage_all',
  }),
}))

vi.mock('../../hooks/useLockBreakPermissions', () => ({
  useLockBreakPermissions: () => ({
    canBreakLock: () => true,
    lockBreakingEnabled: true,
  }),
}))

vi.mock('@tanstack/react-query', async () => {
  const actual =
    await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query')
  return {
    ...actual,
    useQuery: ({ queryFn }: { queryFn: () => Promise<unknown> }) => {
      void queryFn()
      return {
        data: activityData.current,
        isLoading: false,
        refetch: refetchSpy,
      }
    },
  }
})

vi.mock('../../components/BackupJobsTable', () => ({
  default: (props: unknown) => {
    jobsTablePropsSpy(props)
    return <div>Jobs Table</div>
  },
}))

describe('Activity page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    activityData.current = [
      {
        id: 7,
        type: 'backup',
        status: 'completed',
        started_at: '2026-04-01T10:00:00Z',
        completed_at: '2026-04-01T10:05:00Z',
        error_message: null,
        repository: '/backup/repo7',
        log_file_path: '/logs/job7.log',
        archive_name: null,
        package_name: null,
        repository_path: '/backup/repo7',
        has_logs: true,
      },
    ]
    vi.spyOn(activityAPI, 'list').mockResolvedValue({ data: [] } as never)
  })

  it('passes filters into the activity API, tracks filter changes, and supports refresh', async () => {
    const user = userEvent.setup()

    renderWithProviders(<Activity />)

    expect(await screen.findByText('Jobs Table')).toBeInTheDocument()
    expect(activityAPI.list).toHaveBeenCalledWith({ limit: 200 })
    expect(jobsTablePropsSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        showTypeColumn: true,
        showTriggerColumn: true,
        canBreakLocks: expect.any(Function),
        lockBreakingEnabled: true,
        canDeleteJobs: true,
        actions: expect.objectContaining({ delete: true, breakLock: true }),
      })
    )

    fireEvent.mouseDown(screen.getAllByRole('combobox')[0])
    await user.click(await screen.findByRole('option', { name: /^Restore Check$/i }))

    await waitFor(() => {
      expect(activityAPI.list).toHaveBeenLastCalledWith({
        limit: 200,
        job_type: 'restore_check',
      })
    })
    expect(track).toHaveBeenCalledWith('Navigation', 'Filter', {
      filter_kind: 'type',
      filter_value: 'restore_check',
    })

    fireEvent.mouseDown(screen.getAllByRole('combobox')[1])
    await user.click(await screen.findByRole('option', { name: /failed/i }))

    await waitFor(() => {
      expect(activityAPI.list).toHaveBeenLastCalledWith({
        limit: 200,
        job_type: 'restore_check',
        status: 'failed',
      })
    })
    expect(track).toHaveBeenCalledWith('Navigation', 'Filter', {
      filter_kind: 'status',
      filter_value: 'failed',
    })

    fireEvent.mouseDown(screen.getAllByRole('combobox')[1])
    await user.click(await screen.findByRole('option', { name: /completed with warnings/i }))

    await waitFor(() => {
      expect(activityAPI.list).toHaveBeenLastCalledWith({
        limit: 200,
        job_type: 'restore_check',
        status: 'completed_with_warnings',
      })
    })
    expect(track).toHaveBeenCalledWith('Navigation', 'Filter', {
      filter_kind: 'status',
      filter_value: 'completed_with_warnings',
    })

    await user.click(screen.getByRole('button', { name: /refresh/i }))
    expect(refetchSpy).toHaveBeenCalled()
  })

  it('offers cloud storage activity filters and summarizes active rclone jobs', async () => {
    activityData.current = [
      {
        id: 10,
        type: 'rclone_sync',
        status: 'pending',
        started_at: null,
        completed_at: null,
        error_message: null,
        repository: 'Cloud Mirror Repo',
        log_file_path: null,
        archive_name: null,
        package_name: null,
        repository_path: '/repositories/cloud-mirror',
        triggered_by: 'initial',
        has_logs: true,
      },
      {
        id: 11,
        type: 'rclone_hydrate',
        status: 'running',
        started_at: '2026-04-01T10:00:00Z',
        completed_at: null,
        error_message: null,
        repository: 'Cloud Hydrate Repo',
        log_file_path: null,
        archive_name: null,
        package_name: null,
        repository_path: '/repositories/cloud-hydrate',
        triggered_by: 'manual',
        has_logs: true,
      },
    ]
    const user = userEvent.setup()

    renderWithProviders(<Activity />)

    expect(await screen.findByText(/Active cloud storage jobs/i)).toBeInTheDocument()
    expect(screen.getByText('Cloud Mirror Repo')).toBeInTheDocument()
    expect(screen.getByText('Cloud Hydrate Repo')).toBeInTheDocument()

    fireEvent.mouseDown(screen.getAllByRole('combobox')[0])
    await user.click(await screen.findByRole('option', { name: /^Cloud Sync$/i }))

    await waitFor(() => {
      expect(activityAPI.list).toHaveBeenLastCalledWith({
        limit: 200,
        job_type: 'rclone_sync',
      })
    })
  })
})

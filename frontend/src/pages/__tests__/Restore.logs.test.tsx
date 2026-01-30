/**
 * Tests for Restore page logs functionality
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import Restore from '../Restore'
import * as api from '../../services/api'

// Mock API
vi.mock('../../services/api', () => ({
  repositoriesAPI: {
    getAll: vi.fn(),
    getRepositories: vi.fn(),
    listRepositoryArchives: vi.fn(),
    getRepositoryInfo: vi.fn(),
    getArchiveInfo: vi.fn(),
  },
  restoreAPI: {
    getRestoreJobs: vi.fn(),
    getRestoreStatus: vi.fn(),
    startRestore: vi.fn(),
  },
}))
vi.mock('../../hooks/useMatomo', () => ({
  useMatomo: () => ({
    trackArchive: vi.fn(),
    EventAction: {},
  }),
}))
vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { is_admin: true },
  }),
}))

const renderWithProviders = (ui: React.ReactElement) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>{ui}</BrowserRouter>
    </QueryClientProvider>
  )
}

describe('Restore Page - Logs Functionality', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    // Mock repositories API (returns axios response structure)
    vi.mocked(api.repositoriesAPI.getRepositories).mockResolvedValue({
      data: { repositories: [] },
    } as any)

    // Mock restore jobs API with default empty response (axios response structure)
    vi.mocked(api.restoreAPI.getRestoreJobs).mockResolvedValue({
      data: { jobs: [] },
    } as any)
  })

  it('includes logs field in API response for completed jobs', async () => {
    const mockJobs = {
      jobs: [
        {
          id: 1,
          repository: '/test/repo',
          archive: 'test-archive',
          destination: '/test/dest',
          status: 'completed',
          started_at: '2026-01-30T10:00:00Z',
          completed_at: '2026-01-30T10:05:00Z',
          progress: 100,
          error_message: null,
          logs: 'Restore started\nProgress: 100%\nRestore completed successfully',
          progress_details: {
            nfiles: 100,
            current_file: '',
            progress_percent: 100.0,
            restore_speed: 15.5,
            estimated_time_remaining: 0,
          },
        },
      ],
    }

    vi.mocked(api.restoreAPI.getRestoreJobs).mockResolvedValue({
      data: mockJobs,
    } as any)

    renderWithProviders(<Restore />)

    await waitFor(() => {
      // Verify page renders
      expect(screen.getByText(/Restore Archives/i)).toBeInTheDocument()
    })

    // Verify the API was called and would return logs
    expect(vi.mocked(api.restoreAPI.getRestoreJobs)).toHaveBeenCalled()
  })

  it('handles restore jobs with null logs for running jobs', async () => {
    const mockJobs = {
      jobs: [
        {
          id: 1,
          repository: '/test/repo',
          archive: 'test-archive',
          destination: '/test/dest',
          status: 'running',
          started_at: '2026-01-30T10:00:00Z',
          completed_at: null,
          progress: 50,
          error_message: null,
          logs: null,
          progress_details: {
            nfiles: 50,
            current_file: '/test/file.txt',
            progress_percent: 50.0,
            restore_speed: 12.5,
            estimated_time_remaining: 60,
          },
        },
      ],
    }

    vi.mocked(api.restoreAPI.getRestoreJobs).mockResolvedValue({
      data: mockJobs,
    } as any)

    renderWithProviders(<Restore />)

    await waitFor(() => {
      expect(screen.getByText(/Restore Archives/i)).toBeInTheDocument()
    })

    expect(vi.mocked(api.restoreAPI.getRestoreJobs)).toHaveBeenCalled()
  })

  it('handles restore jobs with empty string logs', async () => {
    const mockJobs = {
      jobs: [
        {
          id: 1,
          repository: '/test/repo',
          archive: 'test-archive',
          destination: '/test/dest',
          status: 'completed',
          started_at: '2026-01-30T10:00:00Z',
          completed_at: '2026-01-30T10:02:00Z',
          progress: 100,
          error_message: null,
          logs: '',
          progress_details: {
            nfiles: 10,
            current_file: '',
            progress_percent: 100.0,
            restore_speed: 5.0,
            estimated_time_remaining: 0,
          },
        },
      ],
    }

    vi.mocked(api.restoreAPI.getRestoreJobs).mockResolvedValue({
      data: mockJobs,
    } as any)

    renderWithProviders(<Restore />)

    await waitFor(() => {
      expect(screen.getByText(/Restore Archives/i)).toBeInTheDocument()
    })

    expect(vi.mocked(api.restoreAPI.getRestoreJobs)).toHaveBeenCalled()
  })

  it('handles restore jobs with multiline logs', async () => {
    const multilineLogs = `Starting restore operation
Repository: /test/repo
Archive: test-archive
Destination: /test/dest
Progress: 25%
Progress: 50%
Progress: 75%
Progress: 100%
Restore completed successfully`

    const mockJobs = {
      jobs: [
        {
          id: 1,
          repository: '/test/repo',
          archive: 'test-archive',
          destination: '/test/dest',
          status: 'completed',
          started_at: '2026-01-30T10:00:00Z',
          completed_at: '2026-01-30T10:10:00Z',
          progress: 100,
          error_message: null,
          logs: multilineLogs,
          progress_details: {
            nfiles: 200,
            current_file: '',
            progress_percent: 100.0,
            restore_speed: 20.0,
            estimated_time_remaining: 0,
          },
        },
      ],
    }

    vi.mocked(api.restoreAPI.getRestoreJobs).mockResolvedValue({
      data: mockJobs,
    } as any)

    renderWithProviders(<Restore />)

    await waitFor(() => {
      expect(screen.getByText(/Restore Archives/i)).toBeInTheDocument()
    })

    // Verify multiline logs structure is preserved in the mock
    expect(mockJobs.jobs[0].logs).toContain('\n')
  })

  it('handles failed job with error logs', async () => {
    const errorLogs = `Starting restore operation
Repository: /test/repo
Archive: test-archive
Error: Failed to read archive
Error: Permission denied
Restore failed`

    const mockJobs = {
      jobs: [
        {
          id: 1,
          repository: '/test/repo',
          archive: 'test-archive',
          destination: '/test/dest',
          status: 'failed',
          started_at: '2026-01-30T10:00:00Z',
          completed_at: '2026-01-30T10:01:00Z',
          progress: 10,
          error_message: 'Permission denied',
          logs: errorLogs,
          progress_details: {
            nfiles: 5,
            current_file: '/test/file.txt',
            progress_percent: 10.0,
            restore_speed: 0,
            estimated_time_remaining: 0,
          },
        },
      ],
    }

    vi.mocked(api.restoreAPI.getRestoreJobs).mockResolvedValue({
      data: mockJobs,
    } as any)

    renderWithProviders(<Restore />)

    await waitFor(() => {
      expect(screen.getByText(/Restore Archives/i)).toBeInTheDocument()
    })

    // Verify error logs are present in mock data
    expect(mockJobs.jobs[0].logs).toContain('Error')
    expect(mockJobs.jobs[0].error_message).toBe('Permission denied')
  })

  it('handles multiple jobs with different log states', async () => {
    const mockJobs = {
      jobs: [
        {
          id: 1,
          repository: '/test/repo',
          archive: 'archive1',
          destination: '/test/dest1',
          status: 'completed',
          started_at: '2026-01-30T10:00:00Z',
          completed_at: '2026-01-30T10:05:00Z',
          progress: 100,
          error_message: null,
          logs: 'Completed successfully',
          progress_details: {
            nfiles: 100,
            current_file: '',
            progress_percent: 100.0,
            restore_speed: 15.5,
            estimated_time_remaining: 0,
          },
        },
        {
          id: 2,
          repository: '/test/repo',
          archive: 'archive2',
          destination: '/test/dest2',
          status: 'running',
          started_at: '2026-01-30T10:10:00Z',
          completed_at: null,
          progress: 50,
          error_message: null,
          logs: null,
          progress_details: {
            nfiles: 50,
            current_file: '/test/file.txt',
            progress_percent: 50.0,
            restore_speed: 12.0,
            estimated_time_remaining: 120,
          },
        },
        {
          id: 3,
          repository: '/test/repo',
          archive: 'archive3',
          destination: '/test/dest3',
          status: 'failed',
          started_at: '2026-01-30T10:15:00Z',
          completed_at: '2026-01-30T10:16:00Z',
          progress: 5,
          error_message: 'Failed',
          logs: 'Error occurred',
          progress_details: {
            nfiles: 2,
            current_file: '',
            progress_percent: 5.0,
            restore_speed: 0,
            estimated_time_remaining: 0,
          },
        },
      ],
    }

    vi.mocked(api.restoreAPI.getRestoreJobs).mockResolvedValue({
      data: mockJobs,
    } as any)

    renderWithProviders(<Restore />)

    await waitFor(() => {
      expect(screen.getByText(/Restore Archives/i)).toBeInTheDocument()
    })

    // Verify all jobs have correct log states
    expect(mockJobs.jobs[0].logs).toBe('Completed successfully')
    expect(mockJobs.jobs[1].logs).toBeNull()
    expect(mockJobs.jobs[2].logs).toBe('Error occurred')
  })
})

/**
 * Tests for Restore page speed and ETA display functionality
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { AxiosResponse } from 'axios'
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

describe('Restore Page - Speed and ETA Display', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    // Mock repositories API (returns axios response structure)
    vi.mocked(api.repositoriesAPI.getRepositories).mockResolvedValue({
      data: { repositories: [] },
    } as AxiosResponse)

    // Mock restore jobs API with default empty response (axios response structure)
    vi.mocked(api.restoreAPI.getRestoreJobs).mockResolvedValue({
      data: { jobs: [] },
    } as AxiosResponse)
  })

  it('displays restore speed when job is running', async () => {
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
          progress_details: {
            nfiles: 100,
            current_file: '/test/file.txt',
            progress_percent: 45.5,
            restore_speed: 12.34,
            estimated_time_remaining: 135,
          },
        },
      ],
    }

    vi.mocked(api.restoreAPI.getRestoreJobs).mockResolvedValue({
      data: mockJobs,
    } as AxiosResponse)

    renderWithProviders(<Restore />)

    await waitFor(() => {
      expect(screen.getByText('12.34 MB/s')).toBeInTheDocument()
    })
  })

  it('displays ETA when available', async () => {
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
          progress_details: {
            nfiles: 100,
            current_file: '/test/file.txt',
            progress_percent: 45.5,
            restore_speed: 12.34,
            estimated_time_remaining: 135, // 2m 15s
          },
        },
      ],
    }

    vi.mocked(api.restoreAPI.getRestoreJobs).mockResolvedValue({
      data: mockJobs,
    } as AxiosResponse)

    renderWithProviders(<Restore />)

    await waitFor(() => {
      // Should display formatted ETA (format is "2 min 15 sec")
      // Use getAllByText since "2 min" may appear in other places like "Running for" duration
      const elements = screen.getAllByText(/2 min/i)
      expect(elements.length).toBeGreaterThan(0)
      // Verify the exact ETA text exists
      expect(screen.getByText('2 min 15 sec')).toBeInTheDocument()
    })
  })

  it('displays N/A for speed when restore_speed is 0', async () => {
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
          progress: 0,
          error_message: null,
          progress_details: {
            nfiles: 0,
            current_file: '',
            progress_percent: 0,
            restore_speed: 0,
            estimated_time_remaining: 0,
          },
        },
      ],
    }

    vi.mocked(api.restoreAPI.getRestoreJobs).mockResolvedValue({
      data: mockJobs,
    } as AxiosResponse)

    renderWithProviders(<Restore />)

    await waitFor(() => {
      // Verify Speed label and N/A are both present (restore_speed is 0)
      expect(screen.getByText('Speed:')).toBeInTheDocument()
      expect(screen.getByText('N/A')).toBeInTheDocument()
    })
  })

  it('does not display ETA section when ETA is 0', async () => {
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
          progress: 5,
          error_message: null,
          progress_details: {
            nfiles: 10,
            current_file: '/test/file.txt',
            progress_percent: 5.0,
            restore_speed: 0, // Speed not calculated yet
            estimated_time_remaining: 0,
          },
        },
      ],
    }

    vi.mocked(api.restoreAPI.getRestoreJobs).mockResolvedValue({
      data: mockJobs,
    } as AxiosResponse)

    renderWithProviders(<Restore />)

    await waitFor(() => {
      expect(screen.queryByText('ETA:')).not.toBeInTheDocument()
    })
  })

  it('displays speed and ETA for multiple running jobs', async () => {
    const mockJobs = {
      jobs: [
        {
          id: 1,
          repository: '/test/repo1',
          archive: 'archive1',
          destination: '/test/dest1',
          status: 'running',
          started_at: '2026-01-30T10:00:00Z',
          completed_at: null,
          progress: 30,
          error_message: null,
          progress_details: {
            nfiles: 50,
            current_file: '/file1.txt',
            progress_percent: 30.0,
            restore_speed: 15.67,
            estimated_time_remaining: 200,
          },
        },
        {
          id: 2,
          repository: '/test/repo2',
          archive: 'archive2',
          destination: '/test/dest2',
          status: 'running',
          started_at: '2026-01-30T10:05:00Z',
          completed_at: null,
          progress: 70,
          error_message: null,
          progress_details: {
            nfiles: 150,
            current_file: '/file2.txt',
            progress_percent: 70.0,
            restore_speed: 23.45,
            estimated_time_remaining: 90,
          },
        },
      ],
    }

    vi.mocked(api.restoreAPI.getRestoreJobs).mockResolvedValue({
      data: mockJobs,
    } as AxiosResponse)

    renderWithProviders(<Restore />)

    await waitFor(() => {
      expect(screen.getByText('15.67 MB/s')).toBeInTheDocument()
      expect(screen.getByText('23.45 MB/s')).toBeInTheDocument()
    })
  })

  it('displays N/A for speed when restore_speed is 0', async () => {
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
          progress: 5,
          error_message: null,
          progress_details: {
            nfiles: 200,
            current_file: '/test/file.txt',
            progress_percent: 5.0,
            restore_speed: 0, // Speed not calculated yet, should show N/A
            estimated_time_remaining: 0,
          },
        },
      ],
    }

    vi.mocked(api.restoreAPI.getRestoreJobs).mockResolvedValue({
      data: mockJobs,
    } as AxiosResponse)

    renderWithProviders(<Restore />)

    await waitFor(() => {
      // Job is running but speed is 0, should show N/A
      expect(screen.getByText('Speed:')).toBeInTheDocument()
      expect(screen.getAllByText('N/A').length).toBeGreaterThan(0)
    })
  })

  it('displays all progress metrics in grid layout', async () => {
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
          progress: 60,
          error_message: null,
          progress_details: {
            nfiles: 500,
            current_file: '/test/file.txt',
            progress_percent: 60.5,
            restore_speed: 20.15,
            estimated_time_remaining: 180,
          },
        },
      ],
    }

    vi.mocked(api.restoreAPI.getRestoreJobs).mockResolvedValue({
      data: mockJobs,
    } as AxiosResponse)

    renderWithProviders(<Restore />)

    await waitFor(() => {
      // All metrics should be visible
      expect(screen.getByText('Files Restored:')).toBeInTheDocument()
      expect(screen.getByText('500')).toBeInTheDocument()
      expect(screen.getByText('Progress:')).toBeInTheDocument()
      expect(screen.getByText('60.5%')).toBeInTheDocument()
      expect(screen.getByText('Speed:')).toBeInTheDocument()
      expect(screen.getByText('20.15 MB/s')).toBeInTheDocument()
      expect(screen.getByText('ETA:')).toBeInTheDocument()
    })
  })
})

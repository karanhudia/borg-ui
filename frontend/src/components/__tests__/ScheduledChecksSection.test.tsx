import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createRef } from 'react'
import { act, fireEvent, waitFor } from '@testing-library/react'
import { AxiosResponse } from 'axios'

import ScheduledChecksSection, { type ScheduledChecksSectionRef } from '../ScheduledChecksSection'
import { renderWithProviders, screen } from '../../test/test-utils'
import { repositoriesAPI } from '@/services/api.ts'

vi.mock('../../services/api', () => ({
  repositoriesAPI: {
    getRepositories: vi.fn(),
    list: vi.fn(),
    getCheckSchedule: vi.fn(),
    getRepositoryCheckJobs: vi.fn(),
    updateCheckSchedule: vi.fn(),
  },
}))

vi.mock('../../services/borgApi', () => ({
  BorgApiClient: vi.fn().mockImplementation(() => ({
    checkRepository: vi.fn(),
  })),
}))

vi.mock('../../hooks/usePermissions', () => ({
  usePermissions: () => ({
    canDo: () => true,
  }),
}))

vi.mock('react-hot-toast', async () => {
  const actual = await vi.importActual('react-hot-toast')
  return {
    ...actual,
    toast: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }
})

describe('ScheduledChecksSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(repositoriesAPI.getRepositories).mockResolvedValue({
      data: {
        repositories: [
          {
            id: 1,
            name: 'Repo One',
            path: '/repo-one',
            borg_version: 1,
          },
        ],
      },
    } as AxiosResponse)
    vi.mocked(repositoriesAPI.list).mockResolvedValue({
      data: {
        repositories: [
          {
            id: 1,
            name: 'Repo One',
            path: '/repo-one',
            borg_version: 1,
          },
        ],
      },
    } as AxiosResponse)
    vi.mocked(repositoriesAPI.getCheckSchedule).mockResolvedValue({
      data: {
        repository_id: 1,
        repository_name: 'Repo One',
        repository_path: '/repo-one',
        check_cron_expression: '0 2 * * *',
        last_scheduled_check: null,
        next_scheduled_check: null,
        check_max_duration: 3600,
        check_extra_flags: '--repair',
        notify_on_check_success: false,
        notify_on_check_failure: true,
        enabled: true,
      },
    } as AxiosResponse)
    vi.mocked(repositoriesAPI.updateCheckSchedule).mockResolvedValue({ data: {} } as AxiosResponse)
    vi.mocked(repositoriesAPI.getRepositoryCheckJobs).mockResolvedValue({
      data: {
        jobs: [
          {
            id: 11,
            repository_id: 1,
            status: 'completed',
            started_at: '2026-04-24T01:00:00Z',
            completed_at: '2026-04-24T01:10:00Z',
            error_message: null,
            has_logs: true,
            scheduled_check: true,
          },
        ],
      },
    } as AxiosResponse)
  })

  it('renders scheduled check history table', async () => {
    renderWithProviders(<ScheduledChecksSection />)

    await waitFor(() => {
      expect(screen.getByText('Scheduled Check History')).toBeInTheDocument()
    })

    expect(await screen.findByText('Repo One')).toBeInTheDocument()
  })

  it('prefills and saves advanced check flags for scheduled checks', async () => {
    const sectionRef = createRef<ScheduledChecksSectionRef>()

    renderWithProviders(<ScheduledChecksSection ref={sectionRef} />)

    await waitFor(() => {
      expect(sectionRef.current).not.toBeNull()
    })

    await act(async () => {
      await sectionRef.current?.openEditForRepo(1)
    })

    const flagsInput = await screen.findByLabelText('Advanced check flags')
    expect(flagsInput).toHaveValue('--repair')

    fireEvent.change(flagsInput, { target: { value: '--verify-data' } })
    fireEvent.click(screen.getByRole('button', { name: 'Update' }))

    await waitFor(() => {
      expect(repositoriesAPI.updateCheckSchedule).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          check_extra_flags: '--verify-data',
        })
      )
    })
  }, 60000)
})

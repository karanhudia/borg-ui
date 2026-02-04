import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import UpcomingJobsTable from '../UpcomingJobsTable'

// Mock date utils
vi.mock('../../utils/dateUtils', () => ({
  formatDate: vi.fn((date: string) => {
    return new Date(date).toLocaleDateString()
  }),
  formatRelativeTime: vi.fn((date: string | null | undefined) => {
    if (!date) return 'Never'
    return 'in 2 hours'
  }),
}))

describe('UpcomingJobsTable', () => {
  const mockRepositories = [
    { id: 1, name: 'Repo 1', path: '/path/to/repo1' },
    { id: 2, name: 'Repo 2', path: '/path/to/repo2' },
    { id: 3, name: 'Repo 3', path: '/path/to/repo3' },
  ]

  const mockGetRepositoryName = vi.fn((path: string) => {
    const repo = mockRepositories.find((r) => r.path === path)
    return repo?.name || path
  })

  it('renders nothing when upcomingJobs is empty', () => {
    const { container } = render(
      <UpcomingJobsTable
        upcomingJobs={[]}
        repositories={mockRepositories}
        isLoading={false}
        getRepositoryName={mockGetRepositoryName}
      />
    )

    expect(container.firstChild).toBeNull()
  })

  it('renders card with header when upcomingJobs has items', () => {
    const mockJobs = [
      {
        id: 1,
        name: 'Daily Backup',
        repository_id: 1,
        next_run: '2024-01-01T14:00:00Z',
        cron_expression: '0 14 * * *',
      },
    ]

    render(
      <UpcomingJobsTable
        upcomingJobs={mockJobs}
        repositories={mockRepositories}
        isLoading={false}
        getRepositoryName={mockGetRepositoryName}
      />
    )

    expect(screen.getByText('Upcoming Jobs (Next 24 Hours)')).toBeInTheDocument()
  })

  it('displays job name correctly', () => {
    const mockJobs = [
      {
        id: 1,
        name: 'Daily Backup Job',
        repository_id: 1,
        next_run: '2024-01-01T14:00:00Z',
        cron_expression: '0 14 * * *',
      },
    ]

    render(
      <UpcomingJobsTable
        upcomingJobs={mockJobs}
        repositories={mockRepositories}
        isLoading={false}
        getRepositoryName={mockGetRepositoryName}
      />
    )

    expect(screen.getByText('Daily Backup Job')).toBeInTheDocument()
  })

  it('displays single repository name when repository_id is provided', () => {
    const mockJobs = [
      {
        id: 1,
        name: 'Daily Backup',
        repository_id: 1,
        next_run: '2024-01-01T14:00:00Z',
        cron_expression: '0 14 * * *',
      },
    ]

    render(
      <UpcomingJobsTable
        upcomingJobs={mockJobs}
        repositories={mockRepositories}
        isLoading={false}
        getRepositoryName={mockGetRepositoryName}
      />
    )

    expect(screen.getByText('Repo 1')).toBeInTheDocument()
  })

  it('displays repository count when repository_ids array is provided', () => {
    const mockJobs = [
      {
        id: 1,
        name: 'Multi-Repo Backup',
        repository_ids: [1, 2, 3],
        next_run: '2024-01-01T14:00:00Z',
        cron_expression: '0 14 * * *',
      },
    ]

    render(
      <UpcomingJobsTable
        upcomingJobs={mockJobs}
        repositories={mockRepositories}
        isLoading={false}
        getRepositoryName={mockGetRepositoryName}
      />
    )

    expect(screen.getByText('3 repositories')).toBeInTheDocument()
  })

  it('uses getRepositoryName for legacy repository path', () => {
    const mockJobs = [
      {
        id: 1,
        name: 'Legacy Backup',
        repository: '/path/to/repo1',
        next_run: '2024-01-01T14:00:00Z',
        cron_expression: '0 14 * * *',
      },
    ]

    render(
      <UpcomingJobsTable
        upcomingJobs={mockJobs}
        repositories={mockRepositories}
        isLoading={false}
        getRepositoryName={mockGetRepositoryName}
      />
    )

    expect(mockGetRepositoryName).toHaveBeenCalledWith('/path/to/repo1')
    expect(screen.getByText('Repo 1')).toBeInTheDocument()
  })

  it('displays next run time using formatDate', () => {
    const mockJobs = [
      {
        id: 1,
        name: 'Daily Backup',
        repository_id: 1,
        next_run: '2024-01-01T14:00:00Z',
        cron_expression: '0 14 * * *',
      },
    ]

    render(
      <UpcomingJobsTable
        upcomingJobs={mockJobs}
        repositories={mockRepositories}
        isLoading={false}
        getRepositoryName={mockGetRepositoryName}
      />
    )

    // The formatDate mock returns toLocaleDateString()
    const formattedDate = new Date('2024-01-01T14:00:00Z').toLocaleDateString()
    expect(screen.getByText(formattedDate)).toBeInTheDocument()
  })

  it('displays relative time using formatRelativeTime', () => {
    const mockJobs = [
      {
        id: 1,
        name: 'Daily Backup',
        repository_id: 1,
        next_run: '2024-01-01T14:00:00Z',
        cron_expression: '0 14 * * *',
      },
    ]

    render(
      <UpcomingJobsTable
        upcomingJobs={mockJobs}
        repositories={mockRepositories}
        isLoading={false}
        getRepositoryName={mockGetRepositoryName}
      />
    )

    expect(screen.getByText('in 2 hours')).toBeInTheDocument()
  })

  it('displays maximum of 5 jobs even when more are provided', () => {
    const mockJobs = Array.from({ length: 10 }, (_, i) => ({
      id: i + 1,
      name: `Job ${i + 1}`,
      repository_id: 1,
      next_run: '2024-01-01T14:00:00Z',
      cron_expression: '0 14 * * *',
    }))

    render(
      <UpcomingJobsTable
        upcomingJobs={mockJobs}
        repositories={mockRepositories}
        isLoading={false}
        getRepositoryName={mockGetRepositoryName}
      />
    )

    expect(screen.getByText('Job 1')).toBeInTheDocument()
    expect(screen.getByText('Job 5')).toBeInTheDocument()
    expect(screen.queryByText('Job 6')).not.toBeInTheDocument()
  })

  it('displays multiple jobs correctly', () => {
    const mockJobs = [
      {
        id: 1,
        name: 'Morning Backup',
        repository_id: 1,
        next_run: '2024-01-01T08:00:00Z',
        cron_expression: '0 8 * * *',
      },
      {
        id: 2,
        name: 'Evening Backup',
        repository_ids: [1, 2],
        next_run: '2024-01-01T20:00:00Z',
        cron_expression: '0 20 * * *',
      },
    ]

    render(
      <UpcomingJobsTable
        upcomingJobs={mockJobs}
        repositories={mockRepositories}
        isLoading={false}
        getRepositoryName={mockGetRepositoryName}
      />
    )

    expect(screen.getByText('Morning Backup')).toBeInTheDocument()
    expect(screen.getByText('Evening Backup')).toBeInTheDocument()
    expect(screen.getByText('Repo 1')).toBeInTheDocument()
    expect(screen.getByText('2 repositories')).toBeInTheDocument()
  })

  it('handles unknown repository_id gracefully', () => {
    const mockJobs = [
      {
        id: 1,
        name: 'Unknown Repo Backup',
        repository_id: 999, // Non-existent repository
        next_run: '2024-01-01T14:00:00Z',
        cron_expression: '0 14 * * *',
      },
    ]

    render(
      <UpcomingJobsTable
        upcomingJobs={mockJobs}
        repositories={mockRepositories}
        isLoading={false}
        getRepositoryName={mockGetRepositoryName}
      />
    )

    expect(screen.getByText('Unknown')).toBeInTheDocument()
  })

  it('renders Calendar icon', () => {
    const mockJobs = [
      {
        id: 1,
        name: 'Daily Backup',
        repository_id: 1,
        next_run: '2024-01-01T14:00:00Z',
        cron_expression: '0 14 * * *',
      },
    ]

    const { container } = render(
      <UpcomingJobsTable
        upcomingJobs={mockJobs}
        repositories={mockRepositories}
        isLoading={false}
        getRepositoryName={mockGetRepositoryName}
      />
    )

    // Check that SVG icon is rendered (lucide-react renders as SVG)
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
  })
})

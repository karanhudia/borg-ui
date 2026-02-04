import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ScheduledJobsTable from '../ScheduledJobsTable'

// Mock DataTable component
vi.mock('../DataTable', () => ({
  default: ({
    data,
    loading,
    emptyState,
  }: {
    data: unknown[]
    loading: boolean
    emptyState: { title: string; description: string }
  }) => {
    if (loading) {
      return <div>Loading...</div>
    }
    if (data.length === 0) {
      return (
        <div>
          <div>{emptyState.title}</div>
          <div>{emptyState.description}</div>
        </div>
      )
    }
    return <div data-testid="data-table">DataTable with {data.length} rows</div>
  },
}))

describe('ScheduledJobsTable', () => {
  const mockJobs = [
    {
      id: 1,
      name: 'Daily Backup',
      enabled: true,
      description: 'Daily backup job',
      run_prune_after: true,
      run_compact_after: false,
      prune_keep_hourly: 0,
      prune_keep_daily: 7,
      prune_keep_weekly: 4,
      prune_keep_monthly: 6,
      prune_keep_quarterly: 0,
      prune_keep_yearly: 1,
    },
  ]

  const mockColumns = [
    {
      id: 'name',
      label: 'Name',
      render: (job: (typeof mockJobs)[0]) => job.name,
    },
  ]

  const mockActions = [
    {
      icon: 'edit',
      label: 'Edit',
      onClick: vi.fn(),
    },
  ]

  it('renders the table header', () => {
    render(
      <ScheduledJobsTable
        jobs={mockJobs}
        columns={mockColumns}
        actions={mockActions}
        isLoading={false}
      />
    )

    expect(screen.getByText('All Scheduled Jobs')).toBeInTheDocument()
  })

  it('renders DataTable with jobs', () => {
    render(
      <ScheduledJobsTable
        jobs={mockJobs}
        columns={mockColumns}
        actions={mockActions}
        isLoading={false}
      />
    )

    expect(screen.getByTestId('data-table')).toBeInTheDocument()
    expect(screen.getByText('DataTable with 1 rows')).toBeInTheDocument()
  })

  it('shows loading state when isLoading is true', () => {
    render(
      <ScheduledJobsTable
        jobs={mockJobs}
        columns={mockColumns}
        actions={mockActions}
        isLoading={true}
      />
    )

    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('shows empty state when jobs array is empty', () => {
    render(
      <ScheduledJobsTable jobs={[]} columns={mockColumns} actions={mockActions} isLoading={false} />
    )

    expect(screen.getByText('No scheduled jobs found')).toBeInTheDocument()
    expect(screen.getByText('Create your first scheduled backup job')).toBeInTheDocument()
  })

  it('renders with multiple jobs', () => {
    const multipleJobs = [
      ...mockJobs,
      {
        id: 2,
        name: 'Weekly Backup',
        enabled: false,
        description: 'Weekly backup job',
        run_prune_after: false,
        run_compact_after: true,
        prune_keep_hourly: 0,
        prune_keep_daily: 7,
        prune_keep_weekly: 4,
        prune_keep_monthly: 6,
        prune_keep_quarterly: 0,
        prune_keep_yearly: 1,
      },
    ]

    render(
      <ScheduledJobsTable
        jobs={multipleJobs}
        columns={mockColumns}
        actions={mockActions}
        isLoading={false}
      />
    )

    expect(screen.getByText('DataTable with 2 rows')).toBeInTheDocument()
  })

  it('renders in a Card component', () => {
    const { container } = render(
      <ScheduledJobsTable
        jobs={mockJobs}
        columns={mockColumns}
        actions={mockActions}
        isLoading={false}
      />
    )

    // MUI Card has specific classes
    const card = container.querySelector('.MuiCard-root')
    expect(card).toBeInTheDocument()
  })

  it('renders in a CardContent component', () => {
    const { container } = render(
      <ScheduledJobsTable
        jobs={mockJobs}
        columns={mockColumns}
        actions={mockActions}
        isLoading={false}
      />
    )

    // MUI CardContent has specific classes
    const cardContent = container.querySelector('.MuiCardContent-root')
    expect(cardContent).toBeInTheDocument()
  })
})

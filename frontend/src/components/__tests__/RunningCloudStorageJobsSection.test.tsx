import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import RunningCloudStorageJobsSection from '../RunningCloudStorageJobsSection'
import { renderWithProviders } from '../../test/test-utils'

const activeJobs = [
  {
    id: 10,
    type: 'rclone_sync',
    status: 'pending',
    started_at: null,
    completed_at: null,
    error_message: null,
    repository: 'Cloud Mirror Repo',
    repository_path: '/repositories/cloud-mirror',
    log_file_path: null,
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
    repository_path: '/repositories/cloud-hydrate',
    log_file_path: null,
    triggered_by: 'manual',
    has_logs: true,
  },
]

describe('RunningCloudStorageJobsSection', () => {
  it('returns nothing when there are no active cloud storage jobs', () => {
    renderWithProviders(<RunningCloudStorageJobsSection jobs={[]} onViewLogs={vi.fn()} />)

    expect(screen.queryByText(/Active cloud storage jobs/i)).not.toBeInTheDocument()
  })

  it('renders pending and running rclone jobs with repository context', () => {
    renderWithProviders(<RunningCloudStorageJobsSection jobs={activeJobs} onViewLogs={vi.fn()} />)

    expect(screen.getByText(/Active cloud storage jobs/i)).toBeInTheDocument()
    expect(screen.getByText('Cloud Mirror Repo')).toBeInTheDocument()
    expect(screen.getByText('/repositories/cloud-mirror')).toBeInTheDocument()
    expect(screen.getByText('Cloud Hydrate Repo')).toBeInTheDocument()
    expect(screen.getByText('/repositories/cloud-hydrate')).toBeInTheDocument()
    expect(screen.getByText(/Initial sync/i)).toBeInTheDocument()
    expect(screen.getByText(/Hydrating cache/i)).toBeInTheDocument()
  })

  it('opens logs for the selected rclone job', async () => {
    const user = userEvent.setup()
    const onViewLogs = vi.fn()
    renderWithProviders(<RunningCloudStorageJobsSection jobs={activeJobs} onViewLogs={onViewLogs} />)

    await user.click(screen.getAllByRole('button', { name: /view logs/i })[0])

    expect(onViewLogs).toHaveBeenCalledWith(activeJobs[0])
  })
})

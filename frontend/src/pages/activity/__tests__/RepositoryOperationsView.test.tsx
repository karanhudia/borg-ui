import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent } from '@testing-library/react'
import { screen, waitFor, within, renderWithProviders, userEvent } from '../../../test/test-utils'
import RepositoryOperationsView from '../RepositoryOperationsView'
import { activityAPI, repositoriesAPI } from '../../../services/api'

vi.mock('../../../services/api', () => ({
  activityAPI: { list: vi.fn() },
  repositoriesAPI: { getRepositories: vi.fn() },
}))

vi.mock('../../../components/LogViewerDialog', () => ({
  default: ({ open }: { open: boolean }) => (open ? <div>Log Viewer</div> : null),
}))

const hoursAgo = (hours: number) => new Date(Date.now() - hours * 3600 * 1000).toISOString()

const run = (overrides: Record<string, unknown>) => ({
  id: 1,
  type: 'backup',
  kind: 'backup',
  category: 'backup',
  status: 'completed',
  trigger: 'plan',
  started_at: hoursAgo(1),
  completed_at: hoursAgo(0.5),
  error_message: null,
  repository: 'nas',
  repository_id: 1,
  log_file_path: '/logs/1.log',
  archive_name: 'nas-2026-09-05',
  package_name: null,
  repository_path: '/mnt/nas',
  backup_plan_name: 'nightly',
  has_logs: true,
  followups: [],
  ...overrides,
})

describe('RepositoryOperationsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(repositoriesAPI.getRepositories as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        repositories: [
          { id: 1, name: 'nas', path: '/mnt/nas' },
          { id: 2, name: 'photos', path: '/mnt/photos' },
        ],
      },
    })
    ;(activityAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: [
        run({ id: 1, followups: [{ id: 11, kind: 'archive_sync', status: 'completed' }] }),
        run({
          id: 2,
          kind: 'prune',
          category: 'maintenance',
          trigger: 'schedule',
          schedule_name: 'weekly',
          backup_plan_name: null,
          status: 'running',
          started_at: hoursAgo(26),
          completed_at: null,
          followups: [{ id: 21, kind: 'history_merge', status: 'running' }],
        }),
        run({ id: 3, repository_id: 2, repository: 'photos', repository_path: '/mnt/photos' }),
      ],
    })
  })

  it('titles the view with the repository and groups its runs by day', async () => {
    renderWithProviders(<RepositoryOperationsView repositoryId={1} />)
    expect(await screen.findByRole('heading', { name: 'nas' })).toBeInTheDocument()
    expect(screen.getByText('Today')).toBeInTheDocument()
    expect(screen.getByText('Yesterday')).toBeInTheDocument()
    expect(screen.getAllByTestId('run-row')).toHaveLength(2)
    expect(
      screen.queryAllByTestId('run-row').some((row) => row.textContent?.includes('photos'))
    ).toBe(false)
  })

  it('switches repositories from the header selector', async () => {
    renderWithProviders(<RepositoryOperationsView repositoryId={1} />, {
      initialRoute: '/activity?repository_id=1',
    })
    await screen.findByRole('heading', { name: 'nas' })
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /repository/i }))
    await userEvent.click(await screen.findByRole('option', { name: /photos/ }))
    await waitFor(() => expect(window.location.search).toBe('?repository_id=2'))
  })

  it('shows the trigger source and archive for a run', async () => {
    renderWithProviders(<RepositoryOperationsView repositoryId={1} />)
    const rows = await screen.findAllByTestId('run-row')
    expect(within(rows[0]).getByText(/plan: nightly/i)).toBeInTheDocument()
    expect(within(rows[0]).getByText('nas-2026-09-05')).toBeInTheDocument()
    expect(within(rows[1]).getByText(/schedule: weekly/i)).toBeInTheDocument()
  })

  it('collapses a succeeded chain and expands a running one', async () => {
    renderWithProviders(<RepositoryOperationsView repositoryId={1} />)
    const rows = await screen.findAllByTestId('run-row')
    expect(within(rows[0]).getByText('1 follow-up')).toBeInTheDocument()
    expect(within(rows[1]).getByText('history merge')).toBeInTheDocument()
  })

  it('passes category and trigger filters to the activity API', async () => {
    renderWithProviders(<RepositoryOperationsView repositoryId={1} />)
    await screen.findAllByTestId('run-row')
    await userEvent.click(screen.getByRole('button', { name: /maintenance/i }))
    await waitFor(() =>
      expect(activityAPI.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ category: ['maintenance'] })
      )
    )
  })

  it('opens the log viewer for a run', async () => {
    renderWithProviders(<RepositoryOperationsView repositoryId={1} />)
    const rows = await screen.findAllByTestId('run-row')
    await userEvent.click(within(rows[0]).getByRole('button', { name: /logs/i }))
    expect(await screen.findByText('Log Viewer')).toBeInTheDocument()
  })

  it('links back to the global activity page', async () => {
    renderWithProviders(<RepositoryOperationsView repositoryId={1} />)
    expect(await screen.findByRole('link', { name: /all activity/i })).toHaveAttribute(
      'href',
      '/activity'
    )
  })
})

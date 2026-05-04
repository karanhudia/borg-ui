import { useRef } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AxiosResponse } from 'axios'

import ScheduledRestoreChecksSection, {
  ScheduledRestoreChecksSectionRef,
} from '../ScheduledRestoreChecksSection'
import { renderWithProviders, screen, waitFor, userEvent } from '../../test/test-utils'
import { repositoriesAPI } from '@/services/api.ts'

const { listArchivesMock, getArchiveContentsMock } = vi.hoisted(() => ({
  listArchivesMock: vi.fn(),
  getArchiveContentsMock: vi.fn(),
}))

vi.mock('../../services/api', () => ({
  repositoriesAPI: {
    getRepositories: vi.fn(),
    getRestoreCheckSchedule: vi.fn(),
    updateRestoreCheckSchedule: vi.fn(),
    restoreCheckRepository: vi.fn(),
    getRepositoryRestoreCheckJobs: vi.fn(),
    getRestoreCheckJobStatus: vi.fn(),
  },
  activityAPI: {
    list: vi.fn(),
    getLogs: vi.fn(),
  },
}))

vi.mock('../../services/borgApi', () => ({
  BorgApiClient: vi.fn().mockImplementation(function () {
    return {
      listArchives: listArchivesMock,
      getArchiveContents: getArchiveContentsMock,
    }
  }),
}))

vi.mock('../../services/borgApi/client', () => ({
  BorgApiClient: vi.fn().mockImplementation(function () {
    return {
      listArchives: listArchivesMock,
      getArchiveContents: getArchiveContentsMock,
    }
  }),
}))

vi.mock('../RepoSelect', () => ({
  default: ({
    repositories,
    value,
    onChange,
    label,
  }: {
    repositories: Array<{ id: number; name: string }>
    value: string | number
    onChange: (value: string) => void
    label: string
  }) => (
    <select
      aria-label={label}
      value={String(value)}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">Select repository</option>
      {repositories.map((repo) => (
        <option key={repo.id} value={repo.id}>
          {repo.name}
        </option>
      ))}
    </select>
  ),
}))

vi.mock('../CronBuilderDialog', () => ({
  default: () => <button type="button">Cron builder</button>,
}))

vi.mock('../TerminalLogViewer', () => ({
  TerminalLogViewer: () => <div data-testid="terminal-log-viewer" />,
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

function TestHarness() {
  const sectionRef = useRef<ScheduledRestoreChecksSectionRef>(null)
  return (
    <>
      <button type="button" onClick={() => sectionRef.current?.openAddDialog()}>
        Open restore check dialog
      </button>
      <ScheduledRestoreChecksSection ref={sectionRef} />
    </>
  )
}

describe('ScheduledRestoreChecksSection', () => {
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
    vi.mocked(repositoriesAPI.getRestoreCheckSchedule).mockResolvedValue({
      data: {
        repository_id: 1,
        repository_name: 'Repo One',
        repository_path: '/repo-one',
        restore_check_cron_expression: null,
        restore_check_paths: [],
        restore_check_full_archive: false,
        restore_check_mode: 'canary',
        last_restore_check: null,
        last_scheduled_restore_check: null,
        next_scheduled_restore_check: null,
        notify_on_restore_check_success: false,
        notify_on_restore_check_failure: true,
        enabled: false,
      },
    } as AxiosResponse)
    vi.mocked(repositoriesAPI.getRepositoryRestoreCheckJobs).mockResolvedValue({
      data: { jobs: [] },
    } as AxiosResponse)
    listArchivesMock.mockResolvedValue({
      data: {
        archives: [
          {
            id: 'old-archive',
            archive: 'old-archive',
            name: 'old-archive',
            start: '2026-01-01T00:00:00Z',
            time: '2026-01-01T00:00:00Z',
          },
          {
            id: 'latest-archive',
            archive: 'latest-archive',
            name: 'latest-archive',
            start: '2026-01-02T00:00:00Z',
            time: '2026-01-02T00:00:00Z',
          },
        ],
      },
    })
    getArchiveContentsMock.mockResolvedValue({
      data: {
        items: [
          { name: 'etc', path: 'etc', type: 'directory' },
          { name: 'config.yml', path: 'srv/app/config.yml', type: 'file', size: 42 },
        ],
      },
    })
  })

  it('imports selected files and folders from the latest archive into probe paths', async () => {
    const user = userEvent.setup()

    renderWithProviders(<TestHarness />)

    await user.click(screen.getByRole('button', { name: 'Open restore check dialog' }))
    await user.selectOptions(await screen.findByLabelText('Repository'), '1')
    expect(screen.queryByLabelText('Probe Paths')).not.toBeInTheDocument()

    await user.click(screen.getByLabelText('Selected probe paths'))
    expect(screen.getByLabelText('Probe Paths')).toBeInTheDocument()

    const browseArchiveButton = screen.getByRole('button', { name: 'Browse latest archive' })
    expect(browseArchiveButton).toBeEnabled()

    await user.click(browseArchiveButton)

    expect(await screen.findByText('Choose probe paths')).toBeInTheDocument()
    await waitFor(() => {
      expect(listArchivesMock).toHaveBeenCalled()
      expect(getArchiveContentsMock).toHaveBeenCalledWith('latest-archive', 'latest-archive', '')
    })

    await user.click(screen.getByLabelText('Select directory and all contents'))
    await user.click(screen.getByText('config.yml'))
    await user.click(screen.getByRole('button', { name: 'Import Paths' }))

    expect(screen.getByLabelText('Probe Paths')).toHaveValue('etc\nsrv/app/config.yml')
  })

  it('opens restore-check logs in the generic log viewer dialog', async () => {
    const user = userEvent.setup()
    vi.mocked(repositoriesAPI.getRepositoryRestoreCheckJobs).mockResolvedValue({
      data: {
        jobs: [
          {
            id: 44,
            repository_id: 1,
            status: 'completed',
            started_at: '2026-01-02T00:00:00Z',
            completed_at: '2026-01-02T00:02:00Z',
            archive_name: 'latest-archive',
            has_logs: true,
            error_message: null,
            probe_paths: ['etc'],
            mode: 'probe_paths',
          },
        ],
      },
    } as AxiosResponse)

    renderWithProviders(<ScheduledRestoreChecksSection />)

    expect(await screen.findByRole('button', { name: 'View logs' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'View logs' }))

    expect(await screen.findByText('Restore Check Logs - Job #44')).toBeInTheDocument()
    expect(screen.getByTestId('terminal-log-viewer')).toBeInTheDocument()
  })

  it('shows UTC context in the started time tooltip', async () => {
    const user = userEvent.setup()
    vi.mocked(repositoriesAPI.getRepositoryRestoreCheckJobs).mockResolvedValue({
      data: {
        jobs: [
          {
            id: 45,
            repository_id: 1,
            status: 'completed',
            started_at: '2026-01-02T00:00:00Z',
            completed_at: '2026-01-02T00:02:00Z',
            archive_name: 'latest-archive',
            has_logs: true,
            error_message: null,
            probe_paths: ['etc'],
            mode: 'probe_paths',
          },
        ],
      },
    } as AxiosResponse)

    renderWithProviders(<ScheduledRestoreChecksSection />)

    const startedTime = await screen.findByText((content, element) => {
      return element?.tagName.toLowerCase() === 'p' && content.includes('2026')
    })

    await user.hover(startedTime)

    expect(await screen.findByText('Stored UTC')).toBeInTheDocument()
    expect(screen.getByText('UTC')).toBeInTheDocument()
  })
})

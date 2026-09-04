import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '../../test/test-utils'
import ArchiveDetail from '../ArchiveDetail'
import { archivesAPI, repositoriesAPI } from '../../services/api'

let mockParams = { repositoryId: '7', archiveId: '12' }

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return {
    ...actual,
    useParams: () => mockParams,
  }
})

vi.mock('../../services/api', () => ({
  archivesAPI: {
    getArchive: vi.fn(),
  },
  repositoriesAPI: {
    getRepositories: vi.fn(),
  },
}))

const archive = {
  id: 12,
  repository_id: 7,
  borg_id: 'abc123',
  name: 'nas-2026-09-02T02:00',
  series: 'nightly',
  start: '2026-09-02T02:00:00Z',
  end: '2026-09-02T02:14:00Z',
  duration_seconds: 840,
  nfiles: 12000,
  original_size: 90_000_000_000,
  compressed_size: 60_000_000_000,
  deduplicated_size: 41_200_000_000,
  hostname: 'nas',
  username: 'root',
  comment: null,
  backup_operation_id: 55,
  history_state: 'indexed' as const,
  history_indexed_at: '2026-09-02T02:20:00Z',
  history_rows: 40,
  history_truncated: false,
  first_seen_at: '2026-09-02T02:00:00Z',
  last_seen_at: '2026-09-02T02:00:00Z',
  predecessor_id: 11,
  successor_id: null,
  history_available: true,
}

function renderRoute(path: string) {
  const parts = path.split('/').filter(Boolean)
  mockParams = { repositoryId: parts[1], archiveId: parts[2] }
  renderWithProviders(<ArchiveDetail />, { initialRoute: path })
}

describe('ArchiveDetail', () => {
  beforeEach(() => {
    vi.mocked(archivesAPI.getArchive).mockReset()
    vi.mocked(repositoriesAPI.getRepositories).mockReset()
    vi.mocked(repositoriesAPI.getRepositories).mockResolvedValue({
      data: { repositories: [{ id: 7, name: 'nas', path: '/data/nas', mode: 'full' }] },
    } as never)
  })

  it('shows the archive header and defaults to the Changes tab', async () => {
    vi.mocked(archivesAPI.getArchive).mockResolvedValue({ data: archive } as never)
    renderRoute('/archives/7/12')
    expect(await screen.findByText('nas-2026-09-02T02:00')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /changes/i })).toHaveAttribute('aria-selected', 'true')
  })

  it('switches to the Info tab', async () => {
    vi.mocked(archivesAPI.getArchive).mockResolvedValue({ data: archive } as never)
    renderRoute('/archives/7/12')
    fireEvent.click(await screen.findByRole('tab', { name: /info/i }))
    expect(await screen.findByText(/nightly/)).toBeInTheDocument()
  })

  it('reports an archive that cannot be loaded', async () => {
    vi.mocked(archivesAPI.getArchive).mockRejectedValue(new Error('nope'))
    renderRoute('/archives/7/999')
    expect(await screen.findByText(/could not be loaded/i)).toBeInTheDocument()
  })
})

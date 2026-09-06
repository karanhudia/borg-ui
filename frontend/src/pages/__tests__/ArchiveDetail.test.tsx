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

vi.mock('../../components/archives/ArchiveFilesTab', () => ({
  default: ({
    onRestorePaths,
  }: {
    onRestorePaths?: (paths: string[], items: unknown[], fromArchiveId?: number) => void
  }) => (
    <>
      <button onClick={() => onRestorePaths?.(['home/karan/docs'], [])}>Restore selection</button>
      <button onClick={() => onRestorePaths?.(['home/karan/docs/invoices.xlsx'], [], 9)}>
        Restore this version
      </button>
    </>
  ),
}))

vi.mock('../../components/RestoreWizard', () => ({
  default: ({
    open,
    initialSelectedPaths,
    archive,
  }: {
    open: boolean
    initialSelectedPaths?: string[]
    archive?: { name?: string } | null
  }) =>
    open ? (
      <div>
        Wizard: {(initialSelectedPaths ?? []).join(',')} from {archive?.name}
      </div>
    ) : null,
}))

vi.mock('../../services/api', () => ({
  archivesAPI: {
    getArchive: vi.fn(),
    getChanges: vi.fn(),
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
  const parts = path.split('?')[0].split('/').filter(Boolean)
  mockParams = { repositoryId: parts[1], archiveId: parts[2] }
  renderWithProviders(<ArchiveDetail />, { initialRoute: path })
}

describe('ArchiveDetail', () => {
  beforeEach(() => {
    vi.mocked(archivesAPI.getArchive).mockReset()
    vi.mocked(archivesAPI.getChanges).mockReset()
    vi.mocked(archivesAPI.getChanges).mockResolvedValue({
      data: {
        archive_id: 12,
        compare_to_id: 11,
        changes: [],
        totals: { added: 4, removed: 2, modified: 3, summary: 0 },
        next_cursor: null,
        incomplete: false,
        unindexed_archive_ids: [],
        history_state: 'indexed',
        history_truncated: false,
      },
    } as never)
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

  it('labels the Changes tab with the totals the route returns', async () => {
    vi.mocked(archivesAPI.getArchive).mockResolvedValue({ data: archive } as never)
    renderRoute('/archives/7/12')
    expect(await screen.findByRole('tab', { name: 'Changes (+4 −2 ~3)' })).toBeInTheDocument()
  })

  it('falls back to the Changes tab for a tab the page does not have', async () => {
    vi.mocked(archivesAPI.getArchive).mockResolvedValue({ data: archive } as never)
    renderRoute('/archives/7/12?tab=unknown')
    expect(await screen.findByText('nas-2026-09-02T02:00')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /changes/i })).toHaveAttribute('aria-selected', 'true')
  })

  it('switches to the Info tab', async () => {
    vi.mocked(archivesAPI.getArchive).mockResolvedValue({ data: archive } as never)
    renderRoute('/archives/7/12')
    fireEvent.click(await screen.findByRole('tab', { name: /info/i }))
    expect((await screen.findAllByText(/nightly/)).length).toBeGreaterThan(0)
  })

  it('opens the restore wizard with the Files tab selection', async () => {
    vi.mocked(archivesAPI.getArchive).mockResolvedValue({ data: archive } as never)
    renderRoute('/archives/7/12?tab=files')
    fireEvent.click(await screen.findByRole('button', { name: /restore selection/i }))
    expect(
      await screen.findByText(/Wizard: home\/karan\/docs from nas-2026-09-02T02:00/)
    ).toBeInTheDocument()
  })

  it('restores an older version from the archive that version lives in', async () => {
    const older = {
      ...archive,
      id: 9,
      borg_id: 'older-borg-id',
      name: 'nas-2026-08-24T02:00',
      start: '2026-08-24T02:00:00Z',
    }
    vi.mocked(archivesAPI.getArchive).mockImplementation(
      (_repositoryId: number, archiveId: number) =>
        Promise.resolve({ data: archiveId === 9 ? older : archive }) as never
    )
    renderRoute('/archives/7/12?tab=files')
    fireEvent.click(await screen.findByRole('button', { name: /restore this version/i }))
    expect(
      await screen.findByText(/Wizard: home\/karan\/docs\/invoices.xlsx from nas-2026-08-24T02:00/)
    ).toBeInTheDocument()
  })

  it('reports an archive that cannot be loaded', async () => {
    vi.mocked(archivesAPI.getArchive).mockRejectedValue(new Error('nope'))
    renderRoute('/archives/7/999')
    expect(await screen.findByText(/could not be loaded/i)).toBeInTheDocument()
  })
})

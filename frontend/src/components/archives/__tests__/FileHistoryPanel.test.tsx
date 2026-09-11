import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import FileHistoryPanel from '../FileHistoryPanel'
import { archivesAPI } from '../../../services/api'

const mockPlanCan = vi.fn(() => true)

vi.mock('../../../hooks/usePlan', () => ({
  usePlan: () => ({
    plan: 'community',
    isLoading: false,
    isPro: false,
    isFree: true,
    can: mockPlanCan,
  }),
}))

vi.mock('../../../services/api', () => ({
  archivesAPI: {
    getPathHistory: vi.fn(),
    listStored: vi.fn(),
  },
}))

function renderPanel(path = 'home/karan/docs/invoices.xlsx') {
  const onRestore = vi.fn()
  renderWithProviders(<FileHistoryPanel repositoryId={7} path={path} onRestoreEntry={onRestore} />)
  return { onRestore }
}

describe('FileHistoryPanel', () => {
  beforeEach(() => {
    mockPlanCan.mockReturnValue(true)
    vi.mocked(archivesAPI.getPathHistory).mockReset()
    vi.mocked(archivesAPI.listStored).mockReset()
    vi.mocked(archivesAPI.listStored).mockResolvedValue({
      data: {
        archives: [],
        series: [],
        sync_state: 'fresh',
        last_synced_at: null,
        history_available: true,
      },
    } as never)
  })

  it('renders one row per history entry with its size and change', async () => {
    vi.mocked(archivesAPI.getPathHistory).mockResolvedValue({
      data: {
        path: 'home/karan/docs/invoices.xlsx',
        entries: [
          {
            archive_id: 12,
            archive_name: 'nas-2026-09-02T02:00',
            series: 'nightly',
            start: '2026-09-02T02:00:00Z',
            change: 'modified',
            size_before: 374_000,
            size_after: 412_000,
            mode_changed: false,
            owner_changed: false,
          },
          {
            archive_id: 3,
            archive_name: 'nas-2026-08-24T02:00',
            series: 'nightly',
            start: '2026-08-24T02:00:00Z',
            change: 'added',
            size_before: null,
            size_after: 374_000,
            mode_changed: false,
            owner_changed: false,
          },
        ],
        present: [{ series: 'nightly', from_archive_id: 3, to_archive_id: null }],
        present_in_latest: true,
      },
    } as never)

    renderPanel()
    expect(await screen.findByText('nas-2026-09-02T02:00')).toBeInTheDocument()
    expect(screen.getByText('nas-2026-08-24T02:00')).toBeInTheDocument()
    expect(screen.getByText(/first seen/i)).toBeInTheDocument()
  })

  it('renders a not-present range from the present ranges', async () => {
    vi.mocked(archivesAPI.getPathHistory).mockResolvedValue({
      data: {
        path: 'home/karan/docs/invoices.xlsx',
        entries: [
          {
            archive_id: 12,
            archive_name: 'nas-2026-09-02T02:00',
            series: 'nightly',
            start: '2026-09-02T02:00:00Z',
            change: 'added',
            size_before: null,
            size_after: 374_000,
            mode_changed: false,
            owner_changed: false,
          },
        ],
        present: [{ series: 'nightly', from_archive_id: 12, to_archive_id: null }],
        present_in_latest: true,
        // another series of the repository is still pending; this one is
        // fully indexed, so the statement about its older archives stands
        coverage: { indexed: 4, exhausted: 0, total: 6, capability: 'available' },
      },
    } as never)
    vi.mocked(archivesAPI.listStored).mockResolvedValue({
      data: {
        archives: [
          { id: 9, name: 'a9', series: 'nightly', start: '2026-08-30T02:00:00Z' },
          { id: 10, name: 'a10', series: 'nightly', start: '2026-08-31T02:00:00Z' },
          { id: 11, name: 'a11', series: 'nightly', start: '2026-09-01T02:00:00Z' },
          {
            id: 12,
            name: 'nas-2026-09-02T02:00',
            series: 'nightly',
            start: '2026-09-02T02:00:00Z',
          },
        ].map((row) => ({ ...row, history_state: 'indexed' })),
        series: ['nightly'],
        sync_state: 'fresh',
        last_synced_at: null,
        history_available: true,
      },
    } as never)

    renderPanel()
    expect(await screen.findByText(/not present in 3 older archives/i)).toBeInTheDocument()
  })

  it('renders a restore action per entry', async () => {
    vi.mocked(archivesAPI.getPathHistory).mockResolvedValue({
      data: {
        path: 'home/karan/docs/invoices.xlsx',
        entries: [
          {
            archive_id: 12,
            archive_name: 'nas-2026-09-02T02:00',
            series: 'nightly',
            start: '2026-09-02T02:00:00Z',
            change: 'modified',
            size_before: 374_000,
            size_after: 412_000,
            mode_changed: false,
            owner_changed: false,
          },
        ],
        present: [],
        present_in_latest: true,
      },
    } as never)

    const { onRestore } = renderPanel()
    const button = await screen.findByRole('button', { name: /restore this/i })
    fireEvent.click(button)
    expect(onRestore).toHaveBeenCalledWith(expect.objectContaining({ archive_id: 12 }))
  })

  it('says history is not available for an agent repository instead of judging the path', async () => {
    vi.mocked(archivesAPI.getPathHistory).mockResolvedValue({
      data: {
        path: 'etc/hosts',
        entries: [],
        present: [],
        present_in_latest: false,
        coverage: { indexed: 0, exhausted: 0, total: 12, capability: 'agent_unsupported' },
      },
    } as never)
    renderPanel('etc/hosts')
    expect(
      await screen.findByText(/not available for repositories executed by an agent/i)
    ).toBeInTheDocument()
    expect(screen.queryByText(/no earlier archive contains this path/i)).not.toBeInTheDocument()
  })

  it('says history is not available for an agent repository even with a partial older index', async () => {
    vi.mocked(archivesAPI.getPathHistory).mockResolvedValue({
      data: {
        path: 'etc/hosts',
        entries: [],
        present: [],
        present_in_latest: false,
        coverage: { indexed: 3, exhausted: 0, total: 12, capability: 'agent_unsupported' },
      },
    } as never)
    renderPanel('etc/hosts')
    expect(
      await screen.findByText(/not available for repositories executed by an agent/i)
    ).toBeInTheDocument()
    expect(screen.queryByText(/archives indexed/i)).not.toBeInTheDocument()
  })

  it('says no archive contains the path when an agent repository has a complete older index', async () => {
    // built on the server before the move, nothing skipped since: the
    // index is complete and the path is simply absent
    vi.mocked(archivesAPI.getPathHistory).mockResolvedValue({
      data: {
        path: 'etc/hosts',
        entries: [],
        present: [],
        present_in_latest: false,
        coverage: { indexed: 12, exhausted: 0, total: 12, capability: 'agent_unsupported' },
      },
    } as never)
    renderPanel('etc/hosts')
    expect(await screen.findByText(/no earlier archive contains this path/i)).toBeInTheDocument()
    expect(screen.queryByText(/executed by an agent/i)).not.toBeInTheDocument()
  })

  it('shows the entries an agent repository indexed before it moved, with their coverage', async () => {
    vi.mocked(archivesAPI.getPathHistory).mockResolvedValue({
      data: {
        path: 'etc/hosts',
        entries: [
          {
            archive_id: 2,
            archive_name: 'nas-2026-09-02T02:00',
            series: 'nightly',
            start: '2026-09-02T02:00:00Z',
            change: 'added',
            size_before: null,
            size_after: 374_000,
            mode_changed: false,
            owner_changed: false,
          },
        ],
        present: [{ series: 'nightly', from_archive_id: 2, to_archive_id: null }],
        present_in_latest: true,
        coverage: { indexed: 3, exhausted: 0, total: 12, capability: 'agent_unsupported' },
      },
    } as never)
    // the series: three indexed on the server, nine the agent's listing skipped
    vi.mocked(archivesAPI.listStored).mockResolvedValue({
      data: {
        archives: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((id) => ({
          id,
          name: `a${id}`,
          series: 'nightly',
          start: `2026-09-${String(id).padStart(2, '0')}T02:00:00Z`,
          history_state: id <= 3 ? 'indexed' : 'skipped',
        })),
        series: ['nightly'],
        sync_state: 'fresh',
        last_synced_at: null,
        history_available: true,
      },
    } as never)
    renderPanel('etc/hosts')
    expect(await screen.findByText('nas-2026-09-02T02:00')).toBeInTheDocument()
    expect(await screen.findByText(/3 of 12 archives indexed/i)).toBeInTheDocument()
    expect(screen.queryByText(/executed by an agent/i)).not.toBeInTheDocument()
    // the one older archive is indexed, so the statement about it stands
    expect(screen.getByText(/not present in 1 older archive/i)).toBeInTheDocument()
  })

  it('keeps the repository-wide coverage when the path spans several series', async () => {
    vi.mocked(archivesAPI.getPathHistory).mockResolvedValue({
      data: {
        path: 'etc/hosts',
        entries: [
          {
            archive_id: 2,
            archive_name: 'nightly-2026-09-02',
            series: 'nightly',
            start: '2026-09-02T02:00:00Z',
            change: 'added',
            size_before: null,
            size_after: 374_000,
            mode_changed: false,
            owner_changed: false,
          },
          {
            archive_id: 5,
            archive_name: 'weekly-2026-09-06',
            series: 'weekly',
            start: '2026-09-06T02:00:00Z',
            change: 'added',
            size_before: null,
            size_after: 374_000,
            mode_changed: false,
            owner_changed: false,
          },
        ],
        present: [
          { series: 'nightly', from_archive_id: 2, to_archive_id: null },
          { series: 'weekly', from_archive_id: 5, to_archive_id: null },
        ],
        present_in_latest: true,
        coverage: { indexed: 4, exhausted: 0, total: 10, capability: 'available' },
      },
    } as never)
    renderPanel('etc/hosts')
    expect(await screen.findByText(/4 of 10 archives indexed/i)).toBeInTheDocument()
    expect(archivesAPI.listStored).not.toHaveBeenCalled()
  })

  it('says the repository could not be indexed when the executor gave up on every archive', async () => {
    vi.mocked(archivesAPI.getPathHistory).mockResolvedValue({
      data: {
        path: 'etc/hosts',
        entries: [],
        present: [],
        present_in_latest: false,
        coverage: { indexed: 0, exhausted: 5, total: 5, capability: 'available' },
      },
    } as never)
    renderPanel('etc/hosts')
    expect(await screen.findByText(/could not be indexed/i)).toBeInTheDocument()
    expect(screen.queryByText(/has not been indexed yet/i)).not.toBeInTheDocument()
  })

  it('says the repository is not indexed yet when nothing is indexed', async () => {
    vi.mocked(archivesAPI.getPathHistory).mockResolvedValue({
      data: {
        path: 'etc/hosts',
        entries: [],
        present: [],
        present_in_latest: false,
        coverage: { indexed: 0, exhausted: 0, total: 3, capability: 'available' },
      },
    } as never)
    renderPanel('etc/hosts')
    expect(await screen.findByText(/has not been indexed yet/i)).toBeInTheDocument()
    expect(screen.queryByText(/no earlier archive contains this path/i)).not.toBeInTheDocument()
  })

  it('qualifies an empty history by its partial coverage', async () => {
    vi.mocked(archivesAPI.getPathHistory).mockResolvedValue({
      data: {
        path: 'etc/hosts',
        entries: [],
        present: [],
        present_in_latest: false,
        coverage: { indexed: 2, exhausted: 0, total: 5, capability: 'available' },
      },
    } as never)
    renderPanel('etc/hosts')
    expect(
      await screen.findByText(/none of the indexed archives contains this path/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/2 of 5 archives indexed/i)).toBeInTheDocument()
    expect(screen.queryByText(/no earlier archive contains this path/i)).not.toBeInTheDocument()
  })

  it('counts older archives without the path only when those archives are indexed', async () => {
    const history = {
      path: 'home/karan/docs/invoices.xlsx',
      entries: [
        {
          archive_id: 12,
          archive_name: 'nas-2026-09-02T02:00',
          series: 'nightly',
          start: '2026-09-02T02:00:00Z',
          change: 'added',
          size_before: null,
          size_after: 374_000,
          mode_changed: false,
          owner_changed: false,
        },
      ],
      present: [{ series: 'nightly', from_archive_id: 12, to_archive_id: null }],
      present_in_latest: true,
      coverage: { indexed: 4, exhausted: 0, total: 5, capability: 'available' },
    }
    const listing = (pendingId: number) => ({
      data: {
        archives: [9, 10, 11, 12, 13].map((id) => ({
          id,
          name: `a${id}`,
          series: 'nightly',
          start: `2026-08-${10 + id}T02:00:00Z`,
          history_state: id === pendingId ? 'pending' : 'indexed',
        })),
        series: ['nightly'],
        sync_state: 'fresh',
        last_synced_at: null,
        history_available: true,
      },
    })

    // the newest archive (a backup that just landed) is pending: the older
    // ones are all indexed, so the statement about them stands
    vi.mocked(archivesAPI.getPathHistory).mockResolvedValue({ data: history } as never)
    vi.mocked(archivesAPI.listStored).mockResolvedValue(listing(13) as never)
    const first = renderWithProviders(
      <FileHistoryPanel
        repositoryId={7}
        path="home/karan/docs/invoices.xlsx"
        onRestoreEntry={vi.fn()}
      />
    )
    expect(await screen.findByText(/not present in 3 older archives/i)).toBeInTheDocument()
    first.unmount()

    // an older archive is pending: nothing can be said about the older ones
    vi.mocked(archivesAPI.listStored).mockResolvedValue(listing(10) as never)
    renderWithProviders(
      <FileHistoryPanel
        repositoryId={7}
        path="home/karan/docs/invoices.xlsx"
        onRestoreEntry={vi.fn()}
      />
    )
    expect(await screen.findByText('nas-2026-09-02T02:00')).toBeInTheDocument()
    expect(screen.queryByText(/not present in/i)).not.toBeInTheDocument()
  })

  it('keeps entries a series reset left behind instead of calling the repository unindexed', async () => {
    vi.mocked(archivesAPI.getPathHistory).mockResolvedValue({
      data: {
        path: 'etc/hosts',
        entries: [
          {
            archive_id: 12,
            archive_name: 'nas-2026-09-02T02:00',
            series: 'nightly',
            start: '2026-09-02T02:00:00Z',
            change: 'added',
            size_before: null,
            size_after: 374_000,
            mode_changed: false,
            owner_changed: false,
          },
        ],
        present: [{ series: 'nightly', from_archive_id: 12, to_archive_id: null }],
        present_in_latest: true,
        coverage: { indexed: 0, exhausted: 0, total: 4, capability: 'available' },
      },
    } as never)
    renderPanel('etc/hosts')
    expect(await screen.findByText('nas-2026-09-02T02:00')).toBeInTheDocument()
    expect(screen.queryByText(/has not been indexed yet/i)).not.toBeInTheDocument()
    expect(screen.getByText(/0 of 4 archives indexed/i)).toBeInTheDocument()
  })

  it('renders disabled when the plan lacks the feature', () => {
    mockPlanCan.mockReturnValue(false)
    renderPanel()
    expect(screen.queryByRole('button', { name: /restore this/i })).not.toBeInTheDocument()
  })
})

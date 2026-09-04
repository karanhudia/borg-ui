import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, within } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import ArchiveChangesTab from '../ArchiveChangesTab'
import { archivesAPI } from '../../../services/api'
import type { ArchiveDetailResponse } from '../../../types/archives'

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
    listStored: vi.fn(),
    getChanges: vi.fn(),
    rebuild: vi.fn(),
  },
}))

const archive: ArchiveDetailResponse = {
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
  history_state: 'indexed',
  history_indexed_at: '2026-09-02T02:20:00Z',
  history_rows: 40,
  history_truncated: false,
  first_seen_at: '2026-09-02T02:00:00Z',
  last_seen_at: '2026-09-02T02:00:00Z',
  predecessor_id: 11,
  successor_id: null,
  history_available: true,
}

const changeRows = [
  {
    path: 'home/karan/docs/invoices.xlsx',
    change: 'modified' as const,
    size_before: 374_000,
    size_after: 412_000,
    mode_changed: false,
    owner_changed: false,
    summary_count: null,
  },
]

function baseChangesResponse(overrides: Record<string, unknown> = {}) {
  return {
    archive_id: 12,
    compare_to_id: 11,
    changes: changeRows,
    totals: { added: 0, removed: 0, modified: 1, summary: 0 },
    next_cursor: null,
    incomplete: false,
    unindexed_archive_ids: [],
    history_state: 'indexed' as const,
    history_truncated: false,
    ...overrides,
  }
}

function renderTab() {
  renderWithProviders(<ArchiveChangesTab repositoryId={7} archive={archive} />)
}

describe('ArchiveChangesTab', () => {
  beforeEach(() => {
    mockPlanCan.mockReturnValue(true)
    vi.mocked(archivesAPI.listStored).mockReset()
    vi.mocked(archivesAPI.getChanges).mockReset()
    vi.mocked(archivesAPI.listStored).mockResolvedValue({
      data: {
        archives: [
          {
            id: 11,
            name: 'nas-2026-09-01T02:00',
            series: 'nightly',
            start: '2026-09-01T02:00:00Z',
          },
        ],
        series: ['nightly'],
        sync_state: 'fresh',
        last_synced_at: null,
        history_available: true,
      },
    } as never)
    vi.mocked(archivesAPI.getChanges).mockResolvedValue({ data: baseChangesResponse() } as never)
  })

  it('lists changes with their size transition', async () => {
    renderTab()
    expect(await screen.findByText('home/karan/docs/invoices.xlsx')).toBeInTheDocument()
    expect(screen.getByText(/365\.\d+ KB.*→.*402\.\d+ KB/)).toBeInTheDocument()
  })

  it('filters to a single change type when its chip is toggled', async () => {
    renderTab()
    await screen.findByText('home/karan/docs/invoices.xlsx')
    fireEvent.click(screen.getByRole('button', { name: /^added$/i }))
    await vi.waitFor(() => {
      expect(archivesAPI.getChanges).toHaveBeenCalledWith(
        7,
        12,
        expect.objectContaining({ change: ['added'] })
      )
    })
  })

  it('re-requests changes against the chosen compare target', async () => {
    renderTab()
    await screen.findByText('home/karan/docs/invoices.xlsx')
    const combo = screen.getByRole('combobox')
    fireEvent.mouseDown(combo)
    const listbox = await screen.findByRole('listbox')
    fireEvent.click(within(listbox).getByText('nas-2026-09-01T02:00'))
    await vi.waitFor(() => {
      expect(archivesAPI.getChanges).toHaveBeenCalledWith(
        7,
        12,
        expect.objectContaining({ compare_to: 11 })
      )
    })
  })

  it('explains a pending archive instead of showing an empty list', async () => {
    vi.mocked(archivesAPI.getChanges).mockResolvedValue({
      data: baseChangesResponse({ changes: [], history_state: 'pending' }),
    } as never)
    renderTab()
    expect(await screen.findByText(/has not been indexed yet/i)).toBeInTheDocument()
    expect(screen.queryByText('home/karan/docs/invoices.xlsx')).not.toBeInTheDocument()
  })

  it('warns when the index was truncated', async () => {
    vi.mocked(archivesAPI.getChanges).mockResolvedValue({
      data: baseChangesResponse({ history_truncated: true }),
    } as never)
    renderTab()
    expect(await screen.findByText(/truncated at the row cap/i)).toBeInTheDocument()
  })

  it('shows the inert preview to a plan without the feature', () => {
    mockPlanCan.mockReturnValue(false)
    renderTab()
    expect(screen.queryByText('home/karan/docs/invoices.xlsx')).not.toBeInTheDocument()
  })
})

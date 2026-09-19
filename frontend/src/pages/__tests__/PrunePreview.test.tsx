import { describe, expect, it, vi, beforeEach } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '../../test/test-utils'
import PrunePreview from '../PrunePreview'
import { operationsAPI, repositoriesAPI } from '../../services/api'
import type { PrunePreviewResponse } from '../../types/archives'

let mockParams = { repositoryId: '7' }
let mockState: unknown = null

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return {
    ...actual,
    useParams: () => mockParams,
    useLocation: () => ({ ...actual.useLocation(), state: mockState }),
  }
})

vi.mock('../../services/api', async (importOriginal) => {
  const mod = await importOriginal<typeof import('../../services/api')>()
  return {
    ...mod,
    repositoriesAPI: {
      ...mod.repositoriesAPI,
      getRepositories: vi.fn(),
      prunePreview: vi.fn(),
      pruneRetentionDefaults: vi.fn(),
      pruneRepository: vi.fn(),
      pruneComparison: vi.fn(),
      pruneComparisonRefresh: vi.fn(),
      pruneCandidatePreview: vi.fn(),
    },
    operationsAPI: { ...mod.operationsAPI, get: vi.fn() },
  }
})

function renderPage(opts: { search?: string } = {}) {
  return renderWithProviders(<PrunePreview />, {
    initialRoute: `/repositories/7/prune-preview${opts.search ?? ''}`,
  })
}

const preview: PrunePreviewResponse = {
  operation_id: 5,
  archives: [
    {
      id: 1,
      borg_id: '1',
      name: 'a1',
      series: 'nas',
      start: '2026-09-01T02:00:00',
      verdict: 'deleted',
      rule: null,
      deduplicated_size: 300,
      stats_measured_at: '2026-09-17T09:00:00',
      stale: false,
    },
    {
      id: 2,
      borg_id: '2',
      name: 'a2',
      series: 'nas',
      start: '2026-09-02T02:00:00',
      verdict: 'kept',
      rule: 'daily #1',
      deduplicated_size: 100,
      stats_measured_at: '2026-09-17T09:00:00',
      stale: false,
    },
  ],
  deleted_count: 1,
  kept_count: 1,
  freed_at_least: 300,
  partial_measure: false,
  footprint_before: 1000,
  footprint_after_at_most: 700,
  lost_files: { available: false, capability: 'plan_locked' },
  log: 'Would prune: a1',
}

describe('PrunePreview page', () => {
  beforeEach(() => {
    // call history only; the implementations below are set right after
    vi.clearAllMocks()
    mockParams = { repositoryId: '7' }
    mockState = null
    vi.mocked(operationsAPI.get).mockReset()
    vi.mocked(repositoriesAPI.getRepositories).mockResolvedValue({
      data: { repositories: [{ id: 7, name: 'nas-repo' }] },
    } as never)
    vi.mocked(repositoriesAPI.pruneRetentionDefaults).mockResolvedValue({
      data: {
        source: 'plan',
        plan_name: 'Nightly',
        keep_hourly: 0,
        keep_daily: 3,
        keep_weekly: 4,
        keep_monthly: 6,
        keep_quarterly: 0,
        keep_yearly: 1,
        keep_within: null,
      },
    } as never)
    vi.mocked(repositoriesAPI.prunePreview).mockResolvedValue({ data: preview } as never)
    vi.mocked(repositoriesAPI.pruneCandidatePreview).mockResolvedValue({ data: preview } as never)
    vi.mocked(repositoriesAPI.pruneComparison).mockResolvedValue({
      data: { computed_at: null, archive_count_at: null, stale: true, candidates: [] },
    } as never)
    // the page asks for a comparison on open; unless a test says otherwise
    // the server declines (one already running, or no rights) and the page
    // carries on with what is stored
    vi.mocked(repositoriesAPI.pruneComparisonRefresh).mockRejectedValue(new Error('declined'))
  })

  it('prefills from the plan, runs the preview and shows the numbers', async () => {
    renderWithProviders(<PrunePreview />, { initialRoute: '/repositories/7/prune-preview' })
    await waitFor(() =>
      expect(repositoriesAPI.prunePreview).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ keep_daily: 3 }),
        expect.any(String)
      )
    )
    expect(await screen.findByText(/Nightly/)).toBeInTheDocument()
    expect(screen.getByTestId('prune-preview-deleted').textContent).toContain('1')
    expect(screen.getByTestId('prune-preview-freed').textContent).toMatch(/300\.00 B/)
    expect(screen.getByTestId('prune-preview-after').textContent).toMatch(/700\.00 B/)
  })

  it('re-runs only on refresh and runs the prune with the edited retention', async () => {
    vi.mocked(repositoriesAPI.pruneRepository).mockResolvedValue({ data: { job_id: 9 } } as never)
    renderWithProviders(<PrunePreview />, { initialRoute: '/repositories/7/prune-preview' })
    await screen.findByTestId('prune-preview-deleted')
    fireEvent.change(screen.getByLabelText(/keep daily/i), { target: { value: '2' } })
    expect(repositoriesAPI.prunePreview).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: /refresh preview/i }))
    await waitFor(() =>
      expect(repositoriesAPI.prunePreview).toHaveBeenLastCalledWith(
        7,
        expect.objectContaining({ keep_daily: 2 }),
        expect.any(String)
      )
    )
    fireEvent.click(screen.getByRole('button', { name: /run prune now/i }))
    fireEvent.click(await screen.findByRole('button', { name: /confirm/i }))
    await waitFor(() =>
      expect(repositoriesAPI.pruneRepository).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ keep_daily: 2, dry_run: false })
      )
    )
  })

  it('keeps "run now" disabled while the form differs from the previewed retention', async () => {
    renderWithProviders(<PrunePreview />, { initialRoute: '/repositories/7/prune-preview' })
    await screen.findByTestId('prune-preview-deleted')
    expect(screen.getByRole('button', { name: /run prune now/i })).toBeEnabled()
    fireEvent.change(screen.getByLabelText(/keep daily/i), { target: { value: '2' } })
    expect(screen.getByRole('button', { name: /run prune now/i })).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/keep daily/i), { target: { value: '3' } })
    expect(screen.getByRole('button', { name: /run prune now/i })).toBeEnabled()
  })

  it('shows a message when the preview fails for any reason', async () => {
    vi.mocked(repositoriesAPI.prunePreview).mockRejectedValue({ response: { status: 500 } })
    renderWithProviders(<PrunePreview />, { initialRoute: '/repositories/7/prune-preview' })
    expect(await screen.findByText(/could not be built/i)).toBeInTheDocument()
  })

  it('keeps the form and refresh disabled until the defaults arrive', async () => {
    let resolveDefaults: (v: unknown) => void = () => {}
    vi.mocked(repositoriesAPI.pruneRetentionDefaults).mockReturnValue(
      new Promise((resolve) => {
        resolveDefaults = resolve
      }) as never
    )
    renderWithProviders(<PrunePreview />, { initialRoute: '/repositories/7/prune-preview' })
    expect(await screen.findByRole('button', { name: /refresh preview/i })).toBeDisabled()
    expect(screen.getByLabelText(/keep daily/i)).toBeDisabled()
    expect(repositoriesAPI.prunePreview).not.toHaveBeenCalled()
    resolveDefaults({
      data: {
        source: 'default',
        plan_name: null,
        keep_hourly: 0,
        keep_daily: 3,
        keep_weekly: 4,
        keep_monthly: 6,
        keep_quarterly: 0,
        keep_yearly: 1,
        keep_within: null,
      },
    })
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /refresh preview/i })).toBeEnabled()
    )
  })

  it('offers a retry when the defaults cannot be loaded', async () => {
    vi.mocked(repositoriesAPI.pruneRetentionDefaults).mockRejectedValue(new Error('down'))
    renderWithProviders(<PrunePreview />, { initialRoute: '/repositories/7/prune-preview' })
    expect(await screen.findByRole('button', { name: /retry/i })).toBeInTheDocument()
    expect(repositoriesAPI.prunePreview).not.toHaveBeenCalled()
  })

  it('shows the lower-bound note and no longer a cross-series caveat', async () => {
    renderWithProviders(<PrunePreview />, { initialRoute: '/repositories/7/prune-preview' })
    expect(await screen.findByText(/lower bound/i)).toBeInTheDocument()
    expect(screen.queryByText(/another series/i)).not.toBeInTheDocument()
  })

  it('drops the ceiling while the index is incomplete', async () => {
    vi.mocked(repositoriesAPI.prunePreview).mockResolvedValue({
      data: {
        ...preview,
        lost_files: {
          available: true,
          capability: 'available',
          incomplete: true,
          unindexed_archive_ids: [9],
          total_count: 1,
          total_size: 400,
          top: [],
          by_folder: [],
        },
      },
    } as never)
    renderWithProviders(<PrunePreview />, { initialRoute: '/repositories/7/prune-preview' })
    await screen.findByTestId('prune-preview-deleted')
    const freed = screen.getByTestId('prune-preview-freed').textContent
    expect(freed).toMatch(/at least 300\.00 B/)
    expect(freed).not.toMatch(/up to/)
  })

  it('bounds the freed figure with the lost-file size when the index has it', async () => {
    vi.mocked(repositoriesAPI.prunePreview).mockResolvedValue({
      data: {
        ...preview,
        lost_files: {
          available: true,
          capability: 'available',
          incomplete: false,
          total_count: 1,
          total_size: 400,
          top: [],
          by_folder: [],
        },
      },
    } as never)
    renderWithProviders(<PrunePreview />, { initialRoute: '/repositories/7/prune-preview' })
    await screen.findByTestId('prune-preview-deleted')
    const freed = screen.getByTestId('prune-preview-freed').textContent
    // storage floor from borg, file-data ceiling from the index: both shown,
    // neither subtracted from the footprint, which is measured differently
    expect(freed).toMatch(/at least 300\.00 B/)
    expect(freed).toMatch(/up to 400\.00 B/)
    expect(screen.getByTestId('prune-preview-after').textContent).toMatch(/700\.00 B/)
    expect(screen.getByText(/lower bound/i)).toBeInTheDocument()
  })

  const storedComparison = {
    computed_at: '2026-09-18T01:00:00Z',
    archive_count_at: 2,
    stale: false,
    candidates: [
      {
        key: 'current',
        label: 'Current',
        retention: {
          keep_hourly: 0,
          keep_daily: 30,
          keep_weekly: 0,
          keep_monthly: 0,
          keep_quarterly: 0,
          keep_yearly: 0,
          keep_within: null,
        },
        kept_count: 2,
        deleted_count: 0,
        freed_at_least: 0,
        lost_size: null,
        partial_measure: false,
        operation_id: 1,
        readable: true,
      },
      {
        key: 'standard',
        label: 'Standard',
        retention: {
          keep_hourly: 0,
          keep_daily: 7,
          keep_weekly: 4,
          keep_monthly: 6,
          keep_quarterly: 0,
          keep_yearly: 1,
          keep_within: null,
        },
        kept_count: 1,
        deleted_count: 1,
        freed_at_least: 100,
        lost_size: null,
        partial_measure: false,
        operation_id: 2,
        readable: true,
      },
    ],
  }

  it('reads a compared policy instead of running its dry run again', async () => {
    vi.mocked(repositoriesAPI.pruneComparison).mockResolvedValue({
      data: storedComparison,
    } as never)
    renderPage()
    await waitFor(() => expect(screen.getByText('Standard')).toBeInTheDocument())
    // the prefill here is the plan's retention, which no compared row holds
    await screen.findByTestId('prune-preview-deleted')
    const dryRuns = vi.mocked(repositoriesAPI.prunePreview).mock.calls.length
    fireEvent.click(screen.getByText('Standard'))
    await waitFor(() =>
      expect(repositoriesAPI.pruneCandidatePreview).toHaveBeenCalledWith(7, 'standard')
    )
    const reads = vi.mocked(repositoriesAPI.pruneCandidatePreview).mock.calls.length
    fireEvent.click(screen.getByText('Standard'))
    // a row seen once in this visit is already in hand
    expect(repositoriesAPI.pruneCandidatePreview).toHaveBeenCalledTimes(reads)
    // opening the row ran no dry run of its own
    expect(repositoriesAPI.prunePreview).toHaveBeenCalledTimes(dryRuns)
  })

  it('falls back to a dry run for a policy the comparison never stored', async () => {
    vi.mocked(repositoriesAPI.pruneComparison).mockResolvedValue({
      data: {
        ...storedComparison,
        candidates: storedComparison.candidates.map((c) => ({ ...c, readable: false })),
      },
    } as never)
    renderPage()
    await waitFor(() => expect(screen.getByText('Standard')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Standard'))
    await waitFor(() =>
      expect(repositoriesAPI.prunePreview).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ keep_daily: 7 }),
        expect.any(String)
      )
    )
    expect(repositoriesAPI.pruneCandidatePreview).not.toHaveBeenCalled()
  })

  it('asks for a comparison when the stored one is stale, and not when it is fresh', async () => {
    vi.mocked(repositoriesAPI.pruneComparison).mockResolvedValue({
      data: { ...storedComparison, stale: true },
    } as never)
    renderPage()
    await waitFor(() =>
      expect(repositoriesAPI.pruneComparisonRefresh).toHaveBeenCalledWith(7, true)
    )
    vi.mocked(repositoriesAPI.pruneComparisonRefresh).mockClear()
    vi.mocked(repositoriesAPI.pruneComparison).mockResolvedValue({
      data: storedComparison,
    } as never)
    renderPage()
    await waitFor(() => expect(screen.getAllByText('Standard').length).toBeGreaterThan(0))
    expect(repositoriesAPI.pruneComparisonRefresh).not.toHaveBeenCalled()
  })

  it('waits for the comparison rather than running the same policy twice', async () => {
    // the prefill is a policy the comparison is about to run: opening the
    // page must not fire its own dry run alongside it
    const stale = {
      ...storedComparison,
      stale: true,
      candidates: storedComparison.candidates.map((c) =>
        c.key === 'standard'
          ? { ...c, readable: false, retention: { ...c.retention, keep_daily: 3 } }
          : c
      ),
    }
    vi.mocked(repositoriesAPI.pruneComparison).mockResolvedValue({ data: stale } as never)
    vi.mocked(repositoriesAPI.pruneComparisonRefresh).mockResolvedValue({
      data: { operation_id: 9 },
    } as never)
    vi.mocked(operationsAPI.get).mockResolvedValue({
      data: { id: 9, status: 'running' },
    } as never)
    renderPage()
    await waitFor(() =>
      expect(repositoriesAPI.pruneComparisonRefresh).toHaveBeenCalledWith(7, true)
    )
    expect(repositoriesAPI.prunePreview).not.toHaveBeenCalled()

    // once the comparison has run it, the page reads the stored row
    vi.mocked(repositoriesAPI.pruneComparison).mockResolvedValue({
      data: {
        ...stale,
        stale: false,
        computed_at: '2026-09-19T02:00:00Z',
        candidates: stale.candidates.map((c) =>
          c.key === 'standard' ? { ...c, readable: true } : c
        ),
      },
    } as never)
    vi.mocked(operationsAPI.get).mockResolvedValue({
      data: { id: 9, status: 'completed' },
    } as never)
    await waitFor(
      () => expect(repositoriesAPI.pruneCandidatePreview).toHaveBeenCalledWith(7, 'standard'),
      { timeout: 8000 }
    )
    expect(repositoriesAPI.prunePreview).not.toHaveBeenCalled()
  }, 10000)

  it('waits even when a cached comparison still calls itself fresh', async () => {
    // the payload in hand is from an earlier visit: not stale, but its rows
    // cannot be read back. Opening must not dry-run the policy the
    // comparison is about to run.
    const unreadable = storedComparison.candidates.map((c) =>
      c.key === 'standard'
        ? { ...c, readable: false, retention: { ...c.retention, keep_daily: 3 } }
        : c
    )
    vi.mocked(repositoriesAPI.pruneComparison)
      .mockResolvedValueOnce({
        data: { ...storedComparison, stale: false, candidates: unreadable },
      } as never)
      // the refetch says what the server really thinks: a row nobody can
      // read back means the comparison has to run again
      .mockResolvedValue({
        data: { ...storedComparison, stale: true, candidates: unreadable },
      } as never)
    vi.mocked(repositoriesAPI.pruneComparisonRefresh).mockResolvedValue({
      data: { operation_id: 9 },
    } as never)
    vi.mocked(operationsAPI.get).mockResolvedValue({
      data: { id: 9, status: 'running' },
    } as never)
    renderPage()
    await waitFor(() =>
      expect(repositoriesAPI.pruneComparisonRefresh).toHaveBeenCalledWith(7, true)
    )
    expect(repositoriesAPI.prunePreview).not.toHaveBeenCalled()
  })

  it('starts from the candidate named in the query string', async () => {
    vi.mocked(repositoriesAPI.pruneComparison).mockResolvedValue({
      data: storedComparison,
    } as never)
    renderPage({ search: '?candidate=standard' })
    await waitFor(() =>
      expect(repositoriesAPI.pruneCandidatePreview).toHaveBeenCalledWith(7, 'standard')
    )
    expect(repositoriesAPI.prunePreview).not.toHaveBeenCalled()
  })

  it('compares on its own for a repository never compared, then polls until it ends', async () => {
    vi.mocked(repositoriesAPI.pruneComparison)
      .mockResolvedValueOnce({
        data: { computed_at: null, archive_count_at: null, stale: true, candidates: [] },
      } as never)
      .mockResolvedValue({ data: storedComparison } as never)
    vi.mocked(repositoriesAPI.pruneComparisonRefresh).mockResolvedValue({
      data: { operation_id: 9 },
    } as never)
    vi.mocked(operationsAPI.get)
      .mockResolvedValueOnce({ data: { id: 9, status: 'running' } } as never)
      .mockResolvedValue({ data: { id: 9, status: 'completed' } } as never)
    renderPage()
    // nothing stored, so the page asks for the comparison itself
    await waitFor(() =>
      expect(repositoriesAPI.pruneComparisonRefresh).toHaveBeenCalledWith(7, true)
    )
    expect(screen.getByText('Comparing, this runs one dry run per policy.')).toBeInTheDocument()
    await waitFor(() => expect(operationsAPI.get).toHaveBeenCalledWith(9))
    await waitFor(() => expect(screen.getByText('Standard')).toBeInTheDocument(), {
      timeout: 8000,
    })
    expect(screen.queryByText('Comparing, this runs one dry run per policy.')).toBeNull()
    // and the button is still the reader's way to ask for another one
    const button = screen.getByRole('button', { name: 'Compare now' })
    expect(button).toBeEnabled()
    fireEvent.click(button)
    await waitFor(() =>
      expect(repositoriesAPI.pruneComparisonRefresh).toHaveBeenCalledWith(7, false)
    )
  }, 10000)

  it('stops waiting when the comparison operation is skipped or fails', async () => {
    vi.mocked(repositoriesAPI.pruneComparisonRefresh).mockResolvedValue({
      data: { operation_id: 9 },
    } as never)
    vi.mocked(operationsAPI.get).mockResolvedValue({
      data: { id: 9, status: 'skipped' },
    } as never)
    renderPage()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Compare now' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Compare now' }))
    await waitFor(() => expect(operationsAPI.get).toHaveBeenCalledWith(9))
    await waitFor(() =>
      expect(screen.queryByText('Comparing, this runs one dry run per policy.')).toBeNull()
    )
    expect(screen.getByRole('button', { name: 'Compare now' })).toBeEnabled()
  })

  it('drops the pending comparison when the route moves to another repository', async () => {
    vi.mocked(repositoriesAPI.pruneComparisonRefresh).mockResolvedValue({
      data: { operation_id: 9 },
    } as never)
    vi.mocked(operationsAPI.get).mockResolvedValue({
      data: { id: 9, status: 'running' },
    } as never)
    const { rerender } = renderPage()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Compare now' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Compare now' }))
    await waitFor(() =>
      expect(screen.getByText('Comparing, this runs one dry run per policy.')).toBeInTheDocument()
    )
    mockParams = { repositoryId: '8' }
    rerender(<PrunePreview />)
    await waitFor(() =>
      expect(screen.queryByText('Comparing, this runs one dry run per policy.')).toBeNull()
    )
  })

  it('marks the stored row selected when the dialog form lists keep_within first', async () => {
    vi.mocked(repositoriesAPI.pruneComparison).mockResolvedValue({
      data: storedComparison,
    } as never)
    mockState = {
      retention: {
        keep_within: '',
        keep_hourly: 0,
        keep_daily: 7,
        keep_weekly: 4,
        keep_monthly: 6,
        keep_quarterly: 0,
        keep_yearly: 1,
      },
    }
    renderPage()
    await waitFor(() => expect(screen.getByText('Standard')).toBeInTheDocument())
    // the dialog's retention is a compared policy, so it opens as a read
    await waitFor(() =>
      expect(repositoriesAPI.pruneCandidatePreview).toHaveBeenCalledWith(7, 'standard')
    )
    await waitFor(() => expect(screen.queryByText('Editing')).toBeNull())
    expect(screen.getByText('Standard').closest('tr')).toHaveClass('Mui-selected')
  })
})

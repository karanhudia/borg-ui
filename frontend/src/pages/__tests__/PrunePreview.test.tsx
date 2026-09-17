import { describe, expect, it, vi, beforeEach } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '../../test/test-utils'
import PrunePreview from '../PrunePreview'
import { repositoriesAPI } from '../../services/api'
import type { PrunePreviewResponse } from '../../types/archives'

let mockParams = { repositoryId: '7' }

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return {
    ...actual,
    useParams: () => mockParams,
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
    },
  }
})

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
    mockParams = { repositoryId: '7' }
    vi.mocked(repositoriesAPI.getRepositories).mockResolvedValue({
      data: { repositories: [{ id: 7, name: 'nas-repo' }] },
    } as never)
    vi.mocked(repositoriesAPI.pruneRetentionDefaults).mockResolvedValue({
      data: {
        source: 'plan',
        plan_name: 'Nightly',
        keep_hourly: 0,
        keep_daily: 7,
        keep_weekly: 4,
        keep_monthly: 6,
        keep_quarterly: 0,
        keep_yearly: 1,
        keep_within: null,
      },
    } as never)
    vi.mocked(repositoriesAPI.prunePreview).mockResolvedValue({ data: preview } as never)
  })

  it('prefills from the plan, runs the preview and shows the numbers', async () => {
    renderWithProviders(<PrunePreview />, { initialRoute: '/repositories/7/prune-preview' })
    await waitFor(() =>
      expect(repositoriesAPI.prunePreview).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ keep_daily: 7 })
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
        expect.objectContaining({ keep_daily: 2 })
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

  it('shows the lower-bound and cross-series notes', async () => {
    renderWithProviders(<PrunePreview />, { initialRoute: '/repositories/7/prune-preview' })
    expect(await screen.findByText(/lower bound/i)).toBeInTheDocument()
    expect(screen.getByText(/another series/i)).toBeInTheDocument()
  })
})

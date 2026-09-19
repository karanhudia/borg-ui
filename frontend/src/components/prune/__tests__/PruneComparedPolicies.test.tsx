import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import { PruneComparedPolicies } from '../PruneComparedPolicies'
import type { PruneComparison } from '../../../types/archives'

const retention = (keep_daily: number) => ({
  keep_hourly: 0,
  keep_daily,
  keep_weekly: 4,
  keep_monthly: 6,
  keep_quarterly: 0,
  keep_yearly: 1,
  keep_within: null,
})

const comparison: PruneComparison = {
  computed_at: '2026-09-18T01:00:00Z',
  archive_count_at: 12,
  stale: false,
  candidates: [
    {
      key: 'current',
      label: 'Current',
      retention: retention(30),
      kept_count: 12,
      deleted_count: 0,
      freed_at_least: 0,
      freed: null,
      partial_measure: false,
      operation_id: 1,
    },
    {
      key: 'standard',
      label: 'Standard',
      retention: retention(7),
      kept_count: 8,
      deleted_count: 4,
      freed_at_least: 40 * 1024 ** 3,
      freed: 41 * 1024 ** 3,
      partial_measure: true,
      operation_id: 2,
    },
  ],
}

describe('PruneComparedPolicies', () => {
  it('renders one row per candidate, marks the current one, and selects on click', () => {
    const onSelect = vi.fn()
    renderWithProviders(
      <PruneComparedPolicies
        comparison={comparison}
        editing={null}
        selectedKey="current"
        pending={false}
        refreshDisabled={false}
        onSelect={onSelect}
        onRefresh={() => {}}
      />
    )
    expect(screen.getByText('Compared policies')).toBeInTheDocument()
    expect(screen.getByText('7d 4w 6m 1y')).toBeInTheDocument()
    expect(screen.getByText('30d 4w 6m 1y')).toBeInTheDocument()
    expect(screen.getByText('41.00 GB')).toBeInTheDocument()
    expect(screen.getByText(/at least 0/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Standard'))
    expect(onSelect).toHaveBeenCalledWith(comparison.candidates[1])
  })

  it('shows the editing row and the stale note', () => {
    renderWithProviders(
      <PruneComparedPolicies
        comparison={{ ...comparison, stale: true }}
        editing={{
          retention: { ...retention(3), keep_within: '' },
          kept_count: 4,
          deleted_count: 8,
          freed_at_least: 1024,
          freed: null,
        }}
        selectedKey={null}
        pending={false}
        refreshDisabled={false}
        onSelect={() => {}}
        onRefresh={() => {}}
      />
    )
    expect(screen.getByText('Editing')).toBeInTheDocument()
    expect(screen.getByText('3d 4w 6m 1y')).toBeInTheDocument()
    expect(
      screen.getByText('Numbers may have changed since the last comparison.')
    ).toBeInTheDocument()
  })

  it('offers compare now when nothing is stored, and says comparing while pending', () => {
    const onRefresh = vi.fn()
    const { rerender } = renderWithProviders(
      <PruneComparedPolicies
        comparison={{ computed_at: null, archive_count_at: null, stale: true, candidates: [] }}
        editing={null}
        selectedKey={null}
        pending={false}
        refreshDisabled={false}
        onSelect={() => {}}
        onRefresh={onRefresh}
      />
    )
    expect(screen.getByText('Not compared yet.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Compare now' }))
    expect(onRefresh).toHaveBeenCalled()
    rerender(
      <PruneComparedPolicies
        comparison={null}
        editing={null}
        selectedKey={null}
        pending={true}
        refreshDisabled={true}
        onSelect={() => {}}
        onRefresh={onRefresh}
      />
    )
    expect(screen.getByText('Comparing, this runs one dry run per policy.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Compare now' })).toBeDisabled()
  })
})

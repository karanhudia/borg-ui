import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { renderWithProviders } from '../../test/test-utils'
import { SpaceSavingsPanel } from './SpaceSavingsPanel'

const row = {
  repository_id: 3,
  repository_name: 'nas',
  candidate: 'standard',
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
  freed_at_least: 40 * 1024 ** 3,
  computed_at: '2026-09-18T01:00:00Z',
  stale: true,
}

describe('SpaceSavingsPanel', () => {
  it('renders nothing without rows', () => {
    renderWithProviders(<SpaceSavingsPanel rows={[]} onNavigate={() => {}} />)
    expect(screen.queryByText('Space you could free')).not.toBeInTheDocument()
  })
  it('links each line to the preview with the candidate preselected', () => {
    const onNavigate = vi.fn()
    renderWithProviders(<SpaceSavingsPanel rows={[row]} onNavigate={onNavigate} />)
    expect(screen.getByText('Space you could free')).toBeInTheDocument()
    expect(screen.getByText('nas')).toBeInTheDocument()
    expect(screen.getByText(/7d 4w 6m 1y/)).toBeInTheDocument()
    expect(screen.getByText('may have changed')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /nas/ }))
    expect(onNavigate).toHaveBeenCalledWith('/repositories/3/prune-preview?candidate=standard')
  })
})

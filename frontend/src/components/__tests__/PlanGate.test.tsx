import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../test/test-utils'
import PlanGate from '../PlanGate'

vi.mock('../../hooks/usePlan', () => ({ usePlan: vi.fn() }))
import { usePlan } from '../../hooks/usePlan'

describe('PlanGate', () => {
  it('renders children when plan meets requirement', () => {
    vi.mocked(usePlan).mockReturnValue({
      plan: 'pro',
      features: {},
      isLoading: false,
      can: () => true,
    })
    renderWithProviders(
      <PlanGate feature="borg_v2">
        <div>pro content</div>
      </PlanGate>
    )
    expect(screen.getByText('pro content')).toBeInTheDocument()
  })

  it('renders UpgradePrompt when plan is insufficient', () => {
    vi.mocked(usePlan).mockReturnValue({
      plan: 'community',
      features: {},
      isLoading: false,
      can: () => false,
    })
    renderWithProviders(
      <PlanGate feature="borg_v2">
        <div>pro content</div>
      </PlanGate>
    )
    expect(screen.queryByText('pro content')).not.toBeInTheDocument()
    expect(screen.getByText(/Pro feature/i)).toBeInTheDocument()
  })

  it('renders custom fallback when provided', () => {
    vi.mocked(usePlan).mockReturnValue({
      plan: 'community',
      features: {},
      isLoading: false,
      can: () => false,
    })
    renderWithProviders(
      <PlanGate feature="borg_v2" fallback={<div>custom locked</div>}>
        <div>pro content</div>
      </PlanGate>
    )
    expect(screen.getByText('custom locked')).toBeInTheDocument()
    expect(screen.queryByText('pro content')).not.toBeInTheDocument()
  })
})

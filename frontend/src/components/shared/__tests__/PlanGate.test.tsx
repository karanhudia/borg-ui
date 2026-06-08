import { beforeEach, describe, it, expect, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import PlanGate from '../PlanGate'
import { BUY_URL } from '../../../utils/externalLinks'

const { trackEventMock } = vi.hoisted(() => ({
  trackEventMock: vi.fn(),
}))

vi.mock('../../../hooks/usePlan', () => ({ usePlan: vi.fn() }))
vi.mock('../../../utils/analytics', async () => {
  const actual = await vi.importActual<typeof import('../../../utils/analytics')>(
    '../../../utils/analytics'
  )
  return {
    ...actual,
    trackEvent: trackEventMock,
  }
})
import { usePlan } from '../../../hooks/usePlan'

describe('PlanGate', () => {
  beforeEach(() => {
    trackEventMock.mockClear()
  })

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
    expect(screen.getByRole('link', { name: /upgrade at borgui.com/i })).toHaveAttribute(
      'href',
      BUY_URL
    )
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

  it('renders a dimmed preview behind the upgrade prompt without mounting children', () => {
    vi.mocked(usePlan).mockReturnValue({
      plan: 'community',
      features: {},
      isLoading: false,
      can: () => false,
    })
    const childSpy = vi.fn()
    const GatedChild = () => {
      childSpy()
      return <div>live pro content</div>
    }

    renderWithProviders(
      <PlanGate feature="remote_clients" preview={<div>preview content</div>}>
        <GatedChild />
      </PlanGate>
    )

    expect(screen.getByText('preview content')).toBeInTheDocument()
    expect(screen.getByText('preview content').closest('[inert]')).toBeInTheDocument()
    expect(screen.getByText(/Pro feature/i)).toBeInTheDocument()
    expect(screen.queryByText('live pro content')).not.toBeInTheDocument()
    expect(childSpy).not.toHaveBeenCalled()
  })

  it('tracks blocked gated renders once with feature metadata', async () => {
    vi.mocked(usePlan).mockReturnValue({
      plan: 'community',
      features: {},
      isLoading: false,
      can: () => false,
    })
    renderWithProviders(
      <PlanGate feature="borg_v2" surface="repository_wizard" operation="select_borg_version">
        <div>pro content</div>
      </PlanGate>
    )

    await waitFor(() => {
      expect(trackEventMock).toHaveBeenCalledTimes(1)
    })
    expect(trackEventMock).toHaveBeenCalledWith(
      'Plan',
      'FeatureBlocked',
      expect.objectContaining({
        feature: 'borg_v2',
        current_plan: 'community',
        required_plan: 'pro',
        allowed: false,
        surface: 'repository_wizard',
        operation: 'select_borg_version',
        gate_mode: 'upgrade_prompt',
      })
    )
  })
})

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent } from '../../test/test-utils'
import PlanInfoDrawer from '../PlanInfoDrawer'

const { track } = vi.hoisted(() => ({
  track: vi.fn(),
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    track,
    EventCategory: { PLAN: 'plan' },
  }),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { role: 'admin' },
  }),
}))

const featureMap = {
  borg_v2: 'pro',
  multi_user: 'community',
  extra_users: 'pro',
} as const

describe('PlanInfoDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows upcoming features and tracks plan selection', async () => {
    const user = userEvent.setup()

    renderWithProviders(
      <PlanInfoDrawer open={true} onClose={vi.fn()} plan="community" features={featureMap} />
    )

    expect(screen.getByText('Upcoming for Pro')).toBeInTheDocument()

    await user.click(screen.getByText('Enterprise'))

    expect(track).toHaveBeenCalledWith('plan', 'ViewPlan', { plan: 'enterprise' })
    expect(screen.getByText('Upcoming for Enterprise')).toBeInTheDocument()
  })

  it('shows features for the selected plan tier', async () => {
    const user = userEvent.setup()

    renderWithProviders(
      <PlanInfoDrawer open={true} onClose={vi.fn()} plan="community" features={featureMap} />
    )

    expect(screen.getByText('Borg v2 backups')).toBeInTheDocument()
    expect(screen.getByText('Expanded user seats')).toBeInTheDocument()

    await user.click(screen.getByText('Enterprise'))

    expect(screen.queryByText('Expanded user seats')).not.toBeInTheDocument()
  })

  it('uses the provided initial selected plan when opened', () => {
    renderWithProviders(
      <PlanInfoDrawer
        open={true}
        onClose={vi.fn()}
        plan="community"
        initialSelectedPlan="enterprise"
        features={featureMap}
      />
    )

    expect(screen.queryByText('Expanded user seats')).not.toBeInTheDocument()
    expect(screen.queryByText('Borg v2 backups')).not.toBeInTheDocument()
  })
})

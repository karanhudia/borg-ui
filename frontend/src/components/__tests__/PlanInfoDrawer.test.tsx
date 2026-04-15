import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent } from '../../test/test-utils'
import PlanInfoDrawer from '../PlanInfoDrawer'
import { BUY_URL } from '../../utils/externalLinks'

const { trackPlan } = vi.hoisted(() => ({
  trackPlan: vi.fn(),
}))

const { usePlanContentMock } = vi.hoisted(() => ({
  usePlanContentMock: vi.fn(() => ({
    features: [
      {
        id: 'borg_v2',
        plan: 'pro',
        label: 'Borg v2 beta testing',
        description:
          'Early access to Borg v2 while it is still in beta. Official stable Borg v2 support will move into Community once released.',
        availability: 'included',
      },
      {
        id: 'extra_users',
        plan: 'pro',
        label: 'Up to 10 users',
        description: 'Increase the user limit from 5 in Community to up to 10 users on Pro.',
        availability: 'included',
      },
      {
        id: 'pro_server_seats',
        plan: 'pro',
        label: 'Deployment on 3 servers',
        description: 'Use the same license key on up to 3 Borg UI servers.',
        availability: 'included',
      },
      {
        id: 'backup_reports',
        plan: 'pro',
        label: 'Backup reports',
        description: 'Generate daily, weekly, monthly, or custom backup reports.',
        availability: 'coming_soon',
      },
      {
        id: 'passkeys',
        plan: 'pro',
        label: 'Passkeys',
        description: 'Sign in with biometrics or a hardware security key instead of a password.',
        available_in: '2.0.3',
      },
      {
        id: 'totp_2fa',
        plan: 'community',
        label: 'Two-factor authentication (TOTP)',
        description: 'Secure your account with time-based one-time passwords and recovery codes.',
        available_in: '2.0.3',
      },
      {
        id: 'alerting_monitoring',
        plan: 'pro',
        label: 'Alerts and monitoring',
        description:
          'Create backup alerts and rules, for example when Downloads has not been backed up for 3 days.',
        availability: 'coming_soon',
      },
      {
        id: 'rbac',
        plan: 'enterprise',
        label: 'RBAC',
        description: 'Assign roles and granular permissions to each user account.',
        availability: 'included',
      },
      {
        id: 'enterprise_unlimited_users',
        plan: 'enterprise',
        label: 'Unlimited users',
        description: 'Remove the user-count ceiling for larger teams and segregated operations.',
        availability: 'included',
      },
      {
        id: 'centralized_management',
        plan: 'enterprise',
        label: 'Centralized backup management',
        description:
          'Monitor, control, and run backups across multiple Borg UI instances from one web interface without storing repository passphrases on backup servers.',
        availability: 'coming_soon',
      },
    ],
    isLoading: false,
  })),
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackPlan,
    EventAction: { VIEW: 'View' },
  }),
}))

vi.mock('../../hooks/usePlanContent', () => ({
  usePlanContent: () => usePlanContentMock(),
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

    expect(trackPlan).toHaveBeenCalledWith('View', {
      surface: 'plan_drawer',
      operation: 'select_plan',
      selected_plan: 'enterprise',
    })
    expect(screen.getByText('Upcoming for Enterprise')).toBeInTheDocument()
  })

  it('shows a separate versioned section when the selected plan has version-targeted features', () => {
    renderWithProviders(
      <PlanInfoDrawer open={true} onClose={vi.fn()} plan="community" features={featureMap} />
    )

    expect(screen.getByText('Upcoming for Pro')).toBeInTheDocument()
    expect(screen.getByText('Included in upcoming releases for Pro')).toBeInTheDocument()
    expect(screen.getByText('Available in 2.0.3')).toBeInTheDocument()
  })

  it('shows versioned features as upcoming when the installed version is lower', () => {
    renderWithProviders(
      <PlanInfoDrawer
        open={true}
        onClose={vi.fn()}
        plan="community"
        appVersion="2.0.2"
        features={featureMap}
      />
    )

    expect(screen.getByText('Included in upcoming releases for Pro')).toBeInTheDocument()
    expect(screen.getAllByText('Passkeys').length).toBeGreaterThan(0)
    expect(screen.getByText('Available in 2.0.3')).toBeInTheDocument()
  })

  it('treats versioned upgrade features as included when the installed version is equal or newer', () => {
    renderWithProviders(
      <PlanInfoDrawer
        open={true}
        onClose={vi.fn()}
        plan="community"
        appVersion="2.0.3"
        features={featureMap}
      />
    )

    expect(screen.getAllByText('Passkeys').length).toBeGreaterThan(0)
    expect(screen.queryByText('Available in 2.0.3')).not.toBeInTheDocument()
  })

  it('treats versioned community features as included when the installed version is equal or newer', () => {
    renderWithProviders(
      <PlanInfoDrawer
        open={true}
        onClose={vi.fn()}
        plan="pro"
        appVersion="2.0.3"
        features={featureMap}
      />
    )

    expect(screen.getByText('Two-factor authentication (TOTP)')).toBeInTheDocument()
    expect(screen.queryByText('Available in 2.0.3')).not.toBeInTheDocument()
  })

  it('shows features for the selected plan tier', async () => {
    const user = userEvent.setup()

    renderWithProviders(
      <PlanInfoDrawer open={true} onClose={vi.fn()} plan="community" features={featureMap} />
    )

    expect(screen.getByText('Borg v2 beta testing')).toBeInTheDocument()
    expect(screen.getByText('Up to 10 users')).toBeInTheDocument()
    expect(screen.getByText('Deployment on 3 servers')).toBeInTheDocument()

    await user.click(screen.getByText('Enterprise'))

    expect(screen.getByText('RBAC')).toBeInTheDocument()
    expect(screen.getByText('Unlimited users')).toBeInTheDocument()
    expect(screen.queryByText('Up to 10 users')).not.toBeInTheDocument()
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

    expect(screen.queryByText('Up to 10 users')).not.toBeInTheDocument()
    expect(screen.queryByText('Borg v2 beta testing')).not.toBeInTheDocument()
    expect(screen.getByText('RBAC')).toBeInTheDocument()
  })

  it('shows a buy link for the selected plan', async () => {
    const user = userEvent.setup()

    renderWithProviders(
      <PlanInfoDrawer open={true} onClose={vi.fn()} plan="community" features={featureMap} />
    )

    expect(screen.getByRole('link', { name: /upgrade to pro/i })).toHaveAttribute('href', BUY_URL)

    await user.click(screen.getByText('Enterprise'))

    expect(screen.getByRole('link', { name: /upgrade to enterprise/i })).toHaveAttribute(
      'href',
      BUY_URL
    )
  })
})

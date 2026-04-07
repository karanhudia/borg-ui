import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent } from '../../test/test-utils'
import PlanInfoDrawer from '../PlanInfoDrawer'

const { trackPlan } = vi.hoisted(() => ({
  trackPlan: vi.fn(),
}))

const { usePlanContentMock } = vi.hoisted(() => ({
  usePlanContentMock: vi.fn(() => ({
    features: [
      {
        id: 'borg_v2',
        plan: 'pro',
        label: 'Borg v2 backups',
        description: 'Next-generation Borg format with improved deduplication and performance',
      },
      {
        id: 'extra_users',
        plan: 'pro',
        label: 'Expanded user seats',
        description: 'Add more than 5 users, with up to 10 seats on Pro',
      },
      {
        id: 'backup_reports',
        plan: 'pro',
        label: 'Scheduled backup reports',
        description:
          'Generate daily, weekly, and monthly backup summaries with status, size, and job insights',
        available_in: '2.0.1',
      },
      {
        id: 'compliance_exports',
        plan: 'enterprise',
        label: 'Audit and compliance exports',
        description:
          'Export backup history, retention evidence, and operational records for reporting and reviews',
      },
      {
        id: 'centralized_management',
        plan: 'enterprise',
        label: 'Centralized backup management',
        description:
          'Oversee larger backup environments with stronger controls and a more consolidated workflow',
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

  it('shows roadmap version badges from the manifest', () => {
    renderWithProviders(
      <PlanInfoDrawer open={true} onClose={vi.fn()} plan="community" features={featureMap} />
    )

    expect(screen.getByText('Available in 2.0.1')).toBeInTheDocument()
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

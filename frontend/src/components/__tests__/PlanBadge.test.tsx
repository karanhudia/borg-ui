import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent } from '../../test/test-utils'
import PlanBadge from '../PlanBadge'
import type { EntitlementInfo } from '../../hooks/useSystemInfo'

function fullAccessEntitlement(expires: string): EntitlementInfo {
  return {
    status: 'active',
    access_level: 'full_access',
    is_full_access: true,
    full_access_consumed: false,
    expires_at: expires,
    starts_at: null,
    instance_id: null,
    last_refresh_at: null,
    last_refresh_error: null,
  }
}

describe('PlanBadge', () => {
  it('renders the current plan label and handles clicks', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()

    renderWithProviders(<PlanBadge plan="pro" onClick={onClick} />)

    expect(screen.getByText('Pro')).toBeInTheDocument()
    await user.click(screen.getByText('Pro'))
    expect(onClick).toHaveBeenCalledTimes(1)
  })
})

describe('PlanBadge full access countdown', () => {
  it('shows days left once the trial is inside the countdown window', () => {
    const expires = new Date(Date.now() + 5 * 24 * 60 * 60 * 1000).toISOString()
    renderWithProviders(
      <PlanBadge plan="community" entitlement={fullAccessEntitlement(expires)} onClick={() => {}} />
    )
    expect(screen.getByText(/Full Access · 5 days left/)).toBeInTheDocument()
  })

  it('shows the plain label at exactly the threshold', () => {
    const expires = new Date(Date.now() + 14 * 24 * 60 * 60 * 1000 + 60_000).toISOString()
    renderWithProviders(
      <PlanBadge plan="community" entitlement={fullAccessEntitlement(expires)} onClick={() => {}} />
    )
    expect(screen.getByText('Full Access')).toBeInTheDocument()
  })

  it('hides the countdown while the trial has plenty of time left', () => {
    const expires = new Date(Date.now() + 40 * 24 * 60 * 60 * 1000).toISOString()
    renderWithProviders(
      <PlanBadge plan="community" entitlement={fullAccessEntitlement(expires)} onClick={() => {}} />
    )
    expect(screen.getByText('Full Access')).toBeInTheDocument()
  })
})

describe('PlanBadge feature trial countdown', () => {
  it('names the feature trial and counts its days down', () => {
    // A per-feature trial runs on the Community plan, so the badge shows the
    // trial instead of the plan name (spec 2026-09-21, section 3).
    const expires = new Date(Date.now() + 9 * 24 * 60 * 60 * 1000).toISOString()
    renderWithProviders(
      <PlanBadge
        plan="community"
        onClick={vi.fn()}
        entitlement={{
          status: 'active',
          access_level: 'community',
          is_full_access: false,
          full_access_consumed: true,
          expires_at: expires,
          starts_at: null,
          instance_id: null,
          last_refresh_at: null,
          last_refresh_error: null,
          trial_features: [{ feature: 'archive_history', expires_at: expires }],
        }}
      />
    )
    expect(screen.getByText(/Pro preview · 9 days left/)).toBeInTheDocument()
  })
})

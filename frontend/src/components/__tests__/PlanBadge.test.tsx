import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent } from '../../test/test-utils'
import PlanBadge from '../PlanBadge'

describe('PlanBadge', () => {
  it('renders the current plan label and handles clicks', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()

    renderWithProviders(<PlanBadge plan="pro" onClick={onClick} />)

    expect(screen.getByText('Pro')).toBeInTheDocument()
    await user.click(screen.getByText('Pro'))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('shows full access when the entitlement overrides the plan', () => {
    renderWithProviders(
      <PlanBadge
        plan="community"
        onClick={vi.fn()}
        entitlement={{
          status: 'active',
          access_level: 'full_access',
          is_full_access: true,
          full_access_consumed: false,
          expires_at: null,
          starts_at: null,
          instance_id: 'instance-1',
          last_refresh_at: null,
          last_refresh_error: null,
        }}
      />
    )

    expect(screen.getByText('Full Access')).toBeInTheDocument()
  })
})

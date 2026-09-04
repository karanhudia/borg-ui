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
})

describe('PlanBadge full access countdown', () => {
  it('shows days left once the trial is inside the countdown window', () => {
    const expires = new Date(Date.now() + 5 * 24 * 60 * 60 * 1000).toISOString()
    renderWithProviders(
      <PlanBadge
        plan="community"
        entitlement={{ status: 'active', is_full_access: true, expires_at: expires } as never}
        onClick={() => {}}
      />
    )
    expect(screen.getByText(/Full Access · 5 days left/)).toBeInTheDocument()
  })

  it('hides the countdown while the trial has plenty of time left', () => {
    const expires = new Date(Date.now() + 40 * 24 * 60 * 60 * 1000).toISOString()
    renderWithProviders(
      <PlanBadge
        plan="community"
        entitlement={{ status: 'active', is_full_access: true, expires_at: expires } as never}
        onClick={() => {}}
      />
    )
    expect(screen.getByText('Full Access')).toBeInTheDocument()
  })
})

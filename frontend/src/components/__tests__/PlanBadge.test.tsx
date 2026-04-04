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

import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { UmamiTracker } from '../UmamiTracker'

const { trackPageViewMock, useLocationMock } = vi.hoisted(() => ({
  trackPageViewMock: vi.fn(),
  useLocationMock: vi.fn(),
}))

vi.mock('../../utils/analytics', () => ({
  trackPageView: trackPageViewMock,
}))

vi.mock('react-router-dom', () => ({
  useLocation: () => useLocationMock(),
}))

describe('UmamiTracker', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('tracks the current route including search params', () => {
    useLocationMock.mockReturnValue({ pathname: '/archives', search: '?repo=1' })

    render(<UmamiTracker />)

    expect(trackPageViewMock).toHaveBeenCalledWith('/archives?repo=1')
  })

  it('tracks again when the route changes', () => {
    useLocationMock.mockReturnValue({ pathname: '/dashboard', search: '' })
    const { rerender } = render(<UmamiTracker />)

    useLocationMock.mockReturnValue({ pathname: '/activity', search: '?status=failed' })
    rerender(<UmamiTracker />)

    expect(trackPageViewMock).toHaveBeenNthCalledWith(1, '/dashboard')
    expect(trackPageViewMock).toHaveBeenNthCalledWith(2, '/activity?status=failed')
  })
})

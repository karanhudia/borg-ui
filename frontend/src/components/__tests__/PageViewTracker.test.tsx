import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { PageViewTracker } from '../PageViewTracker'

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

describe('PageViewTracker', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('tracks the current path without search params', () => {
    useLocationMock.mockReturnValue({ pathname: '/archives', search: '?repo=1' })

    render(<PageViewTracker />)

    expect(trackPageViewMock).toHaveBeenCalledWith('/archives')
  })

  it('tracks again when the route changes', () => {
    useLocationMock.mockReturnValue({ pathname: '/dashboard', search: '' })
    const { rerender } = render(<PageViewTracker />)

    useLocationMock.mockReturnValue({ pathname: '/activity', search: '?status=failed' })
    rerender(<PageViewTracker />)

    expect(trackPageViewMock).toHaveBeenNthCalledWith(1, '/dashboard')
    expect(trackPageViewMock).toHaveBeenNthCalledWith(2, '/activity')
  })
})

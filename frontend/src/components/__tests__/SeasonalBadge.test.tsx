import { StrictMode } from 'react'
import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SeasonalBadge from '../SeasonalBadge'
import type { Announcement } from '../../types/announcements'

const badge: Announcement = {
  id: 'badge-test',
  type: 'seasonal_badge',
  emoji: '🛍️',
  effect: 'chunks',
  title: 'Black Friday',
  message: 'Happy Black Friday from Borg UI.',
  cta_label: '20% off Lite and Pro',
  cta_url: 'https://borgui.com/buy?src=test',
}

describe('SeasonalBadge', () => {
  beforeEach(() => sessionStorage.clear())

  it('links to the sale when the plan gets it', () => {
    render(<SeasonalBadge badge={badge} showSale />)
    const link = screen.getByRole('link', { name: 'Black Friday: 20% off Lite and Pro' })
    expect(link).toHaveAttribute('href', badge.cta_url)
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('is a plain festive mark without the sale', () => {
    render(<SeasonalBadge badge={badge} showSale={false} />)
    expect(screen.queryByRole('link')).toBeNull()
    expect(screen.getByRole('img', { name: 'Black Friday' })).toHaveTextContent('🛍️')
  })

  it('plays the chunk burst once per session', () => {
    const { unmount } = render(<SeasonalBadge badge={badge} showSale={false} />)
    expect(screen.queryByTestId('chunk-burst')).not.toBeNull()
    unmount()
    render(<SeasonalBadge badge={badge} showSale={false} />)
    expect(screen.queryByTestId('chunk-burst')).toBeNull()
  })

  it('ends the burst under StrictMode', () => {
    vi.useFakeTimers()
    render(
      <StrictMode>
        <SeasonalBadge badge={badge} showSale={false} />
      </StrictMode>
    )
    expect(screen.queryByTestId('chunk-burst')).not.toBeNull()
    act(() => vi.advanceTimersByTime(5000))
    expect(screen.queryByTestId('chunk-burst')).toBeNull()
    vi.useRealTimers()
  })

  it('keeps the burst for the copy that is on screen', () => {
    // Hidden drawer copy mounts first and must not spend the session burst.
    render(<SeasonalBadge badge={badge} showSale={false} active={false} />)
    expect(screen.queryByTestId('chunk-burst')).toBeNull()

    const visible = render(<SeasonalBadge badge={badge} showSale={false} active={false} />)
    expect(screen.queryByTestId('chunk-burst')).toBeNull()
    visible.rerender(<SeasonalBadge badge={badge} showSale={false} active />)
    expect(screen.getByTestId('chunk-burst')).toBeInTheDocument()
  })

  it('gives a badge swapped in mid-burst its own burst', () => {
    vi.useFakeTimers()
    const view = render(<SeasonalBadge badge={badge} showSale={false} />)
    act(() => vi.advanceTimersByTime(3000))

    // A plain badge replaces it: the old burst must not keep drawing.
    view.rerender(
      <SeasonalBadge badge={{ ...badge, id: 'plain', effect: 'none' }} showSale={false} />
    )
    expect(screen.queryByTestId('chunk-burst')).toBeNull()

    // A new chunks badge plays for its full time, not the old one's remainder.
    view.rerender(<SeasonalBadge badge={{ ...badge, id: 'next' }} showSale={false} />)
    expect(screen.getByTestId('chunk-burst')).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(2000))
    expect(screen.getByTestId('chunk-burst')).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(2500))
    expect(screen.queryByTestId('chunk-burst')).toBeNull()
    vi.useRealTimers()
  })

  it('renders nothing without a badge', () => {
    const { container } = render(<SeasonalBadge badge={null} showSale />)
    expect(container).toBeEmptyDOMElement()
  })
})

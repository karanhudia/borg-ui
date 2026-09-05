import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import RebuildMenu from '../RebuildMenu'

const mockPlanCan = vi.fn(() => true)

vi.mock('../../../hooks/usePlan', () => ({
  usePlan: () => ({
    plan: 'community',
    isLoading: false,
    isPro: false,
    isFree: true,
    can: mockPlanCan,
  }),
}))

describe('RebuildMenu', () => {
  beforeEach(() => {
    mockPlanCan.mockReturnValue(true)
  })

  it('opens the menu and calls onSelect with the chosen stage', () => {
    const onSelect = vi.fn()
    render(<RebuildMenu onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('button', { name: /rebuild/i }))
    fireEvent.click(screen.getByRole('menuitem', { name: /archives/i }))
    expect(onSelect).toHaveBeenCalledWith('archives')
  })

  it('leaves stats and archives selectable without the feature', async () => {
    mockPlanCan.mockReturnValue(false)
    const onSelect = vi.fn()
    const user = userEvent.setup()
    render(<RebuildMenu onSelect={onSelect} />)
    await user.click(screen.getByRole('button', { name: /rebuild/i }))
    await user.click(screen.getByRole('menuitem', { name: /^stats/i }))
    expect(onSelect).toHaveBeenCalledWith('stats')
  })

  it('disables the history option without the feature', async () => {
    mockPlanCan.mockReturnValue(false)
    const onSelect = vi.fn()
    const user = userEvent.setup()
    render(<RebuildMenu onSelect={onSelect} />)
    await user.click(screen.getByRole('button', { name: /rebuild/i }))
    await expect(user.click(screen.getByRole('menuitem', { name: /history/i }))).rejects.toThrow(
      /pointer-events: none/
    )
    expect(onSelect).not.toHaveBeenCalledWith('history')
  })

  it('allows the history option with the feature', async () => {
    mockPlanCan.mockReturnValue(true)
    const onSelect = vi.fn()
    const user = userEvent.setup()
    render(<RebuildMenu onSelect={onSelect} />)
    await user.click(screen.getByRole('button', { name: /rebuild/i }))
    await user.click(screen.getByRole('menuitem', { name: /history/i }))
    expect(onSelect).toHaveBeenCalledWith('history')
  })
})

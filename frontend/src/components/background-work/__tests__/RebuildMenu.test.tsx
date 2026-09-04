import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import RebuildMenu from '../RebuildMenu'

describe('RebuildMenu', () => {
  it('opens the menu and calls onSelect with the chosen stage', () => {
    const onSelect = vi.fn()
    render(<RebuildMenu onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('button', { name: /rebuild/i }))
    fireEvent.click(screen.getByRole('menuitem', { name: /archives/i }))
    expect(onSelect).toHaveBeenCalledWith('archives')
  })
})

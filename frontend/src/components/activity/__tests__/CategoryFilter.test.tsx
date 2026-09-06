import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CategoryFilter from '../CategoryFilter'

describe('CategoryFilter', () => {
  it('adds a category when its toggle is pressed', async () => {
    const onChange = vi.fn()
    render(<CategoryFilter value={[]} onChange={onChange} />)
    await userEvent.click(screen.getByRole('button', { name: /backup/i }))
    expect(onChange).toHaveBeenCalledWith(['backup'])
  })

  it('removes a category that is already selected', async () => {
    const onChange = vi.fn()
    render(<CategoryFilter value={['backup']} onChange={onChange} />)
    expect(screen.getByRole('button', { name: /backup/i })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: /backup/i }))
    expect(onChange).toHaveBeenCalledWith([])
  })

  it('offers every category in one labelled group', () => {
    render(<CategoryFilter value={[]} onChange={() => {}} />)
    const group = screen.getByRole('group', { name: /category/i })
    expect(group.querySelectorAll('button')).toHaveLength(7)
  })

  it('says that index runs are hidden while nothing is selected', () => {
    const { rerender } = render(<CategoryFilter value={[]} onChange={() => {}} />)
    expect(screen.getByText(/except index runs/i)).toBeInTheDocument()
    rerender(<CategoryFilter value={['backup']} onChange={() => {}} />)
    expect(screen.queryByText(/except index runs/i)).not.toBeInTheDocument()
  })
})

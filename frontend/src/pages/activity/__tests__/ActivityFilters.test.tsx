import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ActivityFilters } from '../ActivityFilters'

const baseProps = {
  typeFilter: 'all',
  statusFilter: 'all',
  onTypeFilterChange: vi.fn(),
  onStatusFilterChange: vi.fn(),
  categoryFilter: [],
  onCategoryFilterChange: vi.fn(),
  triggerFilter: 'all',
  onTriggerFilterChange: vi.fn(),
}

describe('ActivityFilters', () => {
  it('toggling a category chip reaches onCategoryFilterChange', async () => {
    const user = userEvent.setup()
    const onCategoryFilterChange = vi.fn()
    render(<ActivityFilters {...baseProps} onCategoryFilterChange={onCategoryFilterChange} />)

    await user.click(screen.getByRole('button', { name: /backup/i }))

    expect(onCategoryFilterChange).toHaveBeenCalledWith(['backup'])
  })

  it('toggling an already-selected category chip removes it', async () => {
    const user = userEvent.setup()
    const onCategoryFilterChange = vi.fn()
    render(
      <ActivityFilters
        {...baseProps}
        categoryFilter={['backup']}
        onCategoryFilterChange={onCategoryFilterChange}
      />
    )

    await user.click(screen.getByRole('button', { name: /backup/i }))

    expect(onCategoryFilterChange).toHaveBeenCalledWith([])
  })

  it('the Index chip is off by default', () => {
    render(<ActivityFilters {...baseProps} />)
    expect(screen.getByRole('button', { name: /index/i })).toHaveAttribute('aria-pressed', 'false')
  })

  it('choosing a trigger reaches onTriggerFilterChange', async () => {
    const user = userEvent.setup()
    const onTriggerFilterChange = vi.fn()
    render(<ActivityFilters {...baseProps} onTriggerFilterChange={onTriggerFilterChange} />)

    await user.click(screen.getByRole('combobox', { name: /Trigger/i }))
    const listbox = await screen.findByRole('listbox')
    await user.click(within(listbox).getByRole('option', { name: 'Schedule' }))

    expect(onTriggerFilterChange).toHaveBeenCalledWith('schedule')
  })
})

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import ArchivePickerMenu from '../ArchivePickerMenu'
import { formatCalendarDay } from '../../../utils/dateUtils'

const anchor = () => document.body.appendChild(document.createElement('div'))

describe('ArchivePickerMenu', () => {
  it('names the day and lists each archive with its time, name and size', () => {
    render(
      <ArchivePickerMenu
        anchorEl={anchor()}
        date="2026-09-24"
        archives={[
          { id: 1, name: 'nightly-a', start: '2026-09-24T08:31:11', size: 0 },
          { id: 2, name: 'nightly-b', start: '2026-09-24T09:13:00', size: 53 },
        ]}
        onPick={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByText(`2 archives on ${formatCalendarDay('2026-09-24')}`)).toBeInTheDocument()
    const second = screen.getByRole('menuitem', { name: /nightly-b/ })
    expect(within(second).getByText('53.00 B')).toBeInTheDocument()
    // The full name stays reachable when two lines are not enough.
    expect(second).toHaveAttribute('title', 'nightly-b')
  })

  it('hands back the archive that was picked', () => {
    const onPick = vi.fn()
    render(
      <ArchivePickerMenu
        anchorEl={anchor()}
        date="2026-09-24"
        archives={[
          { id: 1, name: 'a', start: '2026-09-24T08:31:11', size: null },
          { id: 2, name: 'b', start: '2026-09-24T09:13:00', size: null },
        ]}
        onPick={onPick}
        onClose={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('menuitem', { name: /\bb\b/ }))
    expect(onPick).toHaveBeenCalledWith(2)
  })

  it('still offers an archive the lookup knows nothing about', () => {
    const onPick = vi.fn()
    render(
      <ArchivePickerMenu
        anchorEl={anchor()}
        date="2026-09-24"
        archives={[{ id: 41 }, { id: 42 }]}
        onPick={onPick}
        onClose={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('menuitem', { name: '#42' }))
    expect(onPick).toHaveBeenCalledWith(42)
  })

  it('renders nothing without an anchor', () => {
    render(
      <ArchivePickerMenu
        anchorEl={null}
        date="2026-09-24"
        archives={[{ id: 1 }]}
        onPick={vi.fn()}
        onClose={vi.fn()}
      />
    )
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })
})

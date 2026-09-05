import { describe, it, expect, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import RebuildPanel from '../RebuildPanel'
import type { Repository } from '@/types'

const repositories = [
  { id: 1, name: 'nas', path: '/mnt/nas' },
  { id: 2, name: 'photos', path: '/mnt/photos' },
] as Repository[]

describe('RebuildPanel', () => {
  it('starts at stats so every stage is marked for rebuild', () => {
    renderWithProviders(
      <RebuildPanel repositories={repositories} historyLocked={false} onRebuild={vi.fn()} />
    )
    expect(screen.getByTestId('rebuild-stage-stats')).toHaveAttribute('data-state', 'rebuild')
    expect(screen.getByTestId('rebuild-stage-history')).toHaveAttribute('data-state', 'rebuild')
    expect(screen.getByText(/rebuild everything for nas/i)).toBeInTheDocument()
  })

  it('keeps earlier stages when a later one is chosen and says so', () => {
    const onRebuild = vi.fn()
    renderWithProviders(
      <RebuildPanel repositories={repositories} historyLocked={false} onRebuild={onRebuild} />
    )
    fireEvent.click(screen.getByTestId('rebuild-stage-archives'))
    expect(screen.getByTestId('rebuild-stage-stats')).toHaveAttribute('data-state', 'kept')
    expect(screen.getByText(/rebuild archive list and file history for nas/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^rebuild$/i }))
    expect(onRebuild).toHaveBeenCalledWith(1, 'archives')
  })

  it('locks the history stage on Community and leaves it out of the summary', () => {
    renderWithProviders(
      <RebuildPanel repositories={repositories} historyLocked onRebuild={vi.fn()} />
    )
    const history = screen.getByTestId('rebuild-stage-history')
    expect(history).toHaveAttribute('data-state', 'locked')
    fireEvent.click(history)
    expect(screen.getByTestId('rebuild-stage-stats')).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(screen.getByTestId('rebuild-stage-archives'))
    expect(screen.getByText(/rebuild archive list for nas/i)).toBeInTheDocument()
  })
})

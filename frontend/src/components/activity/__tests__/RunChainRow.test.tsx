import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import RunChainRow from '../RunChainRow'

function followup(kind: string, status: string) {
  return { kind, status, followups: [] }
}

describe('RunChainRow', () => {
  it('renders nothing when the operation has no follow-ups', () => {
    const { container } = render(
      <RunChainRow operation={{ kind: 'backup', status: 'completed', followups: [] }} />
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('renders one entry per follow-up with a status tick', () => {
    render(
      <RunChainRow
        operation={{
          kind: 'backup',
          status: 'completed',
          followups: [followup('archive_sync', 'completed'), followup('stats', 'completed')],
        }}
      />
    )
    expect(screen.getByText('archive sync')).toBeInTheDocument()
    expect(screen.getByText('stats')).toBeInTheDocument()
    const entries = screen.getAllByTestId('run-chain-followup')
    expect(entries).toHaveLength(2)
    expect(entries[0]).toHaveAttribute('data-status', 'completed')
  })

  it('renders a progress fragment for a running follow-up', () => {
    render(
      <RunChainRow
        operation={{
          kind: 'backup',
          status: 'running',
          followups: [
            {
              kind: 'history_index',
              status: 'running',
              progress_current: 14,
              progress_total: 38,
              followups: [],
            },
          ],
        }}
      />
    )
    expect(screen.getByText('14/38')).toBeInTheDocument()
  })

  it('collapses to "N follow-ups" past three and expands on click', () => {
    render(
      <RunChainRow
        operation={{
          kind: 'backup',
          status: 'completed',
          followups: [
            followup('archive_sync', 'completed'),
            followup('history_index', 'completed'),
            followup('stats', 'completed'),
            followup('history_merge', 'completed'),
          ],
        }}
      />
    )
    expect(screen.getByText('4 follow-ups')).toBeInTheDocument()
    expect(screen.queryAllByTestId('run-chain-followup')).toHaveLength(0)

    fireEvent.click(screen.getByText('4 follow-ups'))
    expect(screen.getAllByTestId('run-chain-followup')).toHaveLength(4)
  })

  it('renders no action buttons', () => {
    render(
      <RunChainRow
        operation={{
          kind: 'backup',
          status: 'completed',
          followups: [followup('archive_sync', 'completed')],
        }}
      />
    )
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })
})

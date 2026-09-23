import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import StageStrip from '../StageStrip'
import { emptyCounts, type StageCounts } from '../hubRows'
import type { PausableStage } from '../../../types/operations'

function renderStrip(
  props: Partial<React.ComponentProps<typeof StageStrip>> & { counts?: StageCounts } = {}
) {
  const onSelect = vi.fn()
  const onTogglePause = vi.fn()
  const utils = render(
    <StageStrip
      counts={emptyCounts()}
      selected={null}
      onSelect={onSelect}
      pausedStages={[] as PausableStage[]}
      canManage
      onTogglePause={onTogglePause}
      {...props}
    />
  )
  return { ...utils, onSelect, onTogglePause }
}

describe('StageStrip', () => {
  it('shows every stage, idle ones included', () => {
    renderStrip()
    for (const label of ['Connect', 'Archive list', 'Retention preview', 'File history', 'Stats'])
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    expect(screen.getAllByText('Idle')).toHaveLength(5)
  })

  it('splits a count into running, waiting and failed', () => {
    const counts = emptyCounts()
    counts.archives = { total: 4, running: 2, waiting: 1, failed: 1 }
    renderStrip({ counts })
    const block = screen.getByRole('button', { name: 'Archive list' })
    expect(block).toHaveTextContent('4')
    expect(block).toHaveTextContent('2 running · 1 waiting · 1 failed')
    // The name stays short; the figures reach screen readers as its description.
    expect(block).toHaveAccessibleDescription('4 2 running · 1 waiting · 1 failed')
  })

  it('selects a block, and a second click clears it', () => {
    const { onSelect, rerender } = renderStrip()
    fireEvent.click(screen.getByRole('button', { name: 'Archive list' }))
    expect(onSelect).toHaveBeenCalledWith('archives')
    rerender(
      <StageStrip
        counts={emptyCounts()}
        selected="archives"
        onSelect={onSelect}
        pausedStages={[]}
        canManage
        onTogglePause={vi.fn()}
      />
    )
    const block = screen.getByRole('button', { name: 'Archive list' })
    expect(block).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(block)
    expect(onSelect).toHaveBeenLastCalledWith(null)
  })

  it('pauses and resumes a stage, never connect', () => {
    const { onTogglePause } = renderStrip({ pausedStages: ['history'] })
    expect(screen.queryByRole('button', { name: 'Pause Connect' })).toBeNull()
    expect(screen.getByRole('button', { name: 'File history' })).toHaveAccessibleDescription(
      /paused/i
    )
    fireEvent.click(screen.getByRole('button', { name: 'Resume File history' }))
    expect(onTogglePause).toHaveBeenCalledWith('history', false)
    fireEvent.click(screen.getByRole('button', { name: 'Pause Stats' }))
    expect(onTogglePause).toHaveBeenCalledWith('stats', true)
    expect(screen.getByText('Paused')).toBeInTheDocument()
  })

  it('shows the paused state without controls to operators', () => {
    renderStrip({ pausedStages: ['history'], canManage: false })
    expect(screen.queryByRole('button', { name: /^(Pause|Resume) / })).toBeNull()
    expect(screen.getByText('Paused')).toBeInTheDocument()
  })
})

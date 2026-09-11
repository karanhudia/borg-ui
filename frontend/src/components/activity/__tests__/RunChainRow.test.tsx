import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import RunChainRow, { type RunChainOperation } from '../RunChainRow'
import { buildFlow, buildLanes } from '../runChainLanes'

function followup(kind: string, status: string, extra: Partial<RunChainOperation> = {}) {
  return { kind, status, trigger: 'followup', ...extra }
}

const flowRoles = () =>
  [...screen.getByTestId('run-chain-flow').querySelectorAll('[data-role]')].map((node) => [
    node.getAttribute('data-role'),
    node.textContent,
  ])

describe('RunChainRow', () => {
  it('renders nothing when the operation has no follow-ups', () => {
    const { container } = render(
      <RunChainRow operation={{ kind: 'backup', status: 'completed', followups: [] }} />
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('folds a chain whose steps all succeeded and expands it on click', () => {
    render(
      <RunChainRow
        operation={{
          kind: 'backup',
          status: 'completed',
          followups: [followup('archive_sync', 'completed'), followup('stats', 'completed')],
        }}
      />
    )
    expect(screen.getByText('2 steps')).toBeInTheDocument()
    expect(screen.getByText('All succeeded')).toBeInTheDocument()
    expect(screen.queryAllByTestId('run-chain-followup')).toHaveLength(0)

    fireEvent.click(screen.getByRole('button', { expanded: false }))
    expect(screen.getByText('Sync archive list')).toBeInTheDocument()
    expect(screen.getByText('Refresh stats')).toBeInTheDocument()
    const entries = screen.getAllByTestId('run-chain-followup')
    expect(entries).toHaveLength(2)
    expect(entries[0]).toHaveAttribute('data-status', 'completed')
    // The run itself opens the flow, so the steps read as what came after it.
    expect(screen.getByTestId('run-chain-root')).toHaveTextContent('Backup')
  })

  it('stays open with a progress fragment while a step runs', () => {
    render(
      <RunChainRow
        operation={{
          kind: 'backup',
          status: 'running',
          followups: [
            followup('history_index', 'running', { progress_current: 14, progress_total: 38 }),
          ],
        }}
      />
    )
    expect(screen.getByText('14/38')).toBeInTheDocument()
    expect(screen.getByText('1 in progress')).toBeInTheDocument()
  })

  it('stays open and counts failures when a step failed', () => {
    render(
      <RunChainRow
        operation={{
          kind: 'backup',
          status: 'completed',
          followups: [followup('archive_sync', 'completed'), followup('stats', 'failed')],
        }}
      />
    )
    expect(screen.getAllByTestId('run-chain-followup')).toHaveLength(2)
    expect(screen.getByText('1 failed')).toBeInTheDocument()
  })

  it('uses the singular for one step', () => {
    render(
      <RunChainRow
        operation={{
          kind: 'backup',
          status: 'completed',
          followups: [followup('archive_sync', 'completed')],
        }}
      />
    )
    expect(screen.getByText('1 step')).toBeInTheDocument()
  })

  it('has no controls beyond the toggle', () => {
    render(
      <RunChainRow
        operation={{
          kind: 'backup',
          status: 'completed',
          followups: [followup('archive_sync', 'completed')],
        }}
      />
    )
    expect(screen.getAllByRole('button')).toHaveLength(1)
  })

  it('toggles from the keyboard', async () => {
    const user = userEvent.setup()
    render(
      <RunChainRow
        operation={{
          kind: 'backup',
          status: 'completed',
          followups: [followup('archive_sync', 'completed'), followup('stats', 'completed')],
        }}
      />
    )
    await user.tab()
    expect(screen.getByRole('button', { name: /2 steps/ })).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(screen.getAllByTestId('run-chain-followup')).toHaveLength(2)
    await user.keyboard('{Enter}')
    expect(screen.queryAllByTestId('run-chain-followup')).toHaveLength(0)
  })

  it('reads as one journey: hooks, the run, stages, then the refresh', () => {
    render(
      <RunChainRow
        operation={{
          id: 1,
          kind: 'backup',
          status: 'completed',
          label: 'Backup',
          followups: [
            { id: 2, kind: 'prune', status: 'completed', trigger: 'plan', depends_on_id: 1 },
            { id: 3, kind: 'compact', status: 'completed', trigger: 'plan', depends_on_id: 1 },
            followup('archive_sync', 'completed', { id: 4, depends_on_id: 3 }),
            followup('stats', 'completed', { id: 5, depends_on_id: 4 }),
            {
              id: 91,
              kind: 'script_execution',
              type: 'script_execution',
              hook_type: 'post-backup',
              name: 'Notify',
              status: 'completed',
              trigger: 'plan',
            },
            {
              id: 90,
              kind: 'script_execution',
              type: 'script_execution',
              hook_type: 'pre-backup',
              name: 'Mount',
              status: 'completed',
              trigger: 'plan',
            },
          ],
        }}
      />
    )
    fireEvent.click(screen.getByRole('button'))
    expect(flowRoles()).toEqual([
      ['hook', 'Pre-backup scriptMount'],
      ['root', 'Backup'],
      ['hook', 'Post-backup scriptNotify'],
      ['stage', 'Prune'],
      ['stage', 'Compact'],
      ['step', 'Sync archive list'],
      ['step', 'Refresh stats'],
    ])
    expect(
      within(screen.getByTestId('run-chain-flow')).getAllByTestId('run-chain-followup')
    ).toHaveLength(6)
  })
})

describe('buildLanes', () => {
  it('rides each follow-up under the nearest stage above it', () => {
    const lanes = buildLanes([
      { id: 2, kind: 'prune', status: 'completed', trigger: 'manual', depends_on_id: 1 },
      followup('archive_sync', 'completed', { id: 3, depends_on_id: 1 }),
      followup('history_merge', 'completed', { id: 4, depends_on_id: 3 }),
      followup('archive_sync', 'completed', { id: 5, depends_on_id: 2 }),
      followup('stats', 'completed', { id: 6, depends_on_id: 5 }),
      { id: 7, kind: 'compact', status: 'completed', trigger: 'manual', depends_on_id: 1 },
      followup('stats', 'completed', { id: 8, depends_on_id: 7 }),
    ])
    expect(lanes.map((lane) => [lane.head?.kind ?? null, lane.steps.map((s) => s.id)])).toEqual([
      [null, [3, 4]],
      ['prune', [5, 6]],
      ['compact', [8]],
    ])
  })

  it('puts legacy steps without links under the root', () => {
    const lanes = buildLanes([
      followup('archive_sync', 'completed'),
      followup('stats', 'completed'),
    ])
    expect(lanes).toHaveLength(1)
    expect(lanes[0].head).toBeNull()
    expect(lanes[0].steps).toHaveLength(2)
  })
})

describe('buildFlow', () => {
  it('orders stages by when they started and keeps their steps behind them', () => {
    const root: RunChainOperation = { id: 1, kind: 'backup', status: 'completed' }
    const flow = buildFlow(root, [
      {
        id: 7,
        kind: 'compact',
        status: 'completed',
        trigger: 'plan',
        depends_on_id: 1,
        started_at: '2026-09-11T08:32:24Z',
      },
      followup('stats', 'completed', { id: 8, depends_on_id: 7 }),
      {
        id: 2,
        kind: 'prune',
        status: 'completed',
        trigger: 'plan',
        depends_on_id: 1,
        started_at: '2026-09-11T08:32:21Z',
      },
      followup('archive_sync', 'completed', { id: 3, depends_on_id: 1 }),
    ])
    expect(flow.map((node) => `${node.role}:${node.op.kind}`)).toEqual([
      'root:backup',
      'stage:prune',
      'stage:compact',
      'step:stats',
      'step:archive_sync',
    ])
  })

  it('does not add a root node when the run lists itself as a step', () => {
    const root: RunChainOperation = { id: 1, kind: 'archive_sync', status: 'completed' }
    const flow = buildFlow(root, [
      { id: 1, kind: 'archive_sync', status: 'completed', trigger: 'reconcile' },
      followup('stats', 'completed', { id: 2, depends_on_id: 1 }),
    ])
    expect(flow.map((node) => node.role)).toEqual(['step', 'step'])
  })
})

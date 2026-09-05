import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import RepositoryRow from '../RepositoryRow'
import type { RepositoryTrack, StageState } from '../repositoryTrack'
import type { OperationItem } from '../../../types/operations'

vi.mock('../../shared/PlanGate', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

const op = (overrides: Partial<OperationItem>): OperationItem =>
  ({
    id: 1,
    kind: 'stats',
    category: 'index',
    status: 'queued',
    repository_id: 1,
    repository: 'nas',
    started_at: null,
    progress_percent: null,
    backup_plan_name: null,
    followups: [],
    ...overrides,
  }) as OperationItem

const stage = (key: StageState['key'], overrides: Partial<StageState> = {}): StageState => ({
  key,
  status: 'idle',
  operation: null,
  reason: null,
  ...overrides,
})

const track = (overrides: Partial<RepositoryTrack> = {}): RepositoryTrack => ({
  repositoryId: 1,
  repositoryName: 'nas',
  foreground: null,
  stages: [stage('connect'), stage('stats'), stage('archives'), stage('history')],
  ...overrides,
})

function renderRow(props: Partial<React.ComponentProps<typeof RepositoryRow>> = {}) {
  const handlers = { onOpen: vi.fn(), onRetry: vi.fn(), onRebuild: vi.fn() }
  render(
    <MemoryRouter>
      <RepositoryRow track={track()} {...handlers} {...props} />
    </MemoryRouter>
  )
  return handlers
}

describe('RepositoryRow', () => {
  it('names the repository and explains a waiting stage', () => {
    renderRow({
      track: track({
        stages: [
          stage('connect', { status: 'done', operation: op({ status: 'completed' }) }),
          stage('stats', {
            status: 'running',
            operation: op({ status: 'running', started_at: new Date().toISOString() }),
          }),
          stage('archives', { status: 'waiting', operation: op({}), reason: 'queued' }),
          stage('history', { status: 'waiting', operation: op({}), reason: 'workers' }),
        ],
      }),
    })
    expect(screen.getByText('nas')).toBeInTheDocument()
    expect(screen.getByText(/waiting for an index worker/i)).toBeInTheDocument()
    expect(screen.getByText(/next in line/i)).toBeInTheDocument()
  })

  it('retries from the failed stage', () => {
    const failed = stage('archives', { status: 'failed', operation: op({ status: 'failed' }) })
    const { onRetry } = renderRow({
      track: track({ stages: [stage('connect'), stage('stats'), failed, stage('history')] }),
    })
    fireEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledWith(failed)
  })

  it('shows the foreground job with its plan and a link to the repository runs', () => {
    renderRow({
      track: track({
        foreground: op({
          kind: 'backup',
          category: 'backup',
          status: 'running',
          started_at: new Date().toISOString(),
          backup_plan_name: 'nightly',
        }),
      }),
    })
    expect(screen.getByText(/backup running/i)).toBeInTheDocument()
    expect(screen.getByText(/nightly/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /view runs/i })).toHaveAttribute(
      'href',
      '/activity?repository_id=1'
    )
  })

  it('opens the run track from the repository name', () => {
    const { onOpen } = renderRow()
    fireEvent.click(screen.getByRole('button', { name: /open the run track for nas/i }))
    expect(onOpen).toHaveBeenCalled()
  })

  it('starts a rebuild from the row menu', () => {
    const { onRebuild } = renderRow()
    fireEvent.click(screen.getByRole('button', { name: /rebuild/i }))
    fireEvent.click(screen.getByRole('menuitem', { name: /^stats$/i }))
    expect(onRebuild).toHaveBeenCalledWith('stats')
  })
})

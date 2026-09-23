import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import RepositoryDataTiles from '../RepositoryDataTiles'
import type { HubRepository } from '../../../types/operations'

const repository = (overrides: Partial<HubRepository> = {}): HubRepository => ({
  repository_id: 1,
  repository_name: 'nas',
  repository_type: 'local',
  index_mode: 'full',
  sync_state: 'fresh',
  last_synced_at: new Date(Date.now() - 12 * 60 * 1000).toISOString(),
  last_stats_at: new Date(Date.now() - 11 * 60 * 1000).toISOString(),
  last_history_at: null,
  archives: 18,
  history: { indexed: 16, pending: 0, failed: 2, skipped: 0, truncated: 1, rows: 16219 },
  ...overrides,
})

function renderTiles(props: Partial<React.ComponentProps<typeof RepositoryDataTiles>> = {}) {
  render(
    <RepositoryDataTiles
      repository={repository()}
      historyAvailable
      totalHistoryRows={32438}
      {...props}
    />
  )
  return {
    archives: screen.getByTestId('repository-data-archives'),
    history: screen.getByTestId('repository-data-history'),
    stats: screen.getByTestId('repository-data-stats'),
  }
}

describe('RepositoryDataTiles', () => {
  it('shows what each stage keeps', () => {
    const { archives, history, stats } = renderTiles()
    expect(within(archives).getByText(/18 archives/i)).toBeInTheDocument()
    expect(within(archives).getByText(/synced 12 minutes ago/i)).toBeInTheDocument()
    expect(within(history).getByText(/16 of 18 indexed/i)).toBeInTheDocument()
    expect(history).toHaveTextContent(/16,219 rows/i)
    expect(history).toHaveTextContent(/50% of all history rows/i)
    expect(history).toHaveTextContent(/2 failed/i)
    expect(history).toHaveTextContent(/1 truncated/i)
    expect(within(stats).getByText('11 minutes ago')).toBeInTheDocument()
    expect(stats).toHaveTextContent(/last refreshed/i)
  })

  it('says when nothing has been built yet', () => {
    const { archives, history, stats } = renderTiles({
      repository: repository({
        sync_state: 'never',
        last_synced_at: null,
        last_stats_at: null,
        archives: 0,
        history: { indexed: 0, pending: 0, failed: 0, skipped: 0, truncated: 0, rows: 0 },
      }),
    })
    expect(archives).toHaveTextContent(/not indexed yet/i)
    expect(history).toHaveTextContent(/no file history yet/i)
    expect(stats).toHaveTextContent(/not refreshed yet/i)
  })

  it('marks file history as a Pro feature on Community instead of showing counts', () => {
    const { history } = renderTiles({ historyAvailable: false })
    expect(history).toHaveTextContent('Pro')
    expect(history).not.toHaveTextContent(/of 18 indexed/i)
  })

  it('names the agent reason ahead of Pro, since an upgrade would not help', () => {
    const { history } = renderTiles({
      historyAvailable: false,
      repository: repository({
        history_capability: 'agent_unsupported',
        history: { indexed: 12, pending: 0, failed: 0, skipped: 6, truncated: 0, rows: 4000 },
      }),
    })
    expect(history).toHaveTextContent(/needs a capable agent/i)
    expect(history).not.toHaveTextContent('Pro')
  })

  it('reads the index mode in place of history counts (spec 6.8)', () => {
    expect(
      renderTiles({ repository: repository({ index_mode: 'archives' }) }).history
    ).toHaveTextContent(/archives only/i)
  })

  it('does not call an off repository out of date', () => {
    const { archives } = renderTiles({
      repository: repository({ index_mode: 'off', sync_state: 'stale' }),
    })
    expect(archives).not.toHaveTextContent(/out of date/i)
    expect(archives).toHaveTextContent(/not refreshed/i)
  })
})

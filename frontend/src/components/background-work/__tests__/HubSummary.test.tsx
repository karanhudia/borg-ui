import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import HubSummary from '../HubSummary'

function renderSummary(props: Partial<React.ComponentProps<typeof HubSummary>> = {}) {
  const onReconcile = vi.fn()
  const onAttention = vi.fn()
  render(
    <HubSummary
      totals={{ repositories: 19, archives: 143, history_rows: 27576, history_bytes: 4300000 }}
      lastReconcileAt={new Date(Date.now() - 12 * 60 * 1000).toISOString()}
      reconcileIntervalMinutes={60}
      canManage
      attention={{ stale: 0, never: 0, history: 0, running: 0, total: 0 }}
      onAttention={onAttention}
      onReconcile={onReconcile}
      {...props}
    />
  )
  return { onReconcile, onAttention }
}

describe('HubSummary', () => {
  it('totals the derived data across repositories', () => {
    renderSummary()
    expect(screen.getByText(/19 repositories/i)).toBeInTheDocument()
    expect(screen.getByText(/143 archives indexed/i)).toBeInTheDocument()
    expect(screen.getByText(/27,576 history rows/i)).toBeInTheDocument()
    expect(screen.getByText(/about 4\.10 MB on disk/i)).toBeInTheDocument()
  })

  it('leaves the size out when the database cannot report it', () => {
    renderSummary({
      totals: { repositories: 1, archives: 2, history_rows: 3, history_bytes: null },
    })
    expect(screen.queryByText(/on disk/i)).not.toBeInTheDocument()
  })

  it('says when reconcile last ran and how often it runs', () => {
    renderSummary()
    expect(
      screen.getByText(/reconcile runs every 60 minutes\. the last one ran 12 minutes ago/i)
    ).toBeInTheDocument()
  })

  it('says when no reconcile has run yet', () => {
    renderSummary({ lastReconcileAt: null })
    expect(screen.getByText(/no reconcile has run yet/i)).toBeInTheDocument()
  })

  it('says when automatic reconcile is turned off', () => {
    renderSummary({ reconcileIntervalMinutes: 0 })
    expect(screen.getByText(/automatic reconcile is turned off/i)).toBeInTheDocument()
  })

  it('says when nothing needs attention', () => {
    renderSummary()
    expect(screen.getByText(/nothing needs attention/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /stale/i })).not.toBeInTheDocument()
  })

  it('counts the repositories that need attention and lists each reason', () => {
    renderSummary({ attention: { stale: 3, never: 1, history: 2, running: 0, total: 5 } })
    expect(screen.getByText(/5 need attention/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /3 stale/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /1 never indexed/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /2 with failed or truncated/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /running/i })).not.toBeInTheDocument()
  })

  it('narrows the table to a reason when its count is clicked', () => {
    const { onAttention } = renderSummary({
      attention: { stale: 3, never: 0, history: 0, running: 0, total: 3 },
    })
    fireEvent.click(screen.getByRole('button', { name: /3 stale/i }))
    expect(onAttention).toHaveBeenCalledWith('stale')
  })

  it('starts a reconcile for administrators', () => {
    const { onReconcile } = renderSummary()
    fireEvent.click(screen.getByRole('button', { name: /reconcile now/i }))
    expect(onReconcile).toHaveBeenCalled()
  })

  it('disables the reconcile action for people who cannot manage the queue', () => {
    renderSummary({ canManage: false })
    expect(screen.getByRole('button', { name: /reconcile now/i })).toBeDisabled()
  })
})

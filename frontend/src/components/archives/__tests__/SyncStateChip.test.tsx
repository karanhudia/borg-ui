import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import SyncStateChip from '../SyncStateChip'

describe('SyncStateChip', () => {
  it('shows how long ago a fresh sync completed', () => {
    render(
      <SyncStateChip
        state="fresh"
        lastSyncedAt={new Date(Date.now() - 120_000).toISOString()}
        onRebuild={vi.fn()}
      />
    )
    expect(screen.getByText(/synced/i)).toBeInTheDocument()
  })

  it('offers a rebuild action when the repository was never indexed', () => {
    const onRebuild = vi.fn()
    render(<SyncStateChip state="never" lastSyncedAt={null} onRebuild={onRebuild} />)
    expect(screen.getByText(/not indexed yet/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /rebuild/i }))
    expect(onRebuild).toHaveBeenCalled()
  })

  it('shows no rebuild action while a sync is running', () => {
    render(<SyncStateChip state="syncing" lastSyncedAt={null} onRebuild={vi.fn()} />)
    expect(screen.getByText(/syncing/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /rebuild/i })).not.toBeInTheDocument()
  })
})

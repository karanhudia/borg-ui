import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import SyncStateChip from '../SyncStateChip'

describe('SyncStateChip', () => {
  it('shows how long ago a fresh sync completed', () => {
    render(
      <SyncStateChip state="fresh" lastSyncedAt={new Date(Date.now() - 120_000).toISOString()} />
    )
    expect(screen.getByText(/synced/i)).toBeInTheDocument()
  })

  it('says when the repository was never indexed', () => {
    render(<SyncStateChip state="never" lastSyncedAt={null} />)
    expect(screen.getByText(/not indexed yet/i)).toBeInTheDocument()
  })

  it('says while a sync is running', () => {
    render(<SyncStateChip state="syncing" lastSyncedAt={null} />)
    expect(screen.getByText(/syncing/i)).toBeInTheDocument()
  })
})

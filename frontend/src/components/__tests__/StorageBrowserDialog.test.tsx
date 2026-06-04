import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen } from '../../test/test-utils'
import StorageBrowserDialog from '../StorageBrowserDialog'

describe('StorageBrowserDialog', () => {
  it('does not render invalid negative item sizes as NaN undefined', () => {
    renderWithProviders(
      <StorageBrowserDialog
        open
        title="Browse prod-s3"
        currentPath="borg-ui"
        rootLabel="Root"
        closeLabel="Close"
        emptyDirectoryLabel="Empty directory"
        onClose={vi.fn()}
        onNavigate={vi.fn()}
        items={[
          {
            name: 'snapshots',
            path: 'borg-ui/snapshots',
            type: 'directory',
            size: -1,
          },
          {
            name: 'manifest.json',
            path: 'borg-ui/manifest.json',
            type: 'file',
            size: Number.NaN,
          },
        ]}
      />
    )

    expect(screen.getByText('snapshots')).toBeInTheDocument()
    expect(screen.getByText('manifest.json')).toBeInTheDocument()
    expect(screen.queryByText(/NaN undefined/i)).not.toBeInTheDocument()
  })
})

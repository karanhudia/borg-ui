import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import RcloneRemoteSelect, { type RcloneRemoteSummary } from '../RcloneRemoteSelect'

const remotes: RcloneRemoteSummary[] = [
  {
    id: 3,
    name: 'GoogleDrive',
    provider: 'drive',
    last_test_status: 'connected',
  },
  {
    id: 4,
    name: 'Backblaze',
    provider: 'b2',
    last_test_status: 'success',
  },
]

describe('RcloneRemoteSelect', () => {
  it('renders the selected remote using the shared rich row format', () => {
    render(
      <RcloneRemoteSelect
        value={3}
        onChange={vi.fn()}
        remotes={remotes}
        label="Rclone Remote"
        emptyMessage="No rclone remotes configured."
      />
    )

    const combobox = screen.getByRole('combobox', { name: /Rclone Remote/i })
    expect(combobox).toHaveTextContent('GoogleDrive')
    expect(combobox).toHaveTextContent('drive')
    expect(combobox).toHaveTextContent('connected')
  })

  it('calls onChange with the selected remote id', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(
      <RcloneRemoteSelect
        value={3}
        onChange={onChange}
        remotes={remotes}
        label="Rclone Remote"
        emptyMessage="No rclone remotes configured."
      />
    )

    await user.click(screen.getByRole('combobox', { name: /Rclone Remote/i }))
    const listbox = await screen.findByRole('listbox')
    await user.click(within(listbox).getByRole('option', { name: /Backblaze/i }))

    expect(onChange).toHaveBeenCalledWith(4)
  })

  it('renders the provided empty state when no remotes exist', () => {
    render(
      <RcloneRemoteSelect
        value=""
        onChange={vi.fn()}
        remotes={[]}
        label="Rclone Remote"
        emptyMessage="No rclone remotes configured."
      />
    )

    expect(screen.getByRole('alert')).toHaveTextContent('No rclone remotes configured.')
  })
})

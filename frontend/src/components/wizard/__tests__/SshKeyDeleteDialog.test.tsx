import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import SshKeyDeleteDialog from '../SshKeyDeleteDialog'

describe('SshKeyDeleteDialog', () => {
  it('warns how many repositories share the key before deleting', async () => {
    const onConfirm = vi.fn()
    const user = userEvent.setup()

    render(
      <SshKeyDeleteDialog
        open
        keyName="borgbase-sftp"
        repositoryCount={2}
        onClose={vi.fn()}
        onConfirm={onConfirm}
      />
    )

    expect(screen.getByText('Delete borgbase-sftp?')).toBeInTheDocument()
    expect(screen.getByText(/2 repositories use this key for cloud sync/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Delete key/i }))
    expect(onConfirm).toHaveBeenCalled()
  })

  it('says when no repository uses the key', () => {
    render(
      <SshKeyDeleteDialog
        open
        keyName="spare"
        repositoryCount={0}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />
    )

    expect(screen.getByText(/No repository uses this key/i)).toBeInTheDocument()
  })
})

import { describe, expect, it, vi } from 'vitest'
import i18n from '../../i18n'
import { renderWithProviders, screen, userEvent } from '../../test/test-utils'
import { AddKeyDialog } from './dialogs/AddKeyDialog'
import { DeleteExtraKeyDialog } from './dialogs/DeleteExtraKeyDialog'
import { EditConnectionDialog } from './dialogs/EditConnectionDialog'
import { createEditConnectionForm } from './formDefaults'
import type { SSHConnection, SSHKeySummary } from './types'
import { ExtraKeysCard } from './view/ExtraKeysCard'

const systemKey: SSHKeySummary = {
  id: 1,
  name: 'System SSH Key',
  key_type: 'ed25519',
  is_system_key: true,
  connection_count: 1,
}

const extraKey: SSHKeySummary = {
  id: 2,
  name: 'borgserver-repo1',
  key_type: 'ed25519',
  fingerprint: 'SHA256:abc123',
  public_key: 'ssh-ed25519 AAAA test',
  is_system_key: false,
  connection_count: 0,
}

const connection: SSHConnection = {
  id: 5,
  ssh_key_id: 2,
  ssh_key_name: 'borgserver-repo1',
  host: 'repo1.example',
  username: 'borg',
  port: 22,
  use_sftp_mode: true,
  use_sudo: false,
  status: 'connected',
  created_at: '2026-06-01T10:00:00.000Z',
}

describe('ExtraKeysCard', () => {
  it('lists the keys and reports add, copy and delete', async () => {
    const user = userEvent.setup()
    const onAdd = vi.fn()
    const onCopyPublicKey = vi.fn()
    const onDelete = vi.fn()
    renderWithProviders(
      <ExtraKeysCard
        keys={[extraKey]}
        onAdd={onAdd}
        onCopyPublicKey={onCopyPublicKey}
        onDelete={onDelete}
      />
    )

    expect(screen.getByText('borgserver-repo1')).toBeInTheDocument()
    expect(screen.getByText('Not used yet')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Add Key' }))
    await user.click(screen.getByRole('button', { name: /Copy public key: borgserver-repo1/ }))
    await user.click(screen.getByRole('button', { name: /Delete key: borgserver-repo1/ }))

    expect(onAdd).toHaveBeenCalledOnce()
    expect(onCopyPublicKey).toHaveBeenCalledWith(extraKey)
    expect(onDelete).toHaveBeenCalledWith(extraKey)
  })

  it('says so when there are no additional keys', () => {
    renderWithProviders(
      <ExtraKeysCard keys={[]} onAdd={vi.fn()} onCopyPublicKey={vi.fn()} onDelete={vi.fn()} />
    )
    expect(screen.getByText('No additional keys yet.')).toBeInTheDocument()
  })
})

describe('AddKeyDialog', () => {
  it('generates a key with the chosen name', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    renderWithProviders(<AddKeyDialog open onClose={vi.fn()} onSubmit={onSubmit} />)

    const submit = screen.getByRole('button', { name: 'Add Key' })
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText(/Key Name/), 'repo1')
    await user.click(submit)

    expect(onSubmit).toHaveBeenCalledWith({ mode: 'generate', name: 'repo1', key_type: 'ed25519' })
  })

  it('imports a key from a path', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    renderWithProviders(<AddKeyDialog open onClose={vi.fn()} onSubmit={onSubmit} />)

    await user.click(screen.getByRole('tab', { name: 'Import from path' }))
    await user.type(screen.getByLabelText(/Key Name/), 'borgmatic')
    await user.type(screen.getByLabelText(/Private Key Path/), '/root/.ssh/id_ed25519')
    await user.click(screen.getByRole('button', { name: 'Add Key' }))

    expect(onSubmit).toHaveBeenCalledWith({
      mode: 'import',
      name: 'borgmatic',
      private_key_path: '/root/.ssh/id_ed25519',
      public_key_path: '',
    })
  })

  it('needs a private key before pasting is allowed', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AddKeyDialog open onClose={vi.fn()} onSubmit={vi.fn()} />)

    await user.click(screen.getByRole('tab', { name: 'Paste' }))
    await user.type(screen.getByLabelText(/Key Name/), 'pasted')
    expect(screen.getByRole('button', { name: 'Add Key' })).toBeDisabled()

    await user.type(screen.getByLabelText(/^Private Key/), 'key-body')
    expect(screen.getByRole('button', { name: 'Add Key' })).toBeEnabled()
  })
})

describe('DeleteExtraKeyDialog', () => {
  it('deletes a key nothing uses', async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn()
    renderWithProviders(
      <DeleteExtraKeyDialog
        sshKey={extraKey}
        connectionsUsingKey={[]}
        onClose={vi.fn()}
        onDelete={onDelete}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(onDelete).toHaveBeenCalledOnce()
  })

  it('blocks deleting a key that connections use and names them', () => {
    renderWithProviders(
      <DeleteExtraKeyDialog
        sshKey={extraKey}
        connectionsUsingKey={[connection]}
        onClose={vi.fn()}
        onDelete={vi.fn()}
      />
    )

    expect(screen.getByText('borg@repo1.example:22')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled()
  })
})

describe('EditConnectionDialog key picker', () => {
  const renderDialog = (sshKeys: SSHKeySummary[]) =>
    renderWithProviders(
      <EditConnectionDialog
        t={i18n.t.bind(i18n)}
        open
        setOpen={vi.fn()}
        setSelectedConnection={vi.fn()}
        sshKeys={sshKeys}
        editConnectionForm={{ ...createEditConnectionForm(), ssh_key_id: 1 }}
        setEditConnectionForm={vi.fn()}
        setHostError={vi.fn()}
        pending={false}
        onUpdate={vi.fn()}
      />
    )

  it('is hidden while there is only the system key', () => {
    renderDialog([systemKey])
    expect(screen.queryByText('SSH key')).not.toBeInTheDocument()
  })

  it('shows once there is a second key', () => {
    renderDialog([systemKey, extraKey])
    expect(screen.getAllByText('SSH key').length).toBeGreaterThan(0)
    expect(
      screen.getByText(/Changing the key marks the connection as untested/)
    ).toBeInTheDocument()
  })
})

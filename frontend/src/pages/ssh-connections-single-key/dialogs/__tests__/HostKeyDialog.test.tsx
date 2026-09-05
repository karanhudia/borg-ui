import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useTranslation } from 'react-i18next'
import { HostKeyDialog } from '../HostKeyDialog'
import type { SSHHostKeyResponse } from '../../../../services/api'
import type { SSHConnection } from '../../types'

const connection: SSHConnection = {
  id: 1,
  ssh_key_id: 1,
  ssh_key_name: 'System key',
  host: 'storage.example.com',
  username: 'borg',
  port: 2222,
  use_sftp_mode: true,
  use_sudo: false,
  status: 'connected',
  created_at: '2026-01-01T00:00:00Z',
}

const hostKey = (overrides: Partial<SSHHostKeyResponse> = {}): SSHHostKeyResponse => ({
  connection_id: 1,
  host: connection.host,
  port: connection.port,
  status: 'unknown',
  trusted_fingerprint: null,
  observed_fingerprint: 'SHA256:observed',
  observed_key: 'storage.example.com ssh-ed25519 AAAA',
  ...overrides,
})

function Harness(props: {
  hostKey?: SSHHostKeyResponse | null
  loading?: boolean
  pending?: boolean
  onTrust?: () => void
  onForget?: () => void
}) {
  const { t } = useTranslation()
  return (
    <HostKeyDialog
      t={t}
      open
      onClose={vi.fn()}
      connection={connection}
      hostKey={props.hostKey}
      loading={props.loading ?? false}
      pending={props.pending ?? false}
      onTrust={props.onTrust ?? vi.fn()}
      onForget={props.onForget ?? vi.fn()}
    />
  )
}

describe('HostKeyDialog', () => {
  it('offers to trust a key that is not pinned yet', () => {
    render(<Harness hostKey={hostKey()} />)

    expect(screen.getByText('SHA256:observed')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Trust this key' })).toBeEnabled()
  })

  it('warns loudly and asks again when the key changed', () => {
    render(
      <Harness hostKey={hostKey({ status: 'changed', trusted_fingerprint: 'SHA256:pinned' })} />
    )

    expect(screen.getByTestId('host-key-changed')).toBeInTheDocument()
    expect(screen.getByText('SHA256:pinned')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Trust the new key' })).toBeInTheDocument()
  })

  it('offers only to forget a key that is already trusted', () => {
    render(
      <Harness hostKey={hostKey({ status: 'trusted', trusted_fingerprint: 'SHA256:observed' })} />
    )

    expect(screen.getByRole('button', { name: 'Forget this key' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Trust this key' })).not.toBeInTheDocument()
  })

  it('cannot trust a key it could not read', () => {
    render(
      <Harness
        hostKey={hostKey({
          status: 'unreachable',
          observed_fingerprint: null,
          observed_key: null,
        })}
      />
    )

    expect(screen.queryByRole('button', { name: 'Trust this key' })).not.toBeInTheDocument()
  })

  it('confirms the key through the trust handler', async () => {
    const user = userEvent.setup()
    const onTrust = vi.fn()
    render(<Harness hostKey={hostKey()} onTrust={onTrust} />)

    await user.click(screen.getByRole('button', { name: 'Trust this key' }))

    expect(onTrust).toHaveBeenCalledOnce()
  })

  it('shows nothing to act on while the host key is being read', () => {
    render(<Harness hostKey={null} loading />)

    expect(screen.queryByRole('button', { name: 'Trust this key' })).not.toBeInTheDocument()
  })
})

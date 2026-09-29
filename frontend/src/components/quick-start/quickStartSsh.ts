import { useQuery } from '@tanstack/react-query'

import api, { sshKeysAPI } from '../../services/api'
import type { SshConnectionSummary } from '../shared/SshConnectionSelect'

export interface NewSshMachine {
  host: string
  username: string
  port: number
  password: string
}

export class SshConnectError extends Error {}

/**
 * Installs the system SSH key on a new machine with a one-time password and
 * returns the new connection id. Generates the system key first if this
 * install has none. The password is sent once and never stored.
 */
export async function connectNewMachine(machine: NewSshMachine): Promise<number> {
  const systemKey = await sshKeysAPI.getSystemKey()
  let keyId: number | undefined = systemKey.data?.exists ? systemKey.data.ssh_key?.id : undefined
  if (!keyId) {
    const generated = await sshKeysAPI.generateSSHKey({
      name: 'Borg UI system key',
      key_type: 'ed25519',
    })
    keyId = generated.data?.ssh_key?.id
  }
  if (!keyId) throw new SshConnectError('missing system key id')

  const deployed = await sshKeysAPI.deploySSHKey(keyId, {
    host: machine.host.trim(),
    username: machine.username.trim(),
    port: machine.port,
    password: machine.password,
  })
  // Deploy answers 200 with success false when the password or host is wrong.
  const connection = deployed.data?.connection
  if (!deployed.data?.success || !connection?.id) {
    throw new SshConnectError(connection?.error_message || 'deploy failed')
  }
  return connection.id
}

export function useSshConnections(enabled = true): SshConnectionSummary[] {
  const { data } = useQuery({
    queryKey: ['ssh-connections'],
    queryFn: sshKeysAPI.getSSHConnections,
    enabled,
  })
  const connections = data?.data?.connections
  return Array.isArray(connections) ? connections : []
}

export function useSshConnection(id: number | ''): SshConnectionSummary | undefined {
  const connections = useSshConnections(id !== '')
  return connections.find((connection) => connection.id === id)
}

/**
 * Where a backup path should start on this machine: its saved default path,
 * else the folder its SSH login lands in (asked, not guessed). Undefined while
 * unknown, or when the machine does not say.
 */
export function useSshBasePath(connection: SshConnectionSummary | undefined): string | undefined {
  const config = sshBrowseConfig(connection)
  const savedPath = connection?.default_path?.replace(/\/+$/, '')
  const { data } = useQuery({
    queryKey: ['ssh-home', config],
    queryFn: () => api.get<{ path: string | null }>('/filesystem/ssh-home', { params: config }),
    enabled: Boolean(config) && !savedPath,
    staleTime: Infinity,
    retry: false,
  })
  return savedPath || data?.data?.path || undefined
}

/** What the file browser needs to list folders on a connection. */
export function sshBrowseConfig(connection: SshConnectionSummary | undefined) {
  if (!connection?.ssh_key_id) return undefined
  return {
    ssh_key_id: connection.ssh_key_id,
    host: connection.host,
    username: connection.username,
    port: connection.port,
  }
}

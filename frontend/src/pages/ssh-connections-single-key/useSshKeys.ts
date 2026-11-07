import { useQuery } from '@tanstack/react-query'
import { sshKeysAPI } from '../../services/api'
import type { SSHKeySummary } from './types'

export const SSH_KEYS_QUERY_KEY = ['ssh-keys']

/** The system key and any extra keys, system key first. */
export function useSshKeys(enabled: boolean) {
  const query = useQuery({
    queryKey: SSH_KEYS_QUERY_KEY,
    queryFn: sshKeysAPI.getSSHKeys,
    enabled,
    refetchInterval: 30000,
  })
  const keys: SSHKeySummary[] = [...(query.data?.data?.ssh_keys ?? [])].sort(
    (a, b) => Number(b.is_system_key) - Number(a.is_system_key) || a.name.localeCompare(b.name)
  )
  return { keys, isLoading: query.isLoading }
}

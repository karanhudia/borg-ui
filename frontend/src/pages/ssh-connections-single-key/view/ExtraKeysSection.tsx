import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'react-hot-toast'
import { sshKeysAPI } from '../../../services/api'
import { getApiErrorDetail } from '../../../utils/apiErrors'
import { translateBackendKey } from '../../../utils/translateBackendKey'
import { copyText } from '../../../utils/clipboard'
import { useAnalytics } from '../../../hooks/useAnalytics'
import { AddKeyDialog, type AddKeyInput } from '../dialogs/AddKeyDialog'
import { DeleteExtraKeyDialog } from '../dialogs/DeleteExtraKeyDialog'
import { SSH_KEYS_QUERY_KEY } from '../useSshKeys'
import type { SSHConnection, SSHKeySummary } from '../types'
import { ExtraKeysCard } from './ExtraKeysCard'

interface ExtraKeysSectionProps {
  /** All keys; the system key is filtered out here. */
  keys: SSHKeySummary[]
  connections: SSHConnection[]
}

function addKeyRequest(input: AddKeyInput) {
  switch (input.mode) {
    case 'generate':
      return sshKeysAPI.generateSSHKey({
        name: input.name,
        key_type: input.key_type,
        system_key: false,
      })
    case 'import':
      return sshKeysAPI.importSSHKey({
        name: input.name,
        private_key_path: input.private_key_path,
        ...(input.public_key_path ? { public_key_path: input.public_key_path } : {}),
        system_key: false,
      })
    case 'paste':
      return sshKeysAPI.createSSHKey({ name: input.name, private_key: input.private_key })
  }
}

export function ExtraKeysSection({ keys, connections }: ExtraKeysSectionProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { track, EventCategory, EventAction } = useAnalytics()
  const [addOpen, setAddOpen] = useState(false)
  const [keyToDelete, setKeyToDelete] = useState<SSHKeySummary | null>(null)

  const extraKeys = keys.filter((key) => !key.is_system_key)

  const addMutation = useMutation({
    mutationFn: addKeyRequest,
    onSuccess: async () => {
      toast.success(t('sshConnections.extraKeys.toasts.added'))
      track(EventCategory.SSH, EventAction.CREATE, { resource: 'key' })
      await queryClient.invalidateQueries({ queryKey: SSH_KEYS_QUERY_KEY })
      setAddOpen(false)
    },
    onError: (error: unknown) => {
      console.error('Failed to add SSH key:', error)
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) ||
          t('sshConnections.extraKeys.toasts.addFailed')
      )
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (keyId: number) => sshKeysAPI.deleteSSHKey(keyId),
    onSuccess: async () => {
      toast.success(t('sshConnections.toasts.keyDeleted'))
      track(EventCategory.SSH, EventAction.DELETE, { resource: 'key' })
      // The dialog stays open until the list no longer shows the key (#1197).
      await queryClient.invalidateQueries({ queryKey: SSH_KEYS_QUERY_KEY })
      setKeyToDelete(null)
    },
    onError: (error: unknown) => {
      console.error('Failed to delete SSH key:', error)
      toast.error(
        translateBackendKey(getApiErrorDetail(error)) || t('sshConnections.toasts.keyDeleteFailed')
      )
    },
  })

  const handleCopy = async (key: SSHKeySummary) => {
    if (!key.public_key) return
    if (!(await copyText(key.public_key))) {
      toast.error(t('common.errors.copyFailed'))
      return
    }
    toast.success(t('sshConnections.toasts.publicKeyCopied'))
  }

  return (
    <>
      <ExtraKeysCard
        keys={extraKeys}
        onAdd={() => setAddOpen(true)}
        onCopyPublicKey={handleCopy}
        onDelete={setKeyToDelete}
      />
      <AddKeyDialog
        open={addOpen}
        pending={addMutation.isPending}
        onClose={() => setAddOpen(false)}
        onSubmit={(input) => addMutation.mutate(input)}
      />
      <DeleteExtraKeyDialog
        sshKey={keyToDelete}
        connectionsUsingKey={connections.filter((c) => c.ssh_key_id === keyToDelete?.id)}
        pending={deleteMutation.isPending}
        onClose={() => setKeyToDelete(null)}
        onDelete={() => keyToDelete && deleteMutation.mutate(keyToDelete.id)}
      />
    </>
  )
}

import { useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Box, Button, Stack } from '@mui/material'
import { Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useMutation } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'

import ManagedAgentSelect from '../shared/ManagedAgentSelect'
import AddAgentDialog from '../../pages/managed-agents/AddAgentDialog'
import { resolveAgentServerUrl } from '../../pages/managed-agents/agentServerUrl'
import { managedAgentsAPI } from '../../services/api'
import { useManagedAgents } from './quickStartAgent'

interface QuickStartAgentConnectProps {
  value: number | ''
  onChange: (agentId: number) => void
  /** settings.ssh.manage, the permission the Managed Agents page uses. */
  canAddMachine: boolean
}

/** Pick an enrolled agent, or enroll one with the existing Add agent dialog. */
export default function QuickStartAgentConnect({
  value,
  onChange,
  canAddMachine,
}: QuickStartAgentConnectProps) {
  const { t } = useTranslation()
  const [adding, setAdding] = useState(false)
  const agents = useManagedAgents(true, adding)
  const knownIds = useRef<Set<number> | null>(null)
  const createToken = useMutation({ mutationFn: managedAgentsAPI.createEnrollmentToken })
  const serverUrl = useMemo(() => resolveAgentServerUrl(undefined, window.location.origin), [])

  // Select the agent that connects while the Add agent dialog is open.
  useEffect(() => {
    if (!adding || !knownIds.current) return
    const joined = agents.find((agent) => !knownIds.current?.has(agent.id))
    if (!joined) return
    knownIds.current.add(joined.id)
    onChange(joined.id)
  }, [adding, agents, onChange])

  const startAdding = () => {
    knownIds.current = new Set(agents.map((agent) => agent.id))
    setAdding(true)
  }

  return (
    <Stack spacing={1.5}>
      {agents.length === 0 && !canAddMachine ? (
        <Alert severity="info" variant="outlined">
          {t('quickStart.agent.noAgentsNoPermission')}
        </Alert>
      ) : (
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ alignItems: 'stretch' }}>
          {agents.length > 0 && (
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <ManagedAgentSelect
                value={value}
                onChange={onChange}
                agents={agents}
                label={t('quickStart.agent.label')}
                emptyMessage=""
                hideEmptyAlert
              />
            </Box>
          )}
          {canAddMachine && (
            <Button
              variant={agents.length > 0 ? 'outlined' : 'contained'}
              startIcon={<Plus size={16} />}
              onClick={startAdding}
              sx={{ flexShrink: 0 }}
            >
              {t('quickStart.agent.add')}
            </Button>
          )}
        </Stack>
      )}

      <AddAgentDialog
        open={adding}
        onClose={() => setAdding(false)}
        defaultServerUrl={serverUrl}
        agents={agents}
        onCreateToken={async (payload) => (await createToken.mutateAsync(payload)).data}
        creatingToken={createToken.isPending}
        onCopy={async (text) => {
          await navigator.clipboard.writeText(text)
          toast.success(t('managedAgents.page.toasts.copied'))
        }}
      />
    </Stack>
  )
}

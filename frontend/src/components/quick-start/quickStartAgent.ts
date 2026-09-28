import { useQuery } from '@tanstack/react-query'

import { managedAgentsAPI, type AgentMachineResponse } from '../../services/api'

/** Polls faster while the user is enrolling a new agent, so it appears as soon as it connects. */
export function useManagedAgents(enabled = true, watching = false): AgentMachineResponse[] {
  const { data } = useQuery({
    queryKey: ['managed-agents'],
    queryFn: managedAgentsAPI.listAgents,
    enabled,
    refetchInterval: watching ? 5000 : false,
  })
  return Array.isArray(data?.data) ? data.data : []
}

export function useManagedAgent(id: number | ''): AgentMachineResponse | undefined {
  const agents = useManagedAgents(id !== '')
  return agents.find((agent) => agent.id === id)
}

export function agentLabel(agent: Pick<AgentMachineResponse, 'name' | 'hostname'>): string {
  return agent.hostname || agent.name
}

export function suggestedAgentDestinationPath(
  name: string,
  agent: Pick<AgentMachineResponse, 'default_path'> | undefined
): string {
  const base = agent?.default_path?.replace(/\/+$/, '') || '/var/backups'
  const slug =
    name
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'backup'
  return `${base}/borg-backups/${slug}`
}

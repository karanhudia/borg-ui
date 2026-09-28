import { useQuery } from '@tanstack/react-query'

import { managedAgentsAPI, type AgentMachineResponse } from '../../services/api'
import { isInsidePath } from './quickStartState'

/**
 * Polls faster while the user is enrolling a new agent, so it appears as soon
 * as it connects.
 */
export function useManagedAgents(
  enabled = true,
  watching = false
): { agents: AgentMachineResponse[]; failed: boolean } {
  const { data, isError } = useQuery({
    queryKey: ['managed-agents'],
    queryFn: managedAgentsAPI.listAgents,
    enabled,
    refetchInterval: watching ? 5000 : false,
  })
  return { agents: Array.isArray(data?.data) ? data.data : [], failed: isError }
}

export function useManagedAgent(id: number | ''): AgentMachineResponse | undefined {
  const { agents } = useManagedAgents(id !== '')
  return agents.find((agent) => agent.id === id)
}

export function agentLabel(agent: Pick<AgentMachineResponse, 'name' | 'hostname'>): string {
  return agent.hostname || agent.name
}

/**
 * A folder on the agent for its repository, outside every source folder.
 * Empty when neither candidate is outside them, so the user picks one.
 */
export function suggestedAgentDestinationPath(
  name: string,
  agent: Pick<AgentMachineResponse, 'default_path'> | undefined,
  sourcePaths: string[]
): string {
  const slug =
    name
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'backup'
  const bases = [agent?.default_path?.replace(/\/+$/, ''), '/var/backups'].filter(Boolean)
  const candidates = bases.map((base) => `${base}/borg-backups/${slug}`)
  return (
    candidates.find(
      (candidate) => !sourcePaths.some((source) => isInsidePath(candidate, source))
    ) ?? ''
  )
}

/** The agent that enrolled with this token, once it has connected. */
export function useEnrolledAgentId(tokenId: number | null): number | null {
  const { data } = useQuery({
    queryKey: ['managed-agent-enrollment-tokens'],
    queryFn: managedAgentsAPI.listEnrollmentTokens,
    enabled: tokenId !== null,
    refetchInterval: tokenId !== null ? 5000 : false,
  })
  const tokens = Array.isArray(data?.data) ? data.data : []
  return tokens.find((token) => token.id === tokenId)?.used_by_agent_id ?? null
}

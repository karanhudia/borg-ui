import type { AgentMachineResponse } from '../../services/api'
import type { Repository, SourceLocation } from '../../types'
import type { WizardState } from './types'

export type RouteExecutor = 'server' | 'ssh' | 'agent'

export interface RepositoryRoutePreview {
  repository: Repository
  supported: boolean
  strategy: string | null
  executor: RouteExecutor
  agentMachineId: number | null
  messageKey: string | null
  messageParams: Record<string, string | number | null>
}

function cleanLocations(state: WizardState): SourceLocation[] {
  const sourceLocations = (state.sourceLocations || [])
    .map((location) => ({
      ...location,
      source_ssh_connection_id:
        location.source_type === 'remote' ? location.source_ssh_connection_id : null,
      agent_machine_id: location.source_type === 'agent' ? location.agent_machine_id : null,
      paths: location.paths.map((path) => path.trim()).filter(Boolean),
    }))
    .filter((location) => location.paths.length > 0)

  if (sourceLocations.length > 0) return sourceLocations
  if (state.sourceDirectories.length === 0) return []
  if (state.sourceType === 'remote' && state.sourceSshConnectionId) {
    return [
      {
        source_type: 'remote',
        source_ssh_connection_id: Number(state.sourceSshConnectionId),
        agent_machine_id: null,
        paths: state.sourceDirectories,
      },
    ]
  }
  return [
    {
      source_type: 'local',
      source_ssh_connection_id: null,
      agent_machine_id: null,
      paths: state.sourceDirectories,
    },
  ]
}

function agentName(agentMachines: AgentMachineResponse[], agentMachineId?: number | null) {
  const agent = agentMachines.find((item) => item.id === agentMachineId)
  return agent?.hostname || agent?.name || `Agent ${agentMachineId ?? ''}`.trim()
}

function unsupported(
  repository: Repository,
  executor: RouteExecutor,
  key: string,
  params: Record<string, string | number | null> = {}
): RepositoryRoutePreview {
  return {
    repository,
    supported: false,
    strategy: null,
    executor,
    agentMachineId: repository.agent_machine_id ?? null,
    messageKey: key,
    messageParams: params,
  }
}

export function buildRoutePreviews(
  repositories: Repository[],
  state: WizardState,
  agentMachines: AgentMachineResponse[]
): RepositoryRoutePreview[] {
  const locations = cleanLocations(state)
  const hasAgentSources = locations.some((location) => location.source_type === 'agent')
  const hasNonAgentSources = locations.some((location) => location.source_type !== 'agent')
  const firstLocation = locations[0]

  return repositories.map((repository) => {
    const isAgentRepo = repository.executor_type === 'agent'
    const agentMachineId = repository.agent_machine_id ?? null
    const executor: RouteExecutor = isAgentRepo
      ? 'agent'
      : repository.connection_id
        ? 'ssh'
        : 'server'

    if (hasAgentSources && hasNonAgentSources) {
      return unsupported(repository, executor, 'backupPlans.routePreview.mixedAgentSources')
    }

    if (isAgentRepo) {
      if (repository.connection_id) {
        return unsupported(repository, 'agent', 'backupPlans.routePreview.agentRepoSshUnsupported')
      }
      if (!firstLocation || firstLocation.source_type === 'local') {
        return unsupported(repository, 'agent', 'backupPlans.routePreview.serverToAgentRepo')
      }
      if (firstLocation.source_type === 'remote') {
        return unsupported(repository, 'agent', 'backupPlans.routePreview.sourceMustMatchAgent', {
          agent: agentName(agentMachines, agentMachineId),
        })
      }
      if (firstLocation.agent_machine_id !== agentMachineId) {
        return unsupported(repository, 'agent', 'backupPlans.routePreview.sourceMustMatchAgent', {
          agent: agentName(agentMachines, agentMachineId),
        })
      }
      return {
        repository,
        supported: true,
        strategy: 'agent_direct',
        executor: 'agent',
        agentMachineId,
        messageKey: null,
        messageParams: {},
      }
    }

    if (hasAgentSources) {
      return unsupported(repository, executor, 'backupPlans.routePreview.agentSourceToServerRepo')
    }

    if (firstLocation?.source_type === 'remote') {
      if (!repository.connection_id) {
        return {
          repository,
          supported: true,
          strategy: 'server_sshfs_pull',
          executor: 'server',
          agentMachineId: null,
          messageKey: null,
          messageParams: {},
        }
      }
      const sameRemote = repository.connection_id === firstLocation.source_ssh_connection_id
      return {
        repository,
        supported: true,
        strategy: sameRemote ? 'remote_direct' : 'server_sshfs_pull_then_borg_ssh',
        executor: sameRemote ? 'ssh' : 'server',
        agentMachineId: null,
        messageKey: null,
        messageParams: {},
      }
    }

    return {
      repository,
      supported: true,
      strategy: repository.connection_id ? 'server_direct_borg_ssh' : 'server_direct',
      executor: 'server',
      agentMachineId: null,
      messageKey: null,
      messageParams: {},
    }
  })
}

export function routeExecutorLabelKey(executor: RouteExecutor) {
  if (executor === 'agent') return 'backupPlans.routePreview.runsOnManagedAgent'
  if (executor === 'ssh') return 'backupPlans.routePreview.runsOnSshHost'
  return 'backupPlans.routePreview.runsOnServer'
}

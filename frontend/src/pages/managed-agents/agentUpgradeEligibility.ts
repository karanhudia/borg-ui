import type { AgentMachineResponse } from '../../services/api'

/**
 * The endpoints a server-driven upgrade can actually move right now.
 *
 * One predicate for the row action, the selection checkbox and the banner's
 * count, so the number in a button is always the number that will move.
 */
export const canUpgradeNow = (agent: AgentMachineResponse): boolean =>
  agent.self_upgrade_supported === true &&
  agent.upgrade_status === 'outdated' &&
  agent.upgrade_state !== 'requested' &&
  agent.upgrade_state !== 'queued'

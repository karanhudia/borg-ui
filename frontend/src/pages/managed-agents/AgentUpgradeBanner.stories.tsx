import type { Meta, StoryObj } from '@storybook/react-vite'
import AgentUpgradeBanner from './AgentUpgradeBanner'
import type { AgentMachineResponse } from '../../services/api'

const base: AgentMachineResponse = {
  id: 1,
  name: 'Production NAS',
  agent_id: 'agt_prod_nas_01',
  hostname: 'nas-01.local',
  status: 'online',
  agent_version: '0.1.2',
  available_agent_version: '0.1.3',
  upgrade_status: 'outdated',
  created_at: '2026-05-10T08:00:00.000Z',
  updated_at: '2026-09-07T08:00:00.000Z',
}

const meta: Meta<typeof AgentUpgradeBanner> = {
  title: 'Managed Agents/AgentUpgradeBanner',
  component: AgentUpgradeBanner,
}
export default meta

type Story = StoryObj<typeof AgentUpgradeBanner>

// There is deliberately no story for a fleet with nothing outdated: the banner
// renders null, and the snapshot harness waits for a visible #storybook-root,
// so an empty story times out the visual job. That case is asserted in
// __tests__/AgentUpgradeBanner.test.tsx instead.

export const OneOutdated: Story = {
  args: { agents: [base] },
}

export const SeveralOutdated: Story = {
  args: {
    agents: [
      base,
      { ...base, id: 2, name: 'Finance Workstation', agent_id: 'agt_fin_07' },
      { ...base, id: 3, name: 'Build Server', agent_id: 'agt_build_02' },
    ],
  },
}

export const WithUpgradeAll: Story = {
  name: 'Outdated agents with an Upgrade all action',
  args: {
    agents: [
      { ...base, self_upgrade_supported: true },
      {
        ...base,
        id: 2,
        name: 'Build Server',
        agent_id: 'agt_build_02',
        self_upgrade_supported: true,
      },
    ],
    onUpgradeAll: () => {},
  },
}

export const SomeNeedAManualReinstall: Story = {
  name: 'Outdated agents where some cannot upgrade themselves',
  args: {
    agents: [
      { ...base, self_upgrade_supported: true },
      {
        ...base,
        id: 2,
        name: 'Legacy Print Server',
        agent_id: 'agt_legacy_02',
        self_upgrade_supported: false,
      },
    ],
    onUpgradeAll: () => {},
  },
}

export const MixedTargets: Story = {
  name: 'Outdated agents with different targets',
  args: {
    agents: [
      base,
      {
        ...base,
        id: 2,
        name: 'Legacy Print Server',
        agent_id: 'agt_legacy_02',
        agent_version: '0.1.1',
        desired_agent_version: '0.1.2',
        available_agent_version: '0.1.3',
      },
    ],
  },
}

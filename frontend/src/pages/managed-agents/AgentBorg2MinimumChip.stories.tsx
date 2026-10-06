import type { Meta, StoryObj } from '@storybook/react-vite'
import AgentBorg2MinimumChip from './AgentBorg2MinimumChip'

const meta: Meta<typeof AgentBorg2MinimumChip> = {
  title: 'Managed Agents/AgentBorg2MinimumChip',
  component: AgentBorg2MinimumChip,
}
export default meta

type Story = StoryObj<typeof AgentBorg2MinimumChip>

/** An endpoint with Borg 1 and an older Borg 2: its Borg 2 jobs are refused. */
export const BelowMinimum: Story = {
  args: {
    belowMinimum: true,
    minimumVersion: '2.0.0b25',
    borgVersions: [
      { major: 1, version: '1.4.5' },
      { major: 2, version: '2.0.0b24' },
    ],
  },
}

/** Only Borg 2, older than the server's: the reinstall installs Borg 2 alone. */
export const BelowMinimumBorg2Only: Story = {
  args: {
    belowMinimum: true,
    minimumVersion: '2.0.0b25',
    borgVersions: [{ major: 2, version: '2.0.0b22' }],
  },
}

/** At the minimum: nothing is shown. */
export const AtMinimum: Story = {
  args: {
    belowMinimum: false,
    minimumVersion: '2.0.0b25',
    borgVersions: [{ major: 2, version: '2.0.0b25' }],
  },
}

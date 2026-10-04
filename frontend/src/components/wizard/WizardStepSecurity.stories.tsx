import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import WizardStepSecurity from './WizardStepSecurity'
import { fullFeatureSystemInfo } from './WizardStepLocation.storyFixtures'

const meta = {
  title: 'Components/Wizard/Repository Security',
  component: WizardStepSecurity,
  parameters: {
    layout: 'centered',
    systemInfo: fullFeatureSystemInfo,
  },
  render: (args) => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepSecurity {...args} />
    </Box>
  ),
} satisfies Meta<typeof WizardStepSecurity>

export default meta

type Story = StoryObj<typeof meta>

const data = {
  encryption: 'repokey-aes-ocb',
  passphrase: '',
  remotePath: '',
  selectedKeyfile: null,
}

export const Borg2Encrypted: Story = {
  args: { mode: 'create', borgVersion: 2, data, onChange: () => {} },
}

// Borg 2 has no unencrypted mode; `authenticated` stores the data
// unencrypted, protected by a key and passphrase.
export const Borg2Authenticated: Story = {
  args: {
    mode: 'create',
    borgVersion: 2,
    data: { ...data, encryption: 'authenticated' },
    onChange: () => {},
  },
}

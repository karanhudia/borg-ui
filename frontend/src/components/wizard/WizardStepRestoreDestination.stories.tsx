import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import WizardStepRestoreDestination, {
  type RestoreDestinationStepData,
} from './WizardStepRestoreDestination'

const noop = () => {}

const customPathData: RestoreDestinationStepData = {
  destinationType: 'local',
  destinationConnectionId: '',
  restoreStrategy: 'custom',
  customPath: '/recovery',
  restoreLayout: 'preserve_path',
  existingFiles: 'refuse',
}

const meta = {
  title: 'Components/Wizard/Restore Destination',
  component: WizardStepRestoreDestination,
  parameters: {
    layout: 'centered',
  },
  args: {
    data: customPathData,
    borgVersion: 2,
    selectedItems: [{ path: 'home/alex/documents', type: 'directory' }],
    sshConnections: [],
    repositoryType: 'local',
    onChange: noop,
    onBrowsePath: noop,
  },
  render: (args) => (
    <Box sx={{ width: 760, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepRestoreDestination {...args} />
    </Box>
  ),
} satisfies Meta<typeof WizardStepRestoreDestination>

export default meta

type Story = StoryObj<typeof meta>

/** Borg 2 default: a custom path and the exact restore into an empty directory. */
export const Borg2ExactRestore: Story = {}

/** Borg 2, writing into existing files, with the caveat of Borg's --continue. */
export const Borg2RestoreIntoExistingFiles: Story = {
  args: {
    data: { ...customPathData, existingFiles: 'continue' },
  },
}

/** Borg 2 to the original location: no exact restore there, an explicit choice is needed. */
export const Borg2OriginalLocationNeedsChoice: Story = {
  args: {
    data: { ...customPathData, restoreStrategy: 'original', customPath: '', existingFiles: null },
  },
}

/** Borg 1 overwrites files at the same path and offers no choice. */
export const Borg1OriginalLocation: Story = {
  args: {
    borgVersion: 1,
    data: { ...customPathData, restoreStrategy: 'original', customPath: '' },
  },
}

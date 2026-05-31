import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'

import PathSelectorField from './PathSelectorField'

const meta = {
  title: 'Components/PathSelectorField',
  component: PathSelectorField,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof PathSelectorField>

export default meta

type Story = StoryObj<typeof meta>

function PathSelectorPreview({
  initialValue = '/backups/repositories/app',
  helperText = 'Select a directory on the Borg UI server.',
  customBrowse = false,
  disabled = false,
}: {
  initialValue?: string
  helperText?: string
  customBrowse?: boolean
  disabled?: boolean
}) {
  const [value, setValue] = useState(initialValue)
  const [browseCount, setBrowseCount] = useState(0)

  return (
    <Box sx={{ width: 520, maxWidth: 'calc(100vw - 32px)' }}>
      <PathSelectorField
        label={customBrowse ? 'Relative Remote Path' : 'Repository Path'}
        value={value}
        onChange={setValue}
        placeholder={customBrowse ? 'borg-ui/repositories/app' : '/backups/repositories/app'}
        helperText={
          customBrowse && browseCount > 0
            ? `Custom browse action triggered ${browseCount} time${browseCount === 1 ? '' : 's'}.`
            : helperText
        }
        disabled={disabled}
        required
        onBrowse={customBrowse ? () => setBrowseCount((current) => current + 1) : undefined}
        browseButtonLabel={customBrowse ? 'Browse rclone remote' : undefined}
        browseButtonDisabled={disabled}
      />
    </Box>
  )
}

export const FilesystemBrowse: Story = {
  args: {
    label: 'Repository Path',
    value: '/backups/repositories/app',
    onChange: () => {},
  },
  render: () => <PathSelectorPreview />,
}

export const CustomBrowseAction: Story = {
  args: {
    label: 'Relative Remote Path',
    value: 'borg-ui/repositories/app',
    onChange: () => {},
  },
  render: () => (
    <PathSelectorPreview
      initialValue="borg-ui/repositories/app"
      helperText="Path inside the selected remote."
      customBrowse
    />
  ),
}

export const DisabledControl: Story = {
  args: {
    label: 'Relative Remote Path',
    value: 'borg-ui/repositories/app',
    onChange: () => {},
    disabled: true,
  },
  render: () => (
    <PathSelectorPreview
      initialValue="borg-ui/repositories/app"
      helperText="Select a remote before browsing."
      customBrowse
      disabled
    />
  ),
}

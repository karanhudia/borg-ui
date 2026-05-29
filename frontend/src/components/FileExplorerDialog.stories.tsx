import { useEffect, useState, type ComponentProps } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import MockAdapter from 'axios-mock-adapter'

import api from '../services/api'
import FileExplorerDialog from './FileExplorerDialog'

function useMockedAgentFilesystem() {
  useEffect(() => {
    const mock = new MockAdapter(api, { onNoMatch: 'passthrough' })

    mock.onGet('/managed-machines/agents/42/filesystem/browse').reply(200, {
      current_path: '/',
      parent_path: null,
      items: [
        {
          name: 'srv',
          path: '/srv',
          type: 'directory',
          size: 0,
          modified_at: 0,
          hidden: false,
        },
        {
          name: 'backup.env',
          path: '/backup.env',
          type: 'file',
          size: 2048,
          modified_at: 1_764_500_000,
          hidden: false,
        },
      ],
    })

    return () => {
      mock.restore()
    }
  }, [])
}

const meta = {
  title: 'Components/FileExplorerDialog',
  component: FileExplorerDialog,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof FileExplorerDialog>

export default meta

type Story = StoryObj<typeof meta>

function ManagedAgentBrowserStory(args: ComponentProps<typeof FileExplorerDialog>) {
  useMockedAgentFilesystem()
  const [container, setContainer] = useState<HTMLDivElement | null>(null)

  return (
    <Box ref={setContainer} sx={{ minHeight: '100vh' }}>
      {container ? <FileExplorerDialog {...args} dialogContainer={container} /> : null}
    </Box>
  )
}

export const ManagedAgentBrowser: Story = {
  args: {
    open: true,
    onClose: () => {},
    onSelect: () => {},
    title: 'Select source paths',
    initialPath: '/',
    multiSelect: true,
    connectionType: 'agent',
    agentId: 42,
    agentName: 'Build Runner',
    selectMode: 'both',
  },
  render: (args) => <ManagedAgentBrowserStory {...args} />,
}

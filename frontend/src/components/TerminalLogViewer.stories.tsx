import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import TerminalLogViewer from './TerminalLogViewer'

const escapedGreekPath = 'local/2026/\\u0391\\u03af\\u03b3\\u03b9\\u03bd\\u03b1/clip-001.MP4'
const unicodeJsonLog = `{"type":"archive_progress","path":"${escapedGreekPath}","original_size":344287526826,"compressed_size":3428682049350,"finished":false}`

const meta = {
  title: 'Components/TerminalLogViewer',
  component: TerminalLogViewer,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof TerminalLogViewer>

export default meta

type Story = StoryObj<typeof meta>

export const UnicodeJsonLog: Story = {
  args: {
    jobId: '161',
    status: 'completed',
    jobType: 'backup',
    onFetchLogs: async () => ({
      lines: [
        {
          line_number: 497,
          content: unicodeJsonLog,
        },
      ],
      total_lines: 1,
      has_more: false,
    }),
  },
  render: (args) => (
    <Box sx={{ width: 680 }}>
      <TerminalLogViewer {...args} />
    </Box>
  ),
}

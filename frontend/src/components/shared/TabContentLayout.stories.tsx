import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, Button, Paper, Typography } from '@mui/material'
import { Plus } from 'lucide-react'
import PageHeader from '../PageHeader'
import TabContentLayout from './TabContentLayout'

const meta = {
  title: 'Components/TabContentLayout',
  component: TabContentLayout,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof TabContentLayout>

export default meta

type Story = StoryObj<typeof meta>

export const WithHeader: Story = {
  args: {
    children: null,
  },
  render: () => (
    <Box sx={{ p: 3, bgcolor: 'background.default', minHeight: '100vh' }}>
      <TabContentLayout
        spacing={0}
        header={
          <PageHeader
            title="Remote Clients"
            subtitle="Register Borg UI client servers on other machines."
            actions={
              <Button variant="contained" startIcon={<Plus size={18} />}>
                Add remote client
              </Button>
            }
          />
        }
      >
        <Paper variant="outlined" sx={{ p: 3, borderRadius: 2 }}>
          <Typography fontWeight={700}>Content area</Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5 }}>
            The tab body can be replaced, gated, or loaded while the header remains stable.
          </Typography>
        </Paper>
      </TabContentLayout>
    </Box>
  ),
}

import type { Meta, StoryObj } from '@storybook/react-vite'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Box } from '@mui/material'
import RepositoryScopeSelect from './RepositoryScopeSelect'

// No API mocking layer exists in this codebase's stories, so the list holds
// only the "All repositories" entry here.
const meta: Meta<typeof RepositoryScopeSelect> = {
  title: 'Activity/RepositoryScopeSelect',
  component: RepositoryScopeSelect,
  decorators: [
    (Story) => (
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter>
          <Box sx={{ width: 320 }}>
            <Story />
          </Box>
        </MemoryRouter>
      </QueryClientProvider>
    ),
  ],
}

export default meta

type Story = StoryObj<typeof RepositoryScopeSelect>

export const AllRepositories: Story = { args: { value: null } }

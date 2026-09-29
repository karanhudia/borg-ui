import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'

import { RepositoryGroups } from './RepositoryGroups'

const noop = () => {}

const meta = {
  title: 'Pages/Repositories/Groups',
  component: RepositoryGroups,
  parameters: { layout: 'fullscreen' },
  decorators: [
    (Story) => (
      <Box sx={{ p: 3, maxWidth: 1120, mx: 'auto' }}>
        <Story />
      </Box>
    ),
  ],
  args: {
    isLoading: false,
    repositories: [],
    processedRepositories: { groups: [] },
    repositoriesWithJobs: new Set<number>(),
    searchQuery: '',
    canManageRepositoriesGlobally: true,
    canDo: () => true,
    canBreakLock: () => false,
    onSearchChange: noop,
    onOpenWizard: noop,
    onViewInfo: noop,
    onCheck: noop,
    onCompact: noop,
    onPrune: noop,
    onPrunePreview: noop,
    onWipeContents: noop,
    onBreakLock: noop,
    onEdit: noop,
    onDelete: noop,
    onPermanentDelete: noop,
    onBackupNow: noop,
    onViewArchives: noop,
    onViewBackupPlans: noop,
    onCreateBackupPlan: noop,
    onRcloneSync: noop,
    onRcloneHydrate: noop,
    canPermanentDeleteRepository: () => false,
    getCompressionLabel: (compression: string) => compression,
    onJobCompleted: noop,
  },
} satisfies Meta<typeof RepositoryGroups>

export default meta
type Story = StoryObj<typeof meta>

export const EmptyWithQuickStart: Story = {
  args: { onQuickStart: noop },
}

export const EmptyWithoutQuickStart: Story = {}

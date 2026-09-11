import type { Meta, StoryObj } from '@storybook/react-vite'
import { ThemeProvider } from '@mui/material/styles'
import { Box, CssBaseline } from '@mui/material'
import { getTheme } from '../../theme'
import RunChainRow, { type RunChainOperation } from './RunChainRow'

const meta: Meta<typeof RunChainRow> = {
  title: 'Activity/RunChainRow',
  component: RunChainRow,
}

export default meta

type Story = StoryObj<typeof RunChainRow>

const at = (offset: number) => new Date(Date.UTC(2026, 8, 11, 8, 32, offset)).toISOString()

// One step; `dur` seconds long, starting `start` seconds into the run.
function step(
  id: number,
  kind: string,
  status: string,
  extra: Partial<RunChainOperation> & { start?: number; dur?: number } = {}
): RunChainOperation {
  const { start, dur, ...rest } = extra
  return {
    id,
    kind,
    status,
    trigger: 'followup',
    ...(start != null && { started_at: at(start), completed_at: at(start + (dur ?? 0)) }),
    ...rest,
  }
}

// The real shape of job #11634: a plan backup that ran an inline prune and
// compact, each of which enqueued its own refresh chain.
// The real shape of job #11634: a plan backup wrapped by its hook scripts,
// then an inline prune and compact; the refresh chain hangs off the compact.
const fanOut: RunChainOperation[] = [
  step(562, 'script_execution', 'completed', {
    type: 'script_execution',
    trigger: 'plan',
    hook_type: 'pre-backup',
    name: 'Borg UI Default Vars',
  }),
  step(563, 'script_execution', 'completed', {
    type: 'script_execution',
    trigger: 'plan',
    hook_type: 'post-backup',
    name: 'Borg UI Default Vars',
  }),
  step(11635, 'prune', 'completed', { trigger: 'plan', depends_on_id: 11634, start: 9, dur: 3 }),
  step(11643, 'compact', 'completed', {
    trigger: 'plan',
    depends_on_id: 11634,
    start: 12,
    dur: 3,
  }),
  step(11636, 'archive_sync', 'completed', { depends_on_id: 11643, start: 15, dur: 1 }),
  step(11637, 'history_merge', 'completed', { depends_on_id: 11636, start: 16 }),
  step(11638, 'history_index', 'completed', { depends_on_id: 11637, start: 16, dur: 1 }),
  step(11639, 'stats', 'completed', { depends_on_id: 11638, start: 17 }),
]

const backup: RunChainOperation = {
  id: 11634,
  kind: 'backup',
  label: 'Backup',
  status: 'completed',
  started_at: at(-120),
  completed_at: at(12),
}

export const Succeeded: Story = {
  args: { operation: { ...backup, followups: fanOut } },
}

export const Running: Story = {
  args: {
    operation: {
      ...backup,
      followups: [
        step(1, 'archive_sync', 'completed', { depends_on_id: 11634, start: 0, dur: 2 }),
        step(2, 'history_merge', 'completed', { depends_on_id: 1, start: 2 }),
        step(3, 'history_index', 'running', {
          depends_on_id: 2,
          progress_current: 14,
          progress_total: 38,
          started_at: at(3),
        }),
        step(4, 'stats', 'queued', { depends_on_id: 3 }),
      ],
    },
  },
}

export const Failed: Story = {
  args: {
    operation: {
      ...backup,
      followups: [
        step(11635, 'prune', 'completed', {
          trigger: 'manual',
          depends_on_id: 11634,
          start: 9,
          dur: 3,
        }),
        step(11636, 'archive_sync', 'completed', { depends_on_id: 11634, start: 15, dur: 1 }),
        step(11637, 'history_merge', 'failed', { depends_on_id: 11636, start: 16 }),
        step(11638, 'history_index', 'skipped', { depends_on_id: 11637 }),
        step(11639, 'stats', 'skipped', { depends_on_id: 11638 }),
        step(11640, 'archive_sync', 'completed', { depends_on_id: 11635, start: 15, dur: 1 }),
        step(11641, 'history_merge', 'completed', { depends_on_id: 11640, start: 17 }),
        step(11642, 'stats', 'completed', { depends_on_id: 11641, start: 17 }),
      ],
    },
  },
}

export const SingleLane: Story = {
  args: {
    operation: {
      ...backup,
      followups: [
        step(1, 'archive_sync', 'completed', { depends_on_id: 11634, start: 0, dur: 2 }),
        step(2, 'history_index', 'completed', { depends_on_id: 1, start: 2, dur: 4 }),
        step(3, 'stats', 'completed', { depends_on_id: 2, start: 6 }),
      ],
    },
  },
}

export const Dark: Story = {
  args: { operation: { ...backup, followups: fanOut } },
  render: (args) => (
    <ThemeProvider theme={getTheme('dark')}>
      <CssBaseline />
      <Box sx={{ p: 2, bgcolor: 'background.paper' }}>
        <RunChainRow {...args} />
      </Box>
    </ThemeProvider>
  ),
}

import type { Meta, StoryObj } from '@storybook/react-vite'
import { ThemeProvider } from '@mui/material/styles'
import { Box, CssBaseline } from '@mui/material'
import { getTheme } from '../../theme'
import ActivityTimeline from './ActivityTimeline'
import type { ActivityItem } from '../Activity'
import type { ActionButton } from '../../components/RowActions'
import { Eye, Download, Trash2 } from 'lucide-react'

const meta: Meta<typeof ActivityTimeline> = {
  title: 'Activity/ActivityTimeline',
  component: ActivityTimeline,
  parameters: { layout: 'fullscreen' },
}

export default meta

type Story = StoryObj<typeof ActivityTimeline>

const at = (daysAgo: number, hour: number, minute: number, second = 0) => {
  const day = new Date()
  day.setDate(day.getDate() - daysAgo)
  day.setHours(hour, minute, second, 0)
  return day.toISOString()
}

const base = (overrides: Partial<ActivityItem>): ActivityItem => ({
  id: 1,
  type: 'backup',
  kind: 'backup',
  category: 'backup',
  status: 'completed',
  trigger: 'plan',
  started_at: at(0, 14, 0, 12),
  completed_at: at(0, 14, 2, 24),
  error_message: null,
  repository: 'Downloads Backup',
  repository_id: 4,
  repository_path: '/srv/borg/downloads',
  log_file_path: '/logs/1.log',
  archive_name: 'downloads-2026-09-11T14:00',
  package_name: null,
  backup_plan_name: 'Nightly',
  has_logs: true,
  execution_mode: 'server',
  ...overrides,
})

const step = (
  id: number,
  kind: string,
  status: string,
  extra: Partial<ActivityItem> = {}
): ActivityItem =>
  base({
    id,
    type: kind,
    kind,
    category: 'index',
    trigger: 'followup',
    status,
    archive_name: null,
    started_at: null,
    completed_at: null,
    ...extra,
  })

const hook = (id: number, root: number, hookType: string, when: string): ActivityItem =>
  base({
    id,
    type: 'script_execution',
    kind: null,
    category: 'system',
    trigger: 'plan',
    status: 'completed',
    hook_type: hookType,
    operation_id: root,
    package_name: 'Borg UI Default Vars',
    archive_name: null,
    started_at: when,
    completed_at: when,
  })

// The shape of a plan backup with inline prune and compact: the refresh
// chain hangs off the compact, the last stage, so it is the last thing the
// run does.
const fanOut = (root: number, prune: number, compact: number): ActivityItem[] => [
  hook(root + 100, root, 'pre-backup', at(0, 14, 0, 12)),
  hook(root + 101, root, 'post-backup', at(0, 14, 2, 21)),
  step(prune, 'prune', 'completed', {
    category: 'maintenance',
    trigger: 'plan',
    depends_on_id: root,
    started_at: at(0, 14, 2, 21),
    completed_at: at(0, 14, 2, 24),
  }),
  step(compact, 'compact', 'completed', {
    category: 'maintenance',
    trigger: 'plan',
    depends_on_id: root,
    started_at: at(0, 14, 2, 24),
    completed_at: at(0, 14, 2, 27),
  }),
  step(root + 2, 'archive_sync', 'completed', {
    depends_on_id: compact,
    started_at: at(0, 14, 2, 27),
    completed_at: at(0, 14, 2, 28),
  }),
  step(root + 3, 'history_merge', 'completed', {
    depends_on_id: root + 2,
    started_at: at(0, 14, 2, 28),
    completed_at: at(0, 14, 2, 28),
  }),
  step(root + 4, 'history_index', 'completed', {
    depends_on_id: root + 3,
    started_at: at(0, 14, 2, 28),
    completed_at: at(0, 14, 2, 29),
  }),
  step(root + 5, 'stats', 'completed', {
    depends_on_id: root + 4,
    started_at: at(0, 14, 2, 29),
    completed_at: at(0, 14, 2, 29),
  }),
]

const items: ActivityItem[] = [
  base({
    id: 11700,
    repository: 'Important Documents',
    repository_path: '/srv/borg/pending',
    status: 'running',
    started_at: at(0, 14, 5),
    completed_at: null,
    progress_percent: 41,
    progress_message: 'Reading /srv/data/documents/2026',
    archive_name: 'docs-2026-09-11T14:05',
    followups: [],
  }),
  base({
    id: 11902,
    type: 'script_execution',
    kind: null,
    category: 'system',
    trigger: 'plan',
    backup_plan_run_id: 217,
    hook_type: 'post-backup',
    repository: 'Notify on completion',
    repository_id: null,
    repository_path: null,
    package_name: 'Notify on completion',
    archive_name: null,
    execution_mode: null,
    started_at: at(0, 14, 2, 30),
    completed_at: at(0, 14, 2, 31),
  }),
  base({ id: 11634, backup_plan_run_id: 217, followups: fanOut(11634, 11635, 11643) }),
  base({
    id: 11620,
    backup_plan_run_id: 217,
    repository: 'Photos Library',
    repository_id: 5,
    repository_path: '/srv/borg/photos',
    archive_name: 'photos-2026-09-11T14:00',
    started_at: at(0, 14, 0, 12),
    completed_at: at(0, 14, 0, 58),
    followups: [
      step(11621, 'archive_sync', 'completed', {
        depends_on_id: 11620,
        started_at: at(0, 14, 1, 0),
        completed_at: at(0, 14, 1, 1),
      }),
      step(11622, 'stats', 'completed', {
        depends_on_id: 11621,
        started_at: at(0, 14, 1, 1),
        completed_at: at(0, 14, 1, 1),
      }),
    ],
  }),
  base({
    id: 563,
    type: 'script_execution',
    kind: null,
    category: 'system',
    trigger: 'manual',
    status: 'completed',
    repository: null,
    repository_id: null,
    repository_path: null,
    package_name: 'Borg UI Default Vars',
    archive_name: null,
    backup_plan_name: null,
    execution_mode: null,
    started_at: at(0, 14, 2, 21),
    completed_at: at(0, 14, 2, 21),
  }),
  base({
    id: 11548,
    type: 'check',
    kind: 'check',
    category: 'maintenance',
    trigger: 'schedule',
    schedule_name: 'Weekly integrity',
    backup_plan_name: null,
    status: 'failed',
    error_message: 'Repository check failed: 2 chunks missing',
    archive_name: null,
    started_at: at(0, 12, 21, 50),
    completed_at: at(0, 12, 21, 58),
  }),
  base({
    id: 11549,
    type: 'check',
    kind: 'check',
    category: 'maintenance',
    trigger: 'schedule',
    schedule_name: 'Weekly integrity',
    backup_plan_name: null,
    status: 'cancelled',
    repository: 'Important Documents',
    repository_path: '/srv/borg/pending',
    archive_name: null,
    started_at: at(0, 12, 21, 50),
    completed_at: at(0, 12, 21, 54),
  }),
  base({
    id: 11453,
    backup_plan_run_id: 210,
    repository: 'Important Documents Redundancy',
    repository_path: '/srv/borg/pending-redundancy',
    started_at: at(1, 0, 1, 10),
    completed_at: at(1, 0, 1, 15),
    archive_name: 'redundancy-2026-09-10T00:01',
    followups: fanOut(11453, 11454, 11462),
  }),
  base({
    id: 11428,
    repository: 'Raspberry Pi to Macbook Backup',
    repository_path: '/srv/borg/remote',
    status: 'failed',
    error_message: 'LOCK_ERROR::/srv/borg/remote',
    execution_mode: 'agent',
    started_at: at(1, 0, 0, 55),
    completed_at: at(1, 0, 0, 56),
  }),
  base({
    id: 11300,
    type: 'restore_check',
    kind: 'restore_check',
    category: 'restore',
    trigger: 'schedule',
    schedule_name: 'Monthly restore drill',
    backup_plan_name: null,
    archive_name: 'downloads-2026-09-01T02:00',
    started_at: at(3, 0, 44, 2),
    completed_at: at(3, 1, 0, 40),
  }),
]

const actions: ActionButton<ActivityItem>[] = [
  {
    icon: <Eye size={18} />,
    label: 'View logs',
    onClick: () => {},
    tooltip: 'View logs',
    show: (item) => item.status !== 'pending',
  },
  {
    icon: <Download size={18} />,
    label: 'Download logs',
    onClick: () => {},
    color: 'info',
    tooltip: 'Download logs',
  },
  {
    icon: <Trash2 size={18} />,
    label: 'Delete',
    onClick: () => {},
    color: 'error',
    tooltip: 'Delete',
    show: (item) => item.status !== 'running',
  },
]

function Page({ dark = false, pinned = false }: { dark?: boolean; pinned?: boolean }) {
  const body = (
    <Box sx={{ p: 3, bgcolor: 'background.default', minHeight: '100vh' }}>
      <ActivityTimeline
        items={items}
        loading={false}
        actions={actions}
        showRepository={!pinned}
        getKey={(item) => String(item.id)}
      />
    </Box>
  )
  if (!dark) return body
  return (
    <ThemeProvider theme={getTheme('dark')}>
      <CssBaseline />
      {body}
    </ThemeProvider>
  )
}

export const Global: Story = { render: () => <Page /> }
export const Pinned: Story = { render: () => <Page pinned /> }
export const Dark: Story = { render: () => <Page dark /> }
export const Loading: Story = {
  render: () => (
    <Box sx={{ p: 3 }}>
      <ActivityTimeline
        items={[]}
        loading
        actions={[]}
        showRepository
        getKey={(item) => String(item.id)}
      />
    </Box>
  ),
}

import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import { RepositoryHealthPanel } from './RepositoryHealthPanel'
import { makeT, TokenContext, type Tokens } from './tokens'
import type { DashboardOverview } from './types'

type RepositoryHealth = DashboardOverview['repository_health']

// Follows the Storybook theme toolbar, so each story renders both modes.
const useStoryT = () => makeT(useTheme().palette.mode === 'dark')
const nowMs = Date.parse('2026-06-04T09:00:00.000Z')

const surface = (T: Tokens) =>
  ({
    bgcolor: T.bgCard,
    border: `1px solid ${T.border}`,
    borderRadius: T.radius,
    transition: 'border-color 0.2s',
    '&:hover': { borderColor: T.borderHover },
  }) as const

const mixedRepositories: RepositoryHealth = [
  {
    id: 1,
    name: 'Immich Onsite',
    type: 'local',
    mode: 'full',
    last_backup: '2026-05-30T10:00:00.000Z',
    last_check: '2026-05-07T10:00:00.000Z',
    last_compact: '2026-05-30T10:00:00.000Z',
    last_restore_check: '2026-05-07T10:00:00.000Z',
    archive_count: 4,
    total_size: '833.69 GB',
    health_status: 'warning',
    warnings: ['Restore check is behind'],
    next_run: null,
    has_schedule: false,
    schedule_enabled: false,
    schedule_name: null,
    schedule_timezone: null,
    backup_plan_count: 0,
    backup_plan_scheduled_count: 0,
    backup_plan_names: [],
    backup_plan_next_run: null,
    restore_check_configured: true,
    latest_restore_check_status: 'completed_with_warnings',
    latest_restore_check_error: null,
    dimension_health: {
      backup: 'healthy',
      check: 'warning',
      compact: 'healthy',
      restore: 'warning',
    },
  },
  {
    id: 2,
    name: 'Databases Backup',
    type: 'local',
    mode: 'full',
    last_backup: '2026-06-02T10:00:00.000Z',
    last_check: '2026-06-02T10:00:00.000Z',
    last_compact: '2026-06-02T10:00:00.000Z',
    last_restore_check: '2026-06-02T10:00:00.000Z',
    archive_count: 1,
    total_size: '20.97 MB',
    health_status: 'healthy',
    warnings: [],
    next_run: null,
    has_schedule: false,
    schedule_enabled: false,
    schedule_name: null,
    schedule_timezone: null,
    backup_plan_count: 0,
    backup_plan_scheduled_count: 0,
    backup_plan_names: [],
    backup_plan_next_run: null,
    restore_check_configured: true,
    latest_restore_check_status: 'completed',
    latest_restore_check_error: null,
    dimension_health: {
      backup: 'healthy',
      check: 'healthy',
      compact: 'healthy',
      restore: 'healthy',
    },
  },
  {
    id: 3,
    name: 'Immich Backup',
    type: 'ssh',
    mode: 'full',
    last_backup: '2026-05-30T10:00:00.000Z',
    last_check: '2026-05-30T10:00:00.000Z',
    last_compact: '2026-05-30T10:00:00.000Z',
    last_restore_check: '2026-05-30T10:00:00.000Z',
    archive_count: 4,
    total_size: '821.73 GB',
    health_status: 'healthy',
    warnings: [],
    next_run: null,
    has_schedule: false,
    schedule_enabled: false,
    schedule_name: null,
    schedule_timezone: null,
    backup_plan_count: 0,
    backup_plan_scheduled_count: 0,
    backup_plan_names: [],
    backup_plan_next_run: null,
    restore_check_configured: true,
    latest_restore_check_status: 'completed',
    latest_restore_check_error: null,
    dimension_health: {
      backup: 'healthy',
      check: 'healthy',
      compact: 'healthy',
      restore: 'healthy',
    },
  },
]

const meta = {
  title: 'Pages/DashboardV3/RepositoryHealthPanel',
  component: RepositoryHealthPanel,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof RepositoryHealthPanel>

export default meta

type Story = StoryObj<typeof meta>

export const MixedWarningAndHealthy: Story = {
  args: {
    // Placeholders for the required props: render swaps in the tokens for
    // the active theme.
    T: makeT(false),
    surface: surface(makeT(false)),
    repos: mixedRepositories,
    criticalCount: 0,
    warningCount: 1,
    healthyCount: 2,
    nowMs,
    currentFailures: [],
    onOpenRepositories: () => {},
  },
  render: function Render(args) {
    const T = useStoryT()
    return (
      <TokenContext.Provider value={T}>
        <Box
          sx={{
            minHeight: '100vh',
            p: 3,
            color: T.textPrimary,
          }}
        >
          <Box sx={{ width: '100%', maxWidth: 1280, mx: 'auto' }}>
            <RepositoryHealthPanel {...args} T={T} surface={surface(T)} />
          </Box>
        </Box>
      </TokenContext.Provider>
    )
  },
}

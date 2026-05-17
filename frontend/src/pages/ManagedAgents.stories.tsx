import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, Chip, Divider, Paper, Stack, Typography } from '@mui/material'
import { Laptop, Play, Server } from 'lucide-react'
import type {
  AgentEnrollmentTokenSummary,
  AgentJobResponse,
  AgentMachineResponse,
} from '../services/api'
import { AgentList, JobsTable, TokensTable } from './ManagedAgents'

const agents: AgentMachineResponse[] = [
  {
    id: 1,
    name: 'Production NAS',
    agent_id: 'agt_prod_nas_01',
    hostname: 'nas-01.local',
    os: 'linux',
    arch: 'arm64',
    agent_version: '0.1.0',
    borg_versions: [{ major: 2, version: '2.0.0b10', path: '/usr/local/bin/borg2' }],
    capabilities: ['backup.create', 'backup.cancel', 'logs.stream'],
    labels: { site: 'home-lab' },
    status: 'online',
    last_seen_at: '2026-05-16T11:56:00.000Z',
    last_error: null,
    created_at: '2026-05-10T08:00:00.000Z',
    updated_at: '2026-05-16T11:56:00.000Z',
  },
  {
    id: 2,
    name: 'Finance Workstation',
    agent_id: 'agt_finance_ws_07',
    hostname: 'finance-ws-07.example.com',
    os: 'linux',
    arch: 'x86_64',
    agent_version: '0.1.0',
    borg_versions: [{ major: 1, version: '1.2.8', path: '/usr/bin/borg' }],
    capabilities: ['backup.create', 'logs.stream'],
    labels: { department: 'finance' },
    status: 'offline',
    last_seen_at: '2026-05-16T08:45:00.000Z',
    last_error: 'Last heartbeat missed after network change',
    created_at: '2026-05-09T10:30:00.000Z',
    updated_at: '2026-05-16T08:45:00.000Z',
  },
]

const jobs: AgentJobResponse[] = [
  {
    id: 501,
    agent_machine_id: 1,
    backup_job_id: 9001,
    job_type: 'backup',
    status: 'running',
    payload: { job_kind: 'backup.create' },
    result: null,
    claimed_at: '2026-05-16T11:50:00.000Z',
    started_at: '2026-05-16T11:51:00.000Z',
    completed_at: null,
    error_message: null,
    progress_percent: 68,
    current_file: '/srv/media/photos',
    created_at: '2026-05-16T11:49:00.000Z',
    updated_at: '2026-05-16T11:56:00.000Z',
  },
  {
    id: 500,
    agent_machine_id: 2,
    backup_job_id: 9000,
    job_type: 'backup',
    status: 'completed',
    payload: { job_kind: 'backup.create' },
    result: { archive_name: 'finance-ws-2026-05-16' },
    claimed_at: '2026-05-16T07:15:00.000Z',
    started_at: '2026-05-16T07:16:00.000Z',
    completed_at: '2026-05-16T07:42:00.000Z',
    error_message: null,
    progress_percent: 100,
    current_file: null,
    created_at: '2026-05-16T07:14:00.000Z',
    updated_at: '2026-05-16T07:42:00.000Z',
  },
]

const tokens: AgentEnrollmentTokenSummary[] = [
  {
    id: 11,
    name: 'May workstation rollout',
    token_prefix: 'borgui_enroll_8qP',
    expires_at: '2026-05-18T12:00:00.000Z',
    used_at: null,
    used_by_agent_id: null,
    revoked_at: null,
    created_at: '2026-05-16T09:00:00.000Z',
  },
  {
    id: 10,
    name: 'NAS bootstrap',
    token_prefix: 'borgui_enroll_c6X',
    expires_at: '2026-05-17T09:00:00.000Z',
    used_at: '2026-05-16T09:30:00.000Z',
    used_by_agent_id: 1,
    revoked_at: null,
    created_at: '2026-05-16T09:00:00.000Z',
  },
]

const agentsById = new Map(agents.map((agent) => [agent.id, agent]))

const meta = {
  title: 'Pages/ManagedAgents',
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta

export default meta

type Story = StoryObj<typeof meta>

export const FleetOverview: Story = {
  render: () => (
    <Box sx={{ p: 3, bgcolor: 'background.default', minHeight: '100vh' }}>
      <Stack spacing={3} sx={{ maxWidth: 1180, mx: 'auto' }}>
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={2}
          justifyContent="space-between"
          alignItems={{ xs: 'stretch', md: 'center' }}
        >
          <Box>
            <Typography variant="h4" fontWeight={700}>
              Managed Agents
            </Typography>
            <Typography color="text.secondary" sx={{ mt: 0.5 }}>
              Lightweight machines connected to this Borg UI server
            </Typography>
          </Box>
          <Chip label="2 machines / 1 active job" color="primary" variant="outlined" />
        </Stack>

        <Paper variant="outlined" sx={{ borderRadius: 2, overflow: 'hidden' }}>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, 1fr)' },
            }}
          >
            {[
              { label: 'Agents', value: agents.length, icon: Laptop },
              { label: 'Online', value: 1, icon: Server },
              { label: 'Running Jobs', value: 1, icon: Play },
            ].map((stat, index) => {
              const Icon = stat.icon
              return (
                <Box
                  key={stat.label}
                  sx={{
                    px: 2,
                    py: 1.75,
                    borderRight: { xs: 0, sm: index < 2 ? '1px solid' : 0 },
                    borderBottom: { xs: index < 2 ? '1px solid' : 0, sm: 0 },
                    borderColor: 'divider',
                  }}
                >
                  <Stack direction="row" spacing={0.75} alignItems="center" color="text.secondary">
                    <Icon size={15} />
                    <Typography variant="caption" fontWeight={700} textTransform="uppercase">
                      {stat.label}
                    </Typography>
                  </Stack>
                  <Typography variant="h5" fontWeight={700} sx={{ mt: 0.5 }}>
                    {stat.value}
                  </Typography>
                </Box>
              )
            })}
          </Box>
        </Paper>

        <Box>
          <Typography variant="h6" fontWeight={700} sx={{ mb: 1.5 }}>
            Fleet
          </Typography>
          <AgentList
            agents={agents}
            onQueueBackup={() => {}}
            onRevoke={() => {}}
            isRevoking={false}
          />
        </Box>

        <Divider />

        <Box>
          <Typography variant="h6" fontWeight={700} sx={{ mb: 1.5 }}>
            Jobs
          </Typography>
          <JobsTable
            jobs={jobs}
            agentsById={agentsById}
            onCancel={() => {}}
            onViewLogs={() => {}}
            isCanceling={false}
          />
        </Box>

        <Box>
          <Typography variant="h6" fontWeight={700} sx={{ mb: 1.5 }}>
            Enrollment Tokens
          </Typography>
          <TokensTable tokens={tokens} onRevoke={() => {}} isRevoking={false} />
        </Box>
      </Stack>
    </Box>
  ),
}

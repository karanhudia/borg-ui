import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'

import type { AgentMachineResponse } from '../../../services/api'
import type { Repository } from '../../../types'
import { createInitialState } from '../state'
import type { SSHConnection, WizardState } from '../types'
import { ReviewStep } from './ReviewStep'

const agents: AgentMachineResponse[] = [
  {
    id: 31,
    name: 'Agent A',
    agent_id: 'agt_a',
    hostname: 'agent-a.local',
    status: 'online',
    created_at: '2026-05-20T00:00:00Z',
    updated_at: '2026-05-20T00:00:00Z',
  },
  {
    id: 32,
    name: 'Agent B',
    agent_id: 'agt_b',
    hostname: 'agent-b.local',
    status: 'online',
    created_at: '2026-05-20T00:00:00Z',
    updated_at: '2026-05-20T00:00:00Z',
  },
]

const sshConnections: SSHConnection[] = [
  {
    id: 11,
    host: 'storage.example',
    username: 'borg',
    port: 22,
    ssh_key_id: 1,
    status: 'connected',
  },
]

const serverRepo: Repository = {
  id: 1,
  name: 'Server local repository',
  path: '/backups/server',
  executor_type: 'server',
  connection_id: null,
}

const sshRepo: Repository = {
  id: 2,
  name: 'SSH repository',
  path: 'ssh://borg@storage.example:22/backups/repo',
  executor_type: 'server',
  connection_id: 11,
}

const agentRepoA: Repository = {
  id: 3,
  name: 'Agent A repository',
  path: '/backups/agent-a',
  executor_type: 'agent',
  execution_target: 'agent',
  agent_machine_id: 31,
}

const agentRepoB: Repository = {
  ...agentRepoA,
  id: 4,
  name: 'Agent B repository',
  agent_machine_id: 32,
}

function stateWith(
  repositoryIds: number[],
  sourceLocations: WizardState['sourceLocations']
): WizardState {
  const sourceDirectories = sourceLocations?.flatMap((location) => location.paths) || []
  return {
    ...createInitialState(),
    name: 'Nightly backup plan',
    sourceType:
      sourceLocations && sourceLocations.length > 1
        ? 'mixed'
        : sourceLocations?.[0]?.source_type || 'local',
    sourceSshConnectionId:
      sourceLocations?.[0]?.source_type === 'remote'
        ? sourceLocations[0].source_ssh_connection_id || ''
        : '',
    sourceDirectories,
    sourceLocations,
    repositoryIds,
  }
}

const translations: Record<string, string> = {
  'backupPlans.wizard.steps.review': 'Review',
  'backupPlans.wizard.steps.settings': 'Settings',
  'backupPlans.wizard.steps.scripts': 'Scripts',
  'backupPlans.wizard.steps.schedule': 'Schedule',
  'backupPlans.wizard.review.plan': 'Plan',
  'backupPlans.wizard.review.sourceLocation': 'Source location',
  'backupPlans.wizard.review.remoteSource': 'Remote client',
  'backupPlans.sourceChooser.borgUiServer': 'Borg UI server',
  'backupPlans.sourceChooser.managedAgent': 'Managed agent',
  'backupPlans.sourceChooser.mixedSources': 'Multiple sources',
  'backupPlans.sourceChooser.databaseLivePath': 'Live database path',
  'backupPlans.sourceChooser.databaseBackupPaths': 'Final Borg paths',
  'backupPlans.sourceChooser.containerBackupPath': 'Export staging path',
  'backupPlans.wizard.review.sources': 'Sources',
  'backupPlans.wizard.review.repositories': 'Repositories',
  'backupPlans.wizard.review.compression': 'Compression',
  'backupPlans.wizard.review.noScript': 'None',
  'backupPlans.wizard.review.planPreScript': 'Plan pre-script',
  'backupPlans.wizard.review.planPostScript': 'Plan post-script',
  'backupPlans.wizard.review.repositoryScripts': 'Repository scripts',
  'backupPlans.wizard.review.runMode': 'Run mode',
  'backupPlans.wizard.review.manualOnlyHint': 'Runs only when triggered manually.',
  'backupPlans.wizard.review.prune': 'Prune',
  'backupPlans.wizard.review.compact': 'Compact',
  'backupPlans.wizard.review.check': 'Check',
  'backupPlans.wizard.review.retention': 'Retention',
  'backupPlans.wizard.review.retentionValue': 'daily {{daily}}, weekly {{weekly}}',
  'backupPlans.wizard.review.checkDuration': '{{seconds}} seconds',
  'backupPlans.wizard.fields.archiveNameTemplate': 'Archive name template',
  'backupPlans.wizard.fields.uploadSpeedLimit': 'Upload speed limit',
  'backupPlans.wizard.fields.maxParallelRepositories': 'Max parallel repositories',
  'backupPlans.status.series': 'Series',
  'backupPlans.status.parallel': 'Parallel',
  'backupPlans.status.manualOnly': 'Manual only',
  'backupPlans.routePreview.runsOnServer': 'Runs on Borg UI server',
  'backupPlans.routePreview.runsOnSshHost': 'Runs on SSH host',
  'backupPlans.routePreview.runsOnManagedAgent': 'Runs on managed agent',
  'backupPlans.routePreview.sourceMustMatchAgent':
    'This repository is controlled by {{agent}}, so sources must also be on {{agent}}.',
  'backupPlans.routePreview.agentRepoSshUnsupported':
    'Agent-owned repositories cannot use SSH repository targets.',
  'backupPlans.routePreview.serverToAgentRepo':
    'Borg UI cannot push server-local paths into an agent-owned repository.',
  'backupPlans.routePreview.agentSourceToServerRepo':
    'Agent sources cannot be backed up into a server-owned repository.',
  'backupPlans.routePreview.mixedAgentSources':
    'Managed-agent sources cannot be mixed with Borg UI server or SSH sources.',
  'common.enabled': 'Enabled',
  'common.disabled': 'Disabled',
  'repositories.moreCount': '+{{count}}',
  'wizard.review.excludePatterns': 'Exclude patterns',
}

const t = (key: string, params?: Record<string, unknown>) =>
  (translations[key] || key)
    .replace('{{agent}}', String(params?.agent ?? ''))
    .replace('{{count}}', String(params?.count ?? ''))
    .replace('{{daily}}', String(params?.daily ?? ''))
    .replace('{{weekly}}', String(params?.weekly ?? ''))
    .replace('{{seconds}}', String(params?.seconds ?? ''))

function renderReview(wizardState: WizardState, repositories: Repository[]) {
  const selectedSourceConnection =
    wizardState.sourceSshConnectionId === 11 ? sshConnections[0] : null
  return (
    <Box sx={{ width: 900, maxWidth: 'calc(100vw - 32px)' }}>
      <ReviewStep
        wizardState={wizardState}
        repositories={repositories}
        agentMachines={agents}
        selectedSourceConnection={selectedSourceConnection}
        scripts={[]}
        t={t as never}
      />
    </Box>
  )
}

const meta: Meta = {
  title: 'Backup Plans/ReviewStep',
  parameters: { layout: 'centered' },
}

export default meta

type Story = StoryObj

export const ServerSourceToServerRepo: Story = {
  render: () =>
    renderReview(
      stateWith(
        [serverRepo.id],
        [{ source_type: 'local', source_ssh_connection_id: null, paths: ['/srv/app'] }]
      ),
      [serverRepo]
    ),
}

export const DatabaseSourceToServerRepo: Story = {
  render: () =>
    renderReview(
      {
        ...stateWith(
          [serverRepo.id],
          [
            {
              source_type: 'local',
              source_ssh_connection_id: null,
              paths: ['/var/tmp/borg-ui/database-dumps/sqlite'],
              database: {
                template_id: 'sqlite',
                engine: 'SQLite',
                display_name: 'SQLite database',
                backup_strategy: 'online_backup',
                detected_source_path: '/home/app/state.sqlite',
                detection_label: 'Borg UI server',
                capture_mode: 'dump',
                dump_path: '/var/tmp/borg-ui/database-dumps/sqlite',
                backup_paths: ['/var/tmp/borg-ui/database-dumps/sqlite'],
                script_execution_target: 'source',
              },
            },
          ]
        ),
        name: 'SQLite database backup',
        databaseTemplateId: 'sqlite',
      },
      [serverRepo]
    ),
}

export const DockerContainerSourceToServerRepo: Story = {
  render: () =>
    renderReview(
      {
        ...stateWith(
          [serverRepo.id],
          [
            {
              source_type: 'local',
              source_ssh_connection_id: null,
              paths: ['/var/tmp/borg-ui/container-exports/postgres'],
              container: {
                container_name: 'postgres',
                display_name: 'postgres',
                image: 'postgres:17',
                backup_mode: 'export',
                export_path: '/var/tmp/borg-ui/container-exports/postgres',
                script_execution_target: 'source',
                pre_backup_script_id: 201,
                post_backup_script_id: 202,
                script_execution_order: 1,
              },
            },
          ]
        ),
        name: 'Postgres container export',
      },
      [serverRepo]
    ),
}

export const SshSourceToSameSshRepo: Story = {
  render: () =>
    renderReview(
      stateWith(
        [sshRepo.id],
        [{ source_type: 'remote', source_ssh_connection_id: 11, paths: ['/srv/app'] }]
      ),
      [sshRepo]
    ),
}

export const AgentSourceToSameAgentRepo: Story = {
  render: () =>
    renderReview(
      stateWith(
        [agentRepoA.id],
        [
          {
            source_type: 'agent',
            source_ssh_connection_id: null,
            agent_machine_id: 31,
            paths: ['/srv/app'],
          },
        ]
      ),
      [agentRepoA]
    ),
}

export const UnsupportedServerSourceToAgentRepo: Story = {
  render: () =>
    renderReview(
      stateWith(
        [agentRepoA.id],
        [{ source_type: 'local', source_ssh_connection_id: null, paths: ['/srv/app'] }]
      ),
      [agentRepoA]
    ),
}

export const UnsupportedDifferentAgentSource: Story = {
  render: () =>
    renderReview(
      stateWith(
        [agentRepoB.id],
        [
          {
            source_type: 'agent',
            source_ssh_connection_id: null,
            agent_machine_id: 31,
            paths: ['/srv/app'],
          },
        ]
      ),
      [agentRepoB]
    ),
}

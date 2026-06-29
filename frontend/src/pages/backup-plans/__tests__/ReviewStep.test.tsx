import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { Repository } from '../../../types'
import { createInitialState } from '../state'
import { ReviewStep } from '../wizard-step/ReviewStep'
import type { WizardState } from '../types'

const translations: Record<string, string> = {
  'backupPlans.sourceChooser.borgUiServer': 'Borg UI server',
  'backupPlans.sourceChooser.databaseBackupPaths': 'Final Borg paths',
  'backupPlans.sourceChooser.databaseLivePath': 'Live database path',
  'backupPlans.sourceChooser.databaseTitle': 'Database scan',
  'backupPlans.sourceChooser.containerBackupPath': 'Export staging path',
  'backupPlans.sourceChooser.containerTitle': 'Docker container',
  'backupPlans.sourceChooser.mixedSources': 'Multiple sources',
  'backupPlans.wizard.fields.archiveNameTemplate': 'Archive name',
  'backupPlans.wizard.fields.cronExpression': 'Cron expression',
  'backupPlans.wizard.fields.timezone': 'Timezone',
  'backupPlans.wizard.review.scheduledUploadLimits': 'Scheduled upload limits',
  'backupPlans.wizard.review.uploadPolicyLimit': '{{limit}} MB/s',
  'backupPlans.wizard.review.uploadPolicyUnlimited': 'Unlimited',
  'backupPlans.wizard.maintenance.title': 'Maintenance',
  'backupPlans.wizard.review.check': 'Check',
  'backupPlans.wizard.review.checkDuration': '{{seconds}} seconds',
  'backupPlans.wizard.review.compact': 'Compact',
  'backupPlans.wizard.review.compression': 'Compression',
  'backupPlans.wizard.review.manualOnlyHint': 'Runs only when triggered manually.',
  'backupPlans.wizard.review.noScript': 'None',
  'backupPlans.wizard.review.pathCount': '{{count}} paths',
  'backupPlans.wizard.review.plan': 'Plan',
  'backupPlans.wizard.review.planPostScript': 'Plan post-script',
  'backupPlans.wizard.review.planPreScript': 'Plan pre-script',
  'backupPlans.wizard.review.prune': 'Prune',
  'backupPlans.wizard.review.repositories': 'Repositories',
  'backupPlans.wizard.review.repositoryScripts': 'Repository scripts',
  'backupPlans.wizard.review.retentionValue':
    'daily {{daily}}, weekly {{weekly}}',
  'backupPlans.wizard.review.retentionValueWithWithin':
    'daily {{daily}}, weekly {{weekly}}, within {{within}}',
  'backupPlans.wizard.review.runMode': 'Run mode',
  'backupPlans.wizard.review.sourceLocation': 'Source location',
  'backupPlans.wizard.review.sources': 'Sources',
  'backupPlans.wizard.steps.review': 'Review',
  'backupPlans.wizard.steps.schedule': 'Schedule',
  'backupPlans.wizard.steps.scripts': 'Scripts',
  'backupPlans.wizard.steps.settings': 'Settings',
  'common.disabled': 'Disabled',
  'common.enabled': 'Enabled',
  'repositories.moreCount': '+{{count}} more',
  'wizard.review.excludePatterns': 'Exclude patterns',
}

const t = (key: string, options?: Record<string, unknown>) => {
  const template = translations[key] || key
  return template
    .replace('{{count}}', String(options?.count ?? ''))
    .replace('{{daily}}', String(options?.daily ?? ''))
    .replace('{{weekly}}', String(options?.weekly ?? ''))
    .replace('{{within}}', String(options?.within ?? ''))
    .replace('{{seconds}}', String(options?.seconds ?? ''))
    .replace('{{limit}}', String(options?.limit ?? ''))
}

const repository: Repository = {
  id: 10,
  name: 'Local borg repo',
  path: '/backups/local',
  repository_type: 'local',
}

function renderReview(wizardState: WizardState) {
  return render(
    <ReviewStep
      wizardState={wizardState}
      repositories={[repository]}
      agentMachines={[]}
      selectedSourceConnection={null}
      scripts={[]}
      t={t as never}
    />
  )
}

describe('ReviewStep', () => {
  it('shows scheduled upload limit windows', () => {
    renderReview({
      ...createInitialState(),
      name: 'Policy backup',
      sourceDirectories: ['/data'],
      repositoryIds: [10],
      uploadRatelimitSchedulePolicies: [
        {
          label: 'Daytime cap',
          startTime: '08:00',
          endTime: '18:00',
          uploadRatelimitMb: '0.5',
        },
        {
          label: 'Overnight unlimited',
          startTime: '18:00',
          endTime: '08:00',
          uploadRatelimitMb: '',
        },
      ],
    })

    expect(screen.getByText('Scheduled upload limits')).toBeInTheDocument()
    expect(screen.getByText('Daytime cap')).toBeInTheDocument()
    expect(screen.getByText(/08:00\s*[-–]\s*18:00/)).toBeInTheDocument()
    expect(screen.getByText('0.5 MB/s')).toBeInTheDocument()
    expect(screen.getByText('Overnight unlimited')).toBeInTheDocument()
    expect(screen.getByText(/18:00\s*[-–]\s*08:00/)).toBeInTheDocument()
    expect(screen.getByText('Unlimited')).toBeInTheDocument()
  })

  it('shows live database source paths next to final Borg paths', () => {
    renderReview({
      ...createInitialState(),
      name: 'SQLite backup',
      sourceType: 'local',
      sourceDirectories: ['/var/tmp/borg-ui/database-dumps/sqlite'],
      sourceLocations: [
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
      ],
      repositoryIds: [10],
    })

    expect(screen.getByText('SQLite database')).toBeInTheDocument()
    expect(screen.getByText('Live database path')).toBeInTheDocument()
    expect(screen.getByText('/home/app/state.sqlite')).toBeInTheDocument()
    expect(screen.getByText('Final Borg paths')).toBeInTheDocument()
    expect(screen.getByText('/var/tmp/borg-ui/database-dumps/sqlite')).toBeInTheDocument()
  })

  it('shows Docker container source details next to the export path', () => {
    renderReview({
      ...createInitialState(),
      name: 'Postgres container backup',
      sourceType: 'local',
      sourceDirectories: ['/var/tmp/borg-ui/container-exports/postgres'],
      sourceLocations: [
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
          },
        },
      ],
      repositoryIds: [10],
    })

    expect(screen.getByText('Docker container')).toBeInTheDocument()
    expect(screen.getByText('postgres')).toBeInTheDocument()
    expect(screen.getByText('postgres:17')).toBeInTheDocument()
    expect(screen.getByText('Export staging path')).toBeInTheDocument()
    expect(screen.getByText('/var/tmp/borg-ui/container-exports/postgres')).toBeInTheDocument()
  })

  it('shows keep-within retention in the prune review', () => {
    renderReview({
      ...createInitialState(),
      name: 'Frequent backup',
      sourceDirectories: ['/data'],
      repositoryIds: [10],
      runPruneAfter: true,
      pruneKeepWithin: '1d',
    })

    expect(screen.getByText('Prune')).toBeInTheDocument()
    expect(screen.getByText(/within 1d/)).toBeInTheDocument()
  })

  it('omits keep-within retention when the interval is blank', () => {
    renderReview({
      ...createInitialState(),
      name: 'Frequent backup',
      sourceDirectories: ['/data'],
      repositoryIds: [10],
      runPruneAfter: true,
      pruneKeepWithin: '',
    })

    expect(screen.getByText('Prune')).toBeInTheDocument()
    expect(screen.queryByText(/within/i)).not.toBeInTheDocument()
  })
})

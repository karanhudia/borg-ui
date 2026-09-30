import { useCallback, useEffect, useState, type ComponentType } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import MockAdapter from 'axios-mock-adapter'

import api, { type AppDetection } from '../../services/api'
import { immichFound, immichStats, immichTemplate } from '../app-templates/appTemplates.fixtures'
import type { SshConnectionSummary } from '../shared/SshConnectionSelect'
import QuickStartAppStep from './steps/QuickStartAppStep'
import QuickStartConnectStep from './steps/QuickStartConnectStep'

import {
  createInitialQuickStartAnswers,
  type QuickStartAnswers,
  type QuickStartSettingsChange,
  type QuickStartStepProps,
} from './quickStartState'
import QuickStartDestinationStep from './steps/QuickStartDestinationStep'
import QuickStartFoldersStep from './steps/QuickStartFoldersStep'
import QuickStartProtectStep from './steps/QuickStartProtectStep'
import QuickStartReviewStep from './steps/QuickStartReviewStep'
import QuickStartScheduleStep from './steps/QuickStartScheduleStep'
import QuickStartWhatStep from './steps/QuickStartWhatStep'

const filled: QuickStartAnswers = {
  ...createInitialQuickStartAnswers(),
  sourcePaths: ['/local/home/alex', '/local/etc'],
  destinationPath: '/local/borg-backups/alex',
  name: 'alex',
  passphrase: 'correct horse battery',
  passphraseConfirm: 'correct horse battery',
  passphraseSaved: true,
  timezone: 'Europe/Berlin',
}

const nas: SshConnectionSummary = {
  id: 3,
  host: 'nas.local',
  username: 'backup',
  port: 22,
  ssh_key_id: 1,
  default_path: '/volume1',
  status: 'connected',
}

const laptop = {
  id: 7,
  name: 'alex-laptop',
  hostname: 'alex-laptop.local',
  status: 'online',
  default_path: '/home/alex',
}

const NO_CONNECTIONS: SshConnectionSummary[] = []
const NO_DETECTIONS: AppDetection[] = []
const INSPECT_OK = { root_status: 'ok', user: 'root', folders: immichStats, warnings: [] }

const immichAnswers: QuickStartAnswers = {
  ...createInitialQuickStartAnswers(),
  appChoice: 'app',
  app: immichTemplate,
  appExcludes: ['thumbs', 'encoded-video'],
  schedulePreset: 'custom',
  cronExpression: immichTemplate.schedule_cron,
}

function StepHarness({
  step: Step,
  initial,
  connections = NO_CONNECTIONS,
  detections = NO_DETECTIONS,
  inspect = INSPECT_OK,
}: {
  step: ComponentType<QuickStartStepProps>
  initial: QuickStartAnswers
  connections?: SshConnectionSummary[]
  detections?: AppDetection[]
  inspect?: object
}) {
  const [answers, setAnswers] = useState(initial)
  const [ready, setReady] = useState(false)
  useEffect(() => {
    const mock = new MockAdapter(api)
    mock.onGet('/ssh-keys/connections').reply(200, { connections })
    mock.onGet('/managed-machines/agents').reply(200, [laptop])
    // A machine without a saved default path is asked where its login lands.
    mock.onGet('/filesystem/ssh-home').reply(200, { path: '/home/backup' })
    mock.onGet('/source-discovery/apps').reply(200, { templates: [immichTemplate] })
    mock.onPost('/source-discovery/apps/detect').reply(200, { detections, warnings: [] })
    mock.onPost('/source-discovery/apps/inspect').reply(200, inspect)
    setReady(true)
    return () => mock.restore()
  }, [connections, detections, inspect])
  if (!ready) return null
  return (
    <Box sx={{ width: { xs: '100%', sm: 640 }, p: 2 }}>
      <Step
        answers={answers}
        onChange={(patch) => setAnswers((prev) => ({ ...prev, ...patch }))}
        canAddMachine
      />
    </Box>
  )
}

function ReviewHarness({
  initial,
  connections = NO_CONNECTIONS,
}: {
  initial: QuickStartAnswers
  connections?: SshConnectionSummary[]
}) {
  const [answers, setAnswers] = useState(initial)
  const [ready, setReady] = useState(false)
  const onSettingsChange = useCallback<QuickStartSettingsChange>(
    (patch) => setAnswers((prev) => ({ ...prev, settings: { ...prev.settings, ...patch } })),
    []
  )
  useEffect(() => {
    const mock = new MockAdapter(api)
    mock.onGet('/ssh-keys/connections').reply(200, { connections })
    setReady(true)
    return () => mock.restore()
  }, [connections])
  if (!ready) return null
  return (
    <Box sx={{ width: { xs: '100%', sm: 640 }, p: 2 }}>
      <QuickStartReviewStep answers={answers} onSettingsChange={onSettingsChange} canUseBorg2 />
    </Box>
  )
}

const meta = {
  title: 'Quick Start/Steps',
  component: StepHarness,
  parameters: { layout: 'centered' },
} satisfies Meta<typeof StepHarness>

export default meta
type Story = StoryObj<typeof meta>

export const App: Story = {
  args: { step: QuickStartAppStep, initial: createInitialQuickStartAnswers() },
}

export const AppChosen: Story = {
  args: { step: QuickStartAppStep, initial: immichAnswers },
}

export const FoldersImmichFound: Story = {
  args: { step: QuickStartFoldersStep, initial: immichAnswers, detections: [immichFound] },
}

export const FoldersImmichNotReadable: Story = {
  args: {
    step: QuickStartFoldersStep,
    initial: immichAnswers,
    detections: [{ ...immichFound, path: '/srv/immich', readable: false }],
  },
}

// A named Docker volume on an SSH machine: the SSH user can't open it.
export const FoldersImmichNoPermission: Story = {
  args: {
    step: QuickStartFoldersStep,
    initial: immichAnswers,
    detections: [
      {
        ...immichFound,
        path: '/home/docker-data/docker/volumes/f4eacb753d47/_data',
        host_path: '/home/docker-data/docker/volumes/f4eacb753d47/_data',
      },
    ],
    inspect: { root_status: 'denied', user: 'backup', folders: [], warnings: [] },
  },
}

export const FoldersImmichNotFound: Story = {
  args: { step: QuickStartFoldersStep, initial: immichAnswers },
}

export const What: Story = {
  args: { step: QuickStartWhatStep, initial: createInitialQuickStartAnswers() },
}

export const WhatAnotherComputer: Story = {
  args: {
    step: QuickStartWhatStep,
    initial: { ...createInitialQuickStartAnswers(), sourceKind: 'ssh' },
  },
}

export const ConnectNewMachine: Story = {
  args: {
    step: QuickStartConnectStep,
    initial: { ...createInitialQuickStartAnswers(), sourceKind: 'ssh' },
  },
}

export const ConnectExistingMachine: Story = {
  args: {
    step: QuickStartConnectStep,
    initial: { ...createInitialQuickStartAnswers(), sourceKind: 'ssh', sourceConnectionId: 3 },
    connections: [nas],
  },
}

export const ConnectAgent: Story = {
  args: {
    step: QuickStartConnectStep,
    initial: {
      ...createInitialQuickStartAnswers(),
      sourceKind: 'agent',
      destinationKind: 'agent',
      sourceAgentId: 7,
    },
  },
}

export const FoldersEmpty: Story = {
  args: { step: QuickStartFoldersStep, initial: createInitialQuickStartAnswers() },
}

export const FoldersPicked: Story = {
  args: { step: QuickStartFoldersStep, initial: filled },
}

export const Destination: Story = {
  args: { step: QuickStartDestinationStep, initial: filled },
}

export const DestinationSsh: Story = {
  args: {
    step: QuickStartDestinationStep,
    initial: {
      ...filled,
      destinationKind: 'ssh',
      destinationConnectionId: 3,
      destinationPath: '/volume1/borg-backups/alex',
    },
    connections: [nas],
  },
}

export const DestinationSshNoDefaultPath: Story = {
  args: {
    step: QuickStartDestinationStep,
    initial: {
      ...filled,
      destinationKind: 'ssh',
      destinationConnectionId: 3,
      destinationPath: '',
    },
    connections: [{ ...nas, default_path: null }],
  },
}

export const DestinationAgent: Story = {
  args: {
    step: QuickStartDestinationStep,
    initial: {
      ...filled,
      sourceKind: 'agent',
      sourceAgentId: 7,
      sourcePaths: ['/home/alex/Documents'],
      destinationKind: 'agent',
      destinationPath: '/home/alex/borg-backups/documents',
    },
  },
}

export const DestinationInsideSource: Story = {
  args: {
    step: QuickStartDestinationStep,
    initial: { ...filled, destinationPath: '/local/home/alex/backups' },
  },
}

export const Protect: Story = {
  args: {
    step: QuickStartProtectStep,
    initial: { ...filled, passphraseConfirm: 'correct horse', passphraseSaved: false },
  },
}

export const Schedule: Story = {
  args: { step: QuickStartScheduleStep, initial: filled },
}

export const ScheduleCustom: Story = {
  args: {
    step: QuickStartScheduleStep,
    initial: { ...filled, schedulePreset: 'custom', cronExpression: '30 3 * * 1-5' },
  },
}

export const Review: Story = {
  args: { step: QuickStartReviewStep as never, initial: filled },
  render: (args) => <ReviewHarness initial={args.initial} />,
}

export const ReviewSshManualUnencrypted: Story = {
  args: {
    step: QuickStartReviewStep as never,
    initial: {
      ...filled,
      destinationKind: 'ssh',
      destinationConnectionId: 3,
      destinationPath: '/volume1/borg-backups/alex',
      settings: {
        ...filled.settings,
        encryption: 'none',
        scheduleEnabled: false,
        runPruneAfter: false,
        runCompactAfter: false,
        runCheckAfter: false,
      },
    },
    connections: [nas],
  },
  render: (args) => <ReviewHarness initial={args.initial} connections={args.connections} />,
}

function WhatStepWithAgents(props: QuickStartStepProps) {
  return <QuickStartWhatStep {...props} canUseAgents />
}

export const WhatAgentPro: Story = {
  args: {
    step: WhatStepWithAgents,
    initial: { ...createInitialQuickStartAnswers(), sourceKind: 'agent', destinationKind: 'agent' },
  },
}

export const ReviewImmich: Story = {
  args: {
    step: QuickStartReviewStep as never,
    initial: {
      ...filled,
      ...immichAnswers,
      appRoot: '/local/srv/immich',
      sourcePaths: ['/local/srv/immich'],
      name: 'Immich',
    },
  },
  render: (args) => <ReviewHarness initial={args.initial} />,
}

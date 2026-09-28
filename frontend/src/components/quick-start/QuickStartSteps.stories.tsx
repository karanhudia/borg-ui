import { useCallback, useState, type ComponentType } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'

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

function StepHarness({
  step: Step,
  initial,
}: {
  step: ComponentType<QuickStartStepProps>
  initial: QuickStartAnswers
}) {
  const [answers, setAnswers] = useState(initial)
  return (
    <Box sx={{ width: { xs: '100%', sm: 640 }, p: 2 }}>
      <Step answers={answers} onChange={(patch) => setAnswers((prev) => ({ ...prev, ...patch }))} />
    </Box>
  )
}

function ReviewHarness({ initial }: { initial: QuickStartAnswers }) {
  const [answers, setAnswers] = useState(initial)
  const onSettingsChange = useCallback<QuickStartSettingsChange>(
    (patch) => setAnswers((prev) => ({ ...prev, settings: { ...prev.settings, ...patch } })),
    []
  )
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

export const What: Story = {
  args: { step: QuickStartWhatStep, initial: createInitialQuickStartAnswers() },
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

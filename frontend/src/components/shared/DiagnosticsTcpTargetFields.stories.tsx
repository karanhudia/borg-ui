import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'

import DiagnosticsTcpTargetFields from './DiagnosticsTcpTargetFields'

const labels = {
  summary: 'Advanced: test another service',
  description:
    'Checks whether this machine can reach a separate service. Leave blank for normal diagnostics.',
  host: 'Service host',
  hostHelper: 'Optional service to test from this machine',
  port: 'Service port',
  portError: '1-65535',
  timeout: 'Timeout',
  timeoutHelper: 'Seconds',
  timeoutError: '0.5-15 seconds',
}

const meta = {
  title: 'Components/DiagnosticsTcpTargetFields',
  component: DiagnosticsTcpTargetFields,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof DiagnosticsTcpTargetFields>

export default meta

type Story = StoryObj<typeof meta>

function parsePort(value: string): number | null {
  const trimmed = value.trim()
  if (!/^\d+$/.test(trimmed)) return null
  const port = Number.parseInt(trimmed, 10)
  return Number.isInteger(port) && port >= 1 && port <= 65535 ? port : null
}

function parseTimeout(value: string): number | null {
  const parsed = Number.parseFloat(value.trim())
  return Number.isFinite(parsed) && parsed >= 0.5 && parsed <= 15 ? parsed : null
}

function DiagnosticsTcpTargetPreview({
  defaultExpanded = false,
  initialHost = '',
  initialPort = '',
}: {
  defaultExpanded?: boolean
  initialHost?: string
  initialPort?: string
}) {
  const [targetHost, setTargetHost] = useState(initialHost)
  const [targetPort, setTargetPort] = useState(initialPort)
  const [targetTimeout, setTargetTimeout] = useState('3')
  const hasTarget = Boolean(targetHost.trim())

  return (
    <Box sx={{ width: 640, maxWidth: 'calc(100vw - 32px)' }}>
      <DiagnosticsTcpTargetFields
        targetHost={targetHost}
        targetPort={targetPort}
        targetTimeout={targetTimeout}
        onTargetHostChange={setTargetHost}
        onTargetPortChange={setTargetPort}
        onTargetTimeoutChange={setTargetTimeout}
        hasTarget={hasTarget}
        portInvalid={hasTarget && parsePort(targetPort) === null}
        timeoutInvalid={hasTarget && parseTimeout(targetTimeout) === null}
        timeoutInputProps={{ min: 0.5, max: 15, step: 0.5 }}
        labels={labels}
        defaultExpanded={defaultExpanded}
      />
    </Box>
  )
}

export const Collapsed: Story = {
  args: {
    targetHost: '',
    targetPort: '',
    targetTimeout: '3',
    onTargetHostChange: () => {},
    onTargetPortChange: () => {},
    onTargetTimeoutChange: () => {},
    hasTarget: false,
    portInvalid: false,
    timeoutInvalid: false,
    timeoutInputProps: { min: 0.5, max: 15, step: 0.5 },
    labels,
  },
  render: () => <DiagnosticsTcpTargetPreview />,
}

export const ExpandedWithInvalidPort: Story = {
  args: {
    targetHost: 'postgres.internal',
    targetPort: '',
    targetTimeout: '3',
    onTargetHostChange: () => {},
    onTargetPortChange: () => {},
    onTargetTimeoutChange: () => {},
    hasTarget: true,
    portInvalid: true,
    timeoutInvalid: false,
    timeoutInputProps: { min: 0.5, max: 15, step: 0.5 },
    labels,
    defaultExpanded: true,
  },
  render: () => (
    <DiagnosticsTcpTargetPreview defaultExpanded initialHost="postgres.internal" initialPort="" />
  ),
}

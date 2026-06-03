import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import type { ComponentProps } from 'react'
import type { SSHConnectionDiagnosticsResponse } from '../../../services/api'
import type { SSHConnection } from '../types'
import { ConnectionDiagnosticsDialog } from './ConnectionDiagnosticsDialog'

const connection: SSHConnection = {
  id: 3,
  ssh_key_id: 7,
  ssh_key_name: 'System Backup Key',
  host: 'backup-host',
  username: 'borg',
  port: 2222,
  use_sftp_mode: false,
  use_sudo: false,
  default_path: '/srv/backups',
  ssh_path_prefix: '',
  mount_point: '',
  status: 'connected',
  last_test: '2026-06-03T16:52:00.000Z',
  last_success: '2026-06-03T16:52:00.000Z',
  storage: null,
  created_at: '2026-06-01T10:00:00.000Z',
}

const diagnosticsSuccess: SSHConnectionDiagnosticsResponse = {
  connection: {
    id: connection.id,
    host: connection.host,
    username: connection.username,
    port: connection.port,
    status: connection.status,
    last_test: connection.last_test,
    last_success: connection.last_success,
    error_message: connection.error_message ?? null,
  },
  session: { status: 'success', elapsed_ms: 12, output: '/home/borg' },
  latency: { status: 'success', elapsed_ms: 11 },
  tcp: null,
  throughput: {
    status: 'success',
    direction: 'download',
    probe_size_bytes: 262144,
    bytes_transferred: 262144,
    elapsed_ms: 31,
    mbps: 8.06,
  },
}

const diagnosticsPartialFailure: SSHConnectionDiagnosticsResponse = {
  ...diagnosticsSuccess,
  latency: { status: 'success', elapsed_ms: 14 },
  tcp: {
    target: { host: 'postgres.internal', port: 5432, timeout_seconds: 3 },
    status: 'failed',
    elapsed_ms: 5,
    error: 'connection_refused',
    message: 'Connection refused',
  },
  throughput: {
    status: 'success',
    direction: 'download',
    probe_size_bytes: 131072,
    bytes_transferred: 131072,
    elapsed_ms: 32,
    mbps: 3.91,
  },
}

const diagnosticsTimeout: SSHConnectionDiagnosticsResponse = {
  connection: {
    ...diagnosticsSuccess.connection,
    status: 'failed',
    error_message: 'Connection timed out',
  },
  session: {
    status: 'timeout',
    elapsed_ms: null,
    error: 'ssh_timeout',
    message: 'SSH diagnostics timed out after 5 seconds',
  },
  latency: {
    status: 'timeout',
    elapsed_ms: null,
    error: 'ssh_timeout',
    message: 'SSH diagnostics timed out after 5 seconds',
  },
  tcp: null,
  throughput: null,
}

const meta = {
  title: 'Remote Machines/ConnectionDiagnosticsDialog',
  component: ConnectionDiagnosticsDialog,
} satisfies Meta<typeof ConnectionDiagnosticsDialog>

export default meta

type Story = StoryObj<typeof meta>

function renderDialog(args: ComponentProps<typeof ConnectionDiagnosticsDialog>): JSX.Element {
  return (
    <Box sx={{ p: 3, bgcolor: 'background.default', minHeight: '100vh' }}>
      <ConnectionDiagnosticsDialog {...args} />
    </Box>
  )
}

export const Success: Story = {
  args: {
    open: true,
    connection,
    initialResult: diagnosticsSuccess,
    onClose: () => {},
    onRunDiagnostics: async () => diagnosticsSuccess,
  },
  render: renderDialog,
}

export const PartialTcpFailure: Story = {
  args: {
    open: true,
    connection,
    initialResult: diagnosticsPartialFailure,
    onClose: () => {},
    onRunDiagnostics: async () => diagnosticsPartialFailure,
  },
  render: renderDialog,
}

export const Timeout: Story = {
  args: {
    open: true,
    connection,
    initialResult: diagnosticsTimeout,
    onClose: () => {},
    onRunDiagnostics: async () => diagnosticsTimeout,
  },
  render: renderDialog,
}

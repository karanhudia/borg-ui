import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { Activity, CheckCircle, Gauge, Network, XCircle } from 'lucide-react'
import ResponsiveDialog from '../../../components/shared/ResponsiveDialog'
import type {
  SSHConnectionDiagnosticsProbeResult,
  SSHConnectionDiagnosticsRequest,
  SSHConnectionDiagnosticsResponse,
  SSHConnectionDiagnosticsThroughputResult,
  SSHConnectionDiagnosticsTcpResult,
} from '../../../services/api'
import type { SSHConnection } from '../types'

const DEFAULT_TIMEOUT_SECONDS = 5
const DEFAULT_TARGET_TIMEOUT_SECONDS = 3
const DEFAULT_SPEED_PROBE_BYTES = 262144

function parsePort(value: string): number | null {
  const trimmed = value.trim()
  if (!/^\d+$/.test(trimmed)) return null
  const port = Number.parseInt(trimmed, 10)
  return Number.isInteger(port) && port >= 1 && port <= 65535 ? port : null
}

function parseBoundedNumber(value: string, min: number, max: number): number | null {
  const parsed = Number.parseFloat(value.trim())
  return Number.isFinite(parsed) && parsed >= min && parsed <= max ? parsed : null
}

function parseProbeBytes(value: string): number | null {
  const parsed = Number.parseInt(value.trim(), 10)
  return Number.isInteger(parsed) && parsed >= 65536 && parsed <= 5 * 1024 * 1024
    ? parsed
    : null
}

function getTargetError(host: string, port: string, timeout: string): string | null {
  if (!host.trim()) return null
  if (parsePort(port) === null) return 'Enter a TCP port between 1 and 65535.'
  if (parseBoundedNumber(timeout, 0.5, 15) === null) {
    return 'Enter a target timeout between 0.5 and 15 seconds.'
  }
  return null
}

function formatElapsed(value?: number | null): string {
  return typeof value === 'number' ? `${Math.round(value)} ms` : 'Not reported'
}

function formatBytes(value?: number | null): string {
  if (typeof value !== 'number') return 'Not reported'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(0)} KB`
  return `${(value / 1024 / 1024).toFixed(2)} MB`
}

function probeStatusColor(
  status?: string
): 'default' | 'success' | 'error' | 'warning' | 'info' {
  if (status === 'success') return 'success'
  if (status === 'timeout') return 'warning'
  if (status === 'failed') return 'error'
  return 'default'
}

function sessionLabel(status: string): string {
  if (status === 'success') return 'SSH session healthy'
  if (status === 'timeout') return 'SSH timed out'
  return 'SSH failed'
}

function tcpLabel(status: string): string {
  if (status === 'success') return 'TCP reachable'
  if (status === 'timeout') return 'TCP timed out'
  return 'TCP failed'
}

function throughputLabel(status: string): string {
  if (status === 'success') return 'Speed probe complete'
  if (status === 'timeout') return 'Speed probe timed out'
  return 'Speed probe failed'
}

function buildPayload(
  targetHost: string,
  targetPort: string,
  targetTimeout: string,
  timeoutSeconds: string,
  speedProbeBytes: string
): SSHConnectionDiagnosticsRequest {
  const payload: SSHConnectionDiagnosticsRequest = {
    timeout_seconds: parseBoundedNumber(timeoutSeconds, 1, 30) ?? DEFAULT_TIMEOUT_SECONDS,
    speed_probe_bytes: parseProbeBytes(speedProbeBytes) ?? DEFAULT_SPEED_PROBE_BYTES,
  }
  const host = targetHost.trim()
  if (!host) return payload
  const port = parsePort(targetPort)
  const timeout = parseBoundedNumber(targetTimeout, 0.5, 15)
  if (port === null || timeout === null) return payload
  payload.target = { host, port, timeout_seconds: timeout }
  return payload
}

function DiagnosticRow({
  icon,
  title,
  status,
  value,
  detail,
}: {
  icon: ReactNode
  title: string
  status: string
  value?: string
  detail?: string | null
}) {
  return (
    <Box
      sx={{
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 1.5,
        p: 1.5,
        minWidth: 0,
      }}
    >
      <Stack direction="row" spacing={1} alignItems="flex-start">
        <Box sx={{ color: status === 'success' ? 'success.main' : 'text.secondary', mt: 0.25 }}>
          {icon}
        </Box>
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
            <Typography fontWeight={700} variant="body2">
              {title}
            </Typography>
            <Chip size="small" color={probeStatusColor(status)} label={status} />
          </Stack>
          {value && (
            <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
              {value}
            </Typography>
          )}
          {detail && (
            <Typography variant="caption" color="text.secondary" sx={{ wordBreak: 'break-word' }}>
              {detail}
            </Typography>
          )}
        </Box>
      </Stack>
    </Box>
  )
}

function errorDetail(result: SSHConnectionDiagnosticsProbeResult): string | null {
  if (!result.error && !result.message) return null
  if (result.error && result.message) return `${result.error}: ${result.message}`
  return result.error || result.message || null
}

function tcpDetail(result: SSHConnectionDiagnosticsTcpResult): string {
  const target = `${result.target.host}:${result.target.port}`
  const error = errorDetail(result)
  return error ? `${target} - ${error}` : target
}

function throughputValue(result: SSHConnectionDiagnosticsThroughputResult): string {
  if (result.status === 'success' && typeof result.mbps === 'number') {
    return `${result.mbps.toFixed(2)} MB/s`
  }
  return errorDetail(result) || 'No throughput result'
}

function throughputDetail(result: SSHConnectionDiagnosticsThroughputResult): string {
  if (result.status !== 'success') return errorDetail(result) || ''
  return `${formatBytes(result.bytes_transferred)} in ${formatElapsed(result.elapsed_ms)}`
}

export function ConnectionDiagnosticsDialog({
  connection,
  open,
  initialResult = null,
  onClose,
  onRunDiagnostics,
}: {
  connection: SSHConnection | null
  open: boolean
  initialResult?: SSHConnectionDiagnosticsResponse | null
  onClose: () => void
  onRunDiagnostics?: (
    connection: SSHConnection,
    payload: SSHConnectionDiagnosticsRequest
  ) => Promise<SSHConnectionDiagnosticsResponse>
}) {
  const { t } = useTranslation()
  const [targetHost, setTargetHost] = useState('')
  const [targetPort, setTargetPort] = useState('')
  const [targetTimeout, setTargetTimeout] = useState(String(DEFAULT_TARGET_TIMEOUT_SECONDS))
  const [timeoutSeconds, setTimeoutSeconds] = useState(String(DEFAULT_TIMEOUT_SECONDS))
  const [speedProbeBytes, setSpeedProbeBytes] = useState(String(DEFAULT_SPEED_PROBE_BYTES))
  const [result, setResult] = useState<SSHConnectionDiagnosticsResponse | null>(initialResult)
  const [running, setRunning] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setResult(initialResult)
    setRunning(false)
    setErrorMessage(null)
  }, [initialResult, open])

  const targetError = getTargetError(targetHost, targetPort, targetTimeout)
  const timeoutError =
    parseBoundedNumber(timeoutSeconds, 1, 30) === null
      ? 'Enter an SSH timeout between 1 and 30 seconds.'
      : null
  const speedError =
    parseProbeBytes(speedProbeBytes) === null
      ? 'Enter a speed probe size between 65536 and 5242880 bytes.'
      : null
  const formError = targetError || timeoutError || speedError

  const runDiagnostics = async () => {
    if (!connection || !onRunDiagnostics || formError) return
    setRunning(true)
    setErrorMessage(null)
    try {
      const nextResult = await onRunDiagnostics(
        connection,
        buildPayload(targetHost, targetPort, targetTimeout, timeoutSeconds, speedProbeBytes)
      )
      setResult(nextResult)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to run diagnostics')
    } finally {
      setRunning(false)
    }
  }

  const footer = (
    <DialogActions sx={{ px: 3, py: 2 }}>
      <Button onClick={onClose}>{t('common.buttons.close', { defaultValue: 'Close' })}</Button>
      <Button
        variant="contained"
        onClick={() => void runDiagnostics()}
        disabled={!connection || !onRunDiagnostics || running || Boolean(formError)}
        startIcon={
          running ? <CircularProgress color="inherit" size={16} /> : <Activity size={16} />
        }
      >
        {running
          ? t('sshConnections.diagnostics.running')
          : t('sshConnections.diagnostics.runCheck')}
      </Button>
    </DialogActions>
  )

  return (
    <ResponsiveDialog open={open} onClose={onClose} fullWidth maxWidth="md" footer={footer}>
      <DialogTitle>{t('sshConnections.diagnostics.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2.25} sx={{ pt: 0.5, pb: 1 }}>
          <Box>
            <Typography fontWeight={700}>
              {connection
                ? `${connection.username}@${connection.host}:${connection.port}`
                : t('sshConnections.diagnostics.noConnection')}
            </Typography>
            <Typography color="text.secondary" variant="body2" sx={{ mt: 0.25 }}>
              {t('sshConnections.diagnostics.description')}
            </Typography>
          </Box>

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', sm: 'minmax(0, 1fr) 120px 150px' },
              gap: 1.25,
            }}
          >
            <TextField
              label={t('sshConnections.diagnostics.targetHost')}
              value={targetHost}
              onChange={(event) => setTargetHost(event.target.value)}
              placeholder="postgres.internal"
              size="small"
              helperText={t('sshConnections.diagnostics.targetHostHelper')}
            />
            <TextField
              label={t('sshConnections.diagnostics.targetPort')}
              value={targetPort}
              onChange={(event) => setTargetPort(event.target.value)}
              placeholder="5432"
              size="small"
              type="number"
              inputProps={{ min: 1, max: 65535 }}
              error={Boolean(targetHost.trim()) && parsePort(targetPort) === null}
            />
            <TextField
              label={t('sshConnections.diagnostics.targetTimeout')}
              value={targetTimeout}
              onChange={(event) => setTargetTimeout(event.target.value)}
              size="small"
              type="number"
              inputProps={{ min: 0.5, max: 15, step: 0.5 }}
              error={
                Boolean(targetHost.trim()) &&
                parseBoundedNumber(targetTimeout, 0.5, 15) === null
              }
              helperText={t('sshConnections.diagnostics.seconds')}
            />
          </Box>

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', sm: '160px 1fr' },
              gap: 1.25,
            }}
          >
            <TextField
              label={t('sshConnections.diagnostics.sshTimeout')}
              value={timeoutSeconds}
              onChange={(event) => setTimeoutSeconds(event.target.value)}
              size="small"
              type="number"
              inputProps={{ min: 1, max: 30, step: 1 }}
              error={Boolean(timeoutError)}
              helperText={t('sshConnections.diagnostics.seconds')}
            />
            <TextField
              label={t('sshConnections.diagnostics.speedProbeSize')}
              value={speedProbeBytes}
              onChange={(event) => setSpeedProbeBytes(event.target.value)}
              size="small"
              type="number"
              inputProps={{ min: 65536, max: 5 * 1024 * 1024, step: 65536 }}
              error={Boolean(speedError)}
              helperText={t('sshConnections.diagnostics.speedProbeHelper')}
            />
          </Box>

          {formError && (
            <Alert severity="warning" role="alert" sx={{ borderRadius: 1.5 }}>
              {formError}
            </Alert>
          )}

          {errorMessage && (
            <Alert severity="error" role="alert" sx={{ borderRadius: 1.5 }}>
              {errorMessage}
            </Alert>
          )}

          {result && (
            <Stack spacing={1.25}>
              <DiagnosticRow
                icon={<CheckCircle size={18} />}
                title={sessionLabel(result.session.status)}
                status={result.session.status}
                value={formatElapsed(result.session.elapsed_ms)}
                detail={errorDetail(result.session) || result.session.output}
              />
              <DiagnosticRow
                icon={<Activity size={18} />}
                title={t('sshConnections.diagnostics.latency')}
                status={result.latency.status}
                value={formatElapsed(result.latency.elapsed_ms)}
                detail={errorDetail(result.latency)}
              />
              {result.tcp && (
                <DiagnosticRow
                  icon={<Network size={18} />}
                  title={tcpLabel(result.tcp.status)}
                  status={result.tcp.status}
                  value={formatElapsed(result.tcp.elapsed_ms)}
                  detail={tcpDetail(result.tcp)}
                />
              )}
              {result.throughput && (
                <DiagnosticRow
                  icon={
                    result.throughput.status === 'success' ? (
                      <Gauge size={18} />
                    ) : (
                      <XCircle size={18} />
                    )
                  }
                  title={throughputLabel(result.throughput.status)}
                  status={result.throughput.status}
                  value={throughputValue(result.throughput)}
                  detail={throughputDetail(result.throughput)}
                />
              )}
            </Stack>
          )}
        </Stack>
      </DialogContent>
    </ResponsiveDialog>
  )
}

import { useMemo, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import {
  Alert,
  alpha,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Link as MuiLink,
  LinearProgress,
  Paper,
  Skeleton,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material'
import {
  AlertTriangle,
  Ban,
  CheckCircle,
  Copy,
  Info,
  Plus,
  RefreshCw,
  Terminal,
  XCircle,
} from 'lucide-react'
import {
  AgentEnrollmentTokenSummary,
  AgentJobLogEntryResponse,
  AgentJobResponse,
  AgentMachineResponse,
  managedAgentsAPI,
  settingsAPI,
} from '../services/api'
import { useAuth } from '../hooks/useAuth'
import { getApiErrorDetail } from '../utils/apiErrors'
import { translateBackendKey } from '../utils/translateBackendKey'
import PageTabs from '../components/PageTabs'

type PageTab = 'agents' | 'jobs' | 'tokens'

const FINAL_JOB_STATUSES = new Set(['completed', 'failed', 'canceled'])
const EMPTY_AGENTS: AgentMachineResponse[] = []
const EMPTY_TOKENS: AgentEnrollmentTokenSummary[] = []
const EMPTY_JOBS: AgentJobResponse[] = []
const EMPTY_LOGS: AgentJobLogEntryResponse[] = []

function formatDate(value?: string | null): string {
  if (!value) return 'Never'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function statusChipColor(
  status: string
): 'default' | 'primary' | 'success' | 'error' | 'warning' | 'info' {
  switch (status) {
    case 'online':
    case 'completed':
      return 'success'
    case 'running':
    case 'claimed':
      return 'info'
    case 'queued':
    case 'pending':
      return 'default'
    case 'cancel_requested':
      return 'warning'
    case 'failed':
    case 'revoked':
    case 'disabled':
      return 'error'
    default:
      return 'default'
  }
}

function getAgentLabel(agent?: AgentMachineResponse): string {
  if (!agent) return 'Unknown agent'
  return agent.hostname || agent.name || agent.agent_id
}

function getJobKind(job: AgentJobResponse): string {
  const payloadKind = job.payload?.job_kind
  return typeof payloadKind === 'string' ? payloadKind : job.job_type
}

function extractBackendMessage(error: unknown, fallback: string): string {
  return translateBackendKey(getApiErrorDetail(error)) || fallback
}

export default function ManagedAgents() {
  const queryClient = useQueryClient()
  const { hasGlobalPermission } = useAuth()
  const canManageAgents = hasGlobalPermission('settings.ssh.manage')
  const [activeTab, setActiveTab] = useState<PageTab>('agents')
  const [enrollmentDialogOpen, setEnrollmentDialogOpen] = useState(false)
  const [tokenName, setTokenName] = useState('Agent enrollment')
  const [tokenExpiryMinutes, setTokenExpiryMinutes] = useState(60)
  const [createdToken, setCreatedToken] = useState<string | null>(null)
  const [logsJob, setLogsJob] = useState<AgentJobResponse | null>(null)

  const settingsQuery = useQuery({
    queryKey: ['systemSettings'],
    queryFn: async () => {
      const response = await settingsAPI.getSystemSettings()
      return response.data
    },
    enabled: canManageAgents,
  })
  const managedAgentsBetaEnabled =
    settingsQuery.data?.settings?.managed_agents_beta_enabled ?? false
  const canUseManagedAgents = canManageAgents && managedAgentsBetaEnabled

  const agentsQuery = useQuery({
    queryKey: ['managed-agents'],
    queryFn: managedAgentsAPI.listAgents,
    enabled: canUseManagedAgents,
    refetchInterval: 15000,
  })

  const tokensQuery = useQuery({
    queryKey: ['managed-agent-enrollment-tokens'],
    queryFn: managedAgentsAPI.listEnrollmentTokens,
    enabled: canUseManagedAgents,
  })

  const jobsQuery = useQuery({
    queryKey: ['managed-agent-jobs'],
    queryFn: managedAgentsAPI.listJobs,
    enabled: canUseManagedAgents,
    refetchInterval: 5000,
  })

  const logsQuery = useQuery({
    queryKey: ['managed-agent-job-logs', logsJob?.id],
    queryFn: () => managedAgentsAPI.listJobLogs(logsJob!.id),
    enabled: canUseManagedAgents && !!logsJob,
    refetchInterval: logsJob && !FINAL_JOB_STATUSES.has(logsJob.status) ? 2000 : false,
  })

  const agents = agentsQuery.data?.data ?? EMPTY_AGENTS
  const tokens = tokensQuery.data?.data ?? EMPTY_TOKENS
  const jobs = jobsQuery.data?.data ?? EMPTY_JOBS
  const logs = logsQuery.data?.data ?? EMPTY_LOGS

  const agentsById = useMemo(() => {
    return new Map(agents.map((agent) => [agent.id, agent]))
  }, [agents])

  const refreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ['managed-agents'] })
    queryClient.invalidateQueries({ queryKey: ['managed-agent-enrollment-tokens'] })
    queryClient.invalidateQueries({ queryKey: ['managed-agent-jobs'] })
  }

  const createEnrollmentMutation = useMutation({
    mutationFn: managedAgentsAPI.createEnrollmentToken,
    onSuccess: (response) => {
      setCreatedToken(response.data.token)
      queryClient.invalidateQueries({ queryKey: ['managed-agent-enrollment-tokens'] })
      toast.success('Enrollment token created')
    },
    onError: (error: unknown) => {
      toast.error(extractBackendMessage(error, 'Failed to create enrollment token'))
    },
  })

  const revokeEnrollmentMutation = useMutation({
    mutationFn: managedAgentsAPI.revokeEnrollmentToken,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['managed-agent-enrollment-tokens'] })
      toast.success('Enrollment token revoked')
    },
    onError: (error: unknown) => {
      toast.error(extractBackendMessage(error, 'Failed to revoke enrollment token'))
    },
  })

  const revokeAgentMutation = useMutation({
    mutationFn: managedAgentsAPI.revokeAgent,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['managed-agents'] })
      toast.success('Agent revoked')
    },
    onError: (error: unknown) => {
      toast.error(extractBackendMessage(error, 'Failed to revoke agent'))
    },
  })

  const cancelJobMutation = useMutation({
    mutationFn: managedAgentsAPI.cancelJob,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['managed-agent-jobs'] })
      toast.success('Cancellation requested')
    },
    onError: (error: unknown) => {
      toast.error(extractBackendMessage(error, 'Failed to cancel job'))
    },
  })

  if (!canManageAgents) {
    return <Navigate to="/dashboard" replace />
  }

  if (!settingsQuery.isLoading && !managedAgentsBetaEnabled) {
    return <Navigate to="/dashboard" replace />
  }

  const handleCreateEnrollmentToken = () => {
    createEnrollmentMutation.mutate({
      name: tokenName,
      expires_in_minutes: tokenExpiryMinutes,
    })
  }

  const handleCopy = async (value: string) => {
    await navigator.clipboard.writeText(value)
    toast.success('Copied')
  }

  const registrationCommand = createdToken
    ? `borg-ui-agent register --server ${window.location.origin} --token ${createdToken} --name <machine-name>`
    : ''
  const setupCommand = `borg-ui-agent register --server ${window.location.origin} --token <enrollment-token> --name <machine-name>`

  const isLoading =
    settingsQuery.isLoading || agentsQuery.isLoading || tokensQuery.isLoading || jobsQuery.isLoading

  return (
    <Box>
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={2}
        justifyContent="space-between"
        alignItems={{ xs: 'stretch', md: 'center' }}
        sx={{ mb: 3 }}
      >
        <Box>
          <Typography variant="h4" fontWeight={700}>
            Managed Agents
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5 }}>
            Lightweight machines connected to this Borg UI server
          </Typography>
        </Box>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <Tooltip title="Refresh">
            <IconButton
              onClick={refreshAll}
              sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1.5 }}
            >
              <RefreshCw size={18} />
            </IconButton>
          </Tooltip>
          <Button
            variant="contained"
            startIcon={<Plus size={18} />}
            onClick={() => {
              setCreatedToken(null)
              setEnrollmentDialogOpen(true)
            }}
          >
            Create Enrollment Token
          </Button>
        </Stack>
      </Stack>

      <AgentSetupGuide command={setupCommand} onCopy={handleCopy} />

      <PageTabs value={activeTab} onChange={(_, value: PageTab) => setActiveTab(value)}>
        <Tab label="Agents" value="agents" />
        <Tab label="Jobs" value="jobs" />
        <Tab label="Enrollment Tokens" value="tokens" />
      </PageTabs>

      {isLoading ? (
        <Stack spacing={2}>
          {[0, 1, 2].map((index) => (
            <Skeleton key={index} variant="rounded" height={96} sx={{ borderRadius: 2 }} />
          ))}
        </Stack>
      ) : null}

      {!isLoading && activeTab === 'agents' ? (
        <AgentList
          agents={agents}
          onRevoke={(agent) => revokeAgentMutation.mutate(agent.id)}
          isRevoking={revokeAgentMutation.isPending}
        />
      ) : null}

      {!isLoading && activeTab === 'jobs' ? (
        <JobsTable
          jobs={jobs}
          agentsById={agentsById}
          onCancel={(job) => cancelJobMutation.mutate(job.id)}
          onViewLogs={setLogsJob}
          isCanceling={cancelJobMutation.isPending}
        />
      ) : null}

      {!isLoading && activeTab === 'tokens' ? (
        <TokensTable
          tokens={tokens}
          onRevoke={(tokenId) => revokeEnrollmentMutation.mutate(tokenId)}
          isRevoking={revokeEnrollmentMutation.isPending}
        />
      ) : null}

      <Dialog
        open={enrollmentDialogOpen}
        onClose={() => setEnrollmentDialogOpen(false)}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle>Create Enrollment Token</DialogTitle>
        <DialogContent>
          <Stack spacing={2.5} sx={{ mt: 1 }}>
            <TextField
              label="Name"
              value={tokenName}
              onChange={(event) => setTokenName(event.target.value)}
              fullWidth
            />
            <TextField
              label="Expires In Minutes"
              type="number"
              value={tokenExpiryMinutes}
              onChange={(event) => setTokenExpiryMinutes(Number(event.target.value))}
              inputProps={{ min: 1, max: 43200 }}
              fullWidth
            />
            {createdToken ? (
              <Box>
                <Typography variant="caption" color="text.secondary" fontWeight={700}>
                  Token
                </Typography>
                <Box sx={{ mt: 0.75, mb: 2 }}>
                  <CopyableCodeBlock
                    value={createdToken}
                    copyLabel="Copy token"
                    onCopy={() => handleCopy(createdToken)}
                  />
                </Box>
                <Typography variant="caption" color="text.secondary" fontWeight={700}>
                  Command
                </Typography>
                <Box sx={{ mt: 0.75 }}>
                  <CopyableCodeBlock
                    value={registrationCommand}
                    copyLabel="Copy command"
                    onCopy={() => handleCopy(registrationCommand)}
                  />
                </Box>
              </Box>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEnrollmentDialogOpen(false)}>Close</Button>
          <Button
            variant="contained"
            onClick={handleCreateEnrollmentToken}
            disabled={createEnrollmentMutation.isPending}
          >
            Create
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!logsJob} onClose={() => setLogsJob(null)} fullWidth maxWidth="lg">
        <DialogTitle>Agent Job Logs</DialogTitle>
        <DialogContent>
          <Box
            component="pre"
            sx={{
              m: 0,
              p: 2,
              minHeight: 320,
              maxHeight: '60vh',
              overflow: 'auto',
              borderRadius: 1.5,
              bgcolor: '#111827',
              color: '#d1d5db',
              fontSize: '0.8rem',
              lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
            }}
          >
            {logsQuery.isLoading
              ? 'Loading...'
              : logs.length
                ? logs.map((log) => `${log.sequence} ${log.stream}: ${log.message}`).join('\n')
                : 'No logs'}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLogsJob(null)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export function AgentSetupGuide({
  command,
  onCopy,
}: {
  command: string
  onCopy: (value: string) => void
}) {
  const [helpOpen, setHelpOpen] = useState(false)

  return (
    <Box sx={{ mb: 3 }}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1}
        alignItems={{ xs: 'stretch', sm: 'center' }}
        justifyContent="space-between"
        sx={{ mb: 1 }}
      >
        <Stack direction="row" spacing={1} alignItems="center" color="text.secondary">
          <Terminal size={16} />
          <Typography variant="body2">
            Run this on a remote machine to register it with this Borg UI server.
          </Typography>
        </Stack>
        <Button
          variant="text"
          size="small"
          startIcon={<Info size={16} />}
          onClick={() => setHelpOpen(true)}
        >
          Setup Help
        </Button>
      </Stack>

      <CopyableCodeBlock
        value={command}
        copyLabel="Copy setup command"
        onCopy={() => onCopy(command)}
      />

      <Dialog open={helpOpen} onClose={() => setHelpOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Agent Setup Help</DialogTitle>
        <DialogContent>
          <AgentSetupHelpContent command={command} onCopy={onCopy} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHelpOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export function AgentSetupHelpContent({
  command,
  onCopy,
}: {
  command: string
  onCopy: (value: string) => void
}) {
  const installCommand = [
    'git clone https://github.com/karanhudia/borg-ui.git',
    'cd borg-ui',
    'python3.11 -m venv .venv',
    '. .venv/bin/activate',
    'pip install .',
  ].join('\n')
  const runCommand = 'borg-ui-agent run'
  const linuxStartupCommand = [
    'sudo cp agent/install/systemd/borg-ui-agent.service /etc/systemd/system/',
    'sudo systemctl daemon-reload',
    'sudo systemctl enable --now borg-ui-agent',
  ].join('\n')

  return (
    <Stack spacing={2.5} sx={{ mt: 1 }}>
      <Box>
        <Typography variant="subtitle2" fontWeight={700} gutterBottom>
          1. Install on the client machine
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 1 }}>
          Run this on the machine that owns the files Borg should back up. The agent source is in
          the{' '}
          <MuiLink
            href="https://github.com/karanhudia/borg-ui/tree/main/agent"
            target="_blank"
            rel="noreferrer"
          >
            Borg UI agent directory
          </MuiLink>
          .
        </Typography>
        <CopyableCodeBlock
          value={installCommand}
          copyLabel="Copy install commands"
          onCopy={() => onCopy(installCommand)}
        />
      </Box>

      <Box>
        <Typography variant="subtitle2" fontWeight={700} gutterBottom>
          2. Register with Borg UI
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 1 }}>
          Replace the token with the enrollment token you created above. The server URL must be
          reachable from the client machine. localhost:7879 is only correct when the agent runs on
          the same machine as Borg UI; remote clients should use the Borg UI host name, IP address,
          or HTTPS URL they can reach.
        </Typography>
        <CopyableCodeBlock
          value={command}
          copyLabel="Copy setup command"
          onCopy={() => onCopy(command)}
        />
      </Box>

      <Box>
        <Typography variant="subtitle2" fontWeight={700} gutterBottom>
          3. Start now or on boot
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 1 }}>
          Use systemd on Linux or launchd on macOS for long-running clients. Edit the bundled
          template paths to match your virtualenv and config path before enabling the service.
        </Typography>
        <CopyableCodeBlock
          value={runCommand}
          copyLabel="Copy run command"
          onCopy={() => onCopy(runCommand)}
        />
        <Box sx={{ mt: 1 }}>
          <CopyableCodeBlock
            value={linuxStartupCommand}
            copyLabel="Copy systemd commands"
            onCopy={() => onCopy(linuxStartupCommand)}
          />
        </Box>
      </Box>
    </Stack>
  )
}

function CopyableCodeBlock({
  value,
  copyLabel,
  onCopy,
}: {
  value: string
  copyLabel: string
  onCopy: () => void
}) {
  return (
    <Box sx={{ position: 'relative', minWidth: 0 }}>
      <Box
        component="code"
        sx={{
          display: 'block',
          p: 1.5,
          pr: 5.5,
          borderRadius: 1,
          border: '1px solid',
          borderColor: 'divider',
          bgcolor: 'action.hover',
          color: 'text.primary',
          overflowX: 'auto',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          fontSize: '0.8rem',
          fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
        }}
      >
        {value}
      </Box>
      <Tooltip title={copyLabel}>
        <IconButton
          aria-label={copyLabel}
          size="small"
          onClick={onCopy}
          sx={{
            position: 'absolute',
            top: 8,
            right: 8,
            border: '1px solid',
            borderColor: 'divider',
            bgcolor: 'background.paper',
            '&:hover': { bgcolor: 'background.default' },
          }}
        >
          <Copy size={16} />
        </IconButton>
      </Tooltip>
    </Box>
  )
}

const AGENT_STATUS_ACCENT: Record<string, string> = {
  online: '#059669',
  offline: '#6b7280',
  revoked: '#ef4444',
  disabled: '#ef4444',
}

const getAgentStatusAccent = (status: string) => AGENT_STATUS_ACCENT[status] ?? '#6b7280'

const getAgentStatusIcon = (status: string) => {
  switch (status) {
    case 'online':
      return <CheckCircle size={13} />
    case 'revoked':
    case 'disabled':
      return <XCircle size={13} />
    default:
      return <AlertTriangle size={13} />
  }
}

export function AgentList({
  agents,
  onRevoke,
  isRevoking,
}: {
  agents: AgentMachineResponse[]
  onRevoke: (agent: AgentMachineResponse) => void
  isRevoking: boolean
}) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  if (!agents.length) {
    return <Alert severity="info">No agents enrolled.</Alert>
  }

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', lg: 'repeat(2, minmax(0, 1fr))' },
        gap: 2,
      }}
    >
      {agents.map((agent) => {
        const accent = getAgentStatusAccent(agent.status)
        const borgValue = agent.borg_versions?.length
          ? agent.borg_versions
              .map((binary) => String(binary.version || binary.path || 'borg'))
              .join(', ')
          : '—'
        const stats = [
          { label: 'OS', value: [agent.os, agent.arch].filter(Boolean).join(' / ') || '—' },
          { label: 'Agent', value: agent.agent_version || '—' },
          { label: 'Last Seen', value: formatDate(agent.last_seen_at) },
          { label: 'Borg', value: borgValue },
        ]

        return (
          <Box
            key={agent.id}
            sx={{
              width: '100%',
              display: 'flex',
              flexDirection: 'column',
              borderRadius: 2,
              bgcolor: 'background.paper',
              boxShadow: isDark
                ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 4px 16px ${alpha('#000', 0.25)}`
                : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 8px ${alpha('#000', 0.07)}`,
              transition: 'all 200ms cubic-bezier(0.16,1,0.3,1)',
              '&:hover': {
                transform: 'translateY(-2px)',
                boxShadow: isDark
                  ? `0 0 0 1px ${alpha(accent, 0.4)}, 0 8px 24px ${alpha('#000', 0.3)}, 0 2px 8px ${alpha(accent, 0.1)}`
                  : `0 0 0 1px ${alpha(accent, 0.3)}, 0 8px 24px ${alpha('#000', 0.12)}, 0 2px 8px ${alpha(accent, 0.08)}`,
              },
            }}
          >
            <Box
              sx={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                px: { xs: 1.75, sm: 2 },
                pt: { xs: 1.75, sm: 2 },
                pb: { xs: 1.5, sm: 1.75 },
              }}
            >
              <Box sx={{ mb: 1.5 }}>
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    mb: 0.5,
                  }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <Box sx={{ color: accent, display: 'flex', alignItems: 'center' }}>
                      {getAgentStatusIcon(agent.status)}
                    </Box>
                    <Typography
                      sx={{
                        fontSize: '0.6rem',
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        letterSpacing: '0.08em',
                        color: alpha(accent, 0.9),
                        lineHeight: 1,
                      }}
                    >
                      {agent.status}
                    </Typography>
                  </Box>
                  {agent.agent_version && (
                    <Typography
                      sx={{
                        fontSize: '0.58rem',
                        fontWeight: 500,
                        color: 'text.disabled',
                        letterSpacing: '0.02em',
                        flexShrink: 0,
                      }}
                    >
                      v{agent.agent_version}
                    </Typography>
                  )}
                </Box>

                <Typography
                  variant="subtitle1"
                  fontWeight={700}
                  noWrap
                  title={getAgentLabel(agent)}
                  sx={{ lineHeight: 1.3, mb: 0.25 }}
                >
                  {getAgentLabel(agent)}
                </Typography>

                <Typography
                  noWrap
                  title={agent.agent_id}
                  sx={{
                    fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
                    fontSize: '0.7rem',
                    color: 'text.disabled',
                  }}
                >
                  {agent.agent_id}
                </Typography>
              </Box>

              <Box
                sx={{
                  borderRadius: 1.5,
                  border: '1px solid',
                  borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                  overflow: 'hidden',
                  mb: 1.5,
                  bgcolor: isDark ? alpha('#fff', 0.025) : alpha('#000', 0.018),
                }}
              >
                <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)' }}>
                  {stats.map((stat, i) => (
                    <Box
                      key={stat.label}
                      sx={{
                        px: { xs: 1.25, sm: 1.5 },
                        py: { xs: 1.25, sm: 1 },
                        borderRight: i % 2 === 0 ? '1px solid' : 0,
                        borderBottom: i < 2 ? '1px solid' : 0,
                        borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                        minWidth: 0,
                      }}
                    >
                      <Typography
                        noWrap
                        sx={{
                          fontSize: '0.6rem',
                          fontWeight: 700,
                          textTransform: 'uppercase',
                          letterSpacing: '0.06em',
                          color: 'text.disabled',
                          lineHeight: 1,
                          mb: 0.5,
                        }}
                      >
                        {stat.label}
                      </Typography>
                      <Typography
                        noWrap
                        title={stat.value}
                        sx={{
                          fontSize: { xs: '0.82rem', sm: '0.78rem' },
                          fontWeight: 600,
                          fontVariantNumeric: 'tabular-nums',
                          lineHeight: 1.2,
                        }}
                      >
                        {stat.value}
                      </Typography>
                    </Box>
                  ))}
                </Box>
              </Box>

              {agent.last_error && (
                <Box
                  sx={{
                    mb: 1.5,
                    px: 1.25,
                    py: 0.875,
                    bgcolor: alpha(theme.palette.error.main, isDark ? 0.1 : 0.06),
                    borderRadius: 1.5,
                    border: '1px solid',
                    borderColor: alpha(theme.palette.error.main, 0.25),
                  }}
                >
                  <Typography
                    sx={{
                      fontSize: '0.7rem',
                      color: 'error.main',
                      wordBreak: 'break-word',
                      lineHeight: 1.4,
                    }}
                  >
                    {agent.last_error}
                  </Typography>
                </Box>
              )}

              <Box
                sx={{
                  mt: 'auto',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'flex-end',
                  pt: { xs: 1.5, sm: 1.25 },
                  borderTop: '1px solid',
                  borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                }}
              >
                <Tooltip title="Revoke agent" arrow>
                  <span>
                    <IconButton
                      size="small"
                      aria-label="Revoke agent"
                      onClick={() => onRevoke(agent)}
                      disabled={isRevoking || agent.status === 'revoked'}
                      sx={{
                        width: { xs: 40, sm: 34 },
                        height: { xs: 40, sm: 34 },
                        borderRadius: 1.5,
                        color: alpha(theme.palette.error.main, 0.6),
                        '&:hover': {
                          color: theme.palette.error.main,
                          bgcolor: alpha(theme.palette.error.main, isDark ? 0.15 : 0.1),
                        },
                        '&.Mui-disabled': { opacity: 0.28 },
                      }}
                    >
                      <Ban size={16} />
                    </IconButton>
                  </span>
                </Tooltip>
              </Box>
            </Box>
          </Box>
        )
      })}
    </Box>
  )
}

export function JobsTable({
  jobs,
  agentsById,
  onCancel,
  onViewLogs,
  isCanceling,
}: {
  jobs: AgentJobResponse[]
  agentsById: Map<number, AgentMachineResponse>
  onCancel: (job: AgentJobResponse) => void
  onViewLogs: (job: AgentJobResponse) => void
  isCanceling: boolean
}) {
  if (!jobs.length) {
    return <Alert severity="info">No agent jobs yet.</Alert>
  }

  return (
    <Paper variant="outlined" sx={{ borderRadius: 2, overflow: 'hidden' }}>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>Job</TableCell>
            <TableCell>Agent</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Progress</TableCell>
            <TableCell>Updated</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {jobs.map((job) => {
            const agent = agentsById.get(job.agent_machine_id)
            const canCancel = !FINAL_JOB_STATUSES.has(job.status)
            return (
              <TableRow key={job.id} hover>
                <TableCell>
                  <Typography fontWeight={700}>#{job.id}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {getJobKind(job)}
                  </Typography>
                </TableCell>
                <TableCell>{getAgentLabel(agent)}</TableCell>
                <TableCell>
                  <Chip label={job.status} color={statusChipColor(job.status)} size="small" />
                </TableCell>
                <TableCell sx={{ minWidth: 160 }}>
                  <LinearProgress
                    variant="determinate"
                    value={Math.max(0, Math.min(100, job.progress_percent ?? 0))}
                    sx={{ borderRadius: 1, height: 7 }}
                  />
                  <Typography variant="caption" color="text.secondary">
                    {Math.round(job.progress_percent ?? 0)}%
                  </Typography>
                </TableCell>
                <TableCell>{formatDate(job.updated_at)}</TableCell>
                <TableCell align="right">
                  <Tooltip title="View logs">
                    <IconButton onClick={() => onViewLogs(job)}>
                      <Terminal size={18} />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Cancel job">
                    <span>
                      <IconButton
                        color="warning"
                        onClick={() => onCancel(job)}
                        disabled={!canCancel || isCanceling}
                      >
                        <XCircle size={18} />
                      </IconButton>
                    </span>
                  </Tooltip>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </Paper>
  )
}

export function TokensTable({
  tokens,
  onRevoke,
  isRevoking,
}: {
  tokens: Array<{
    id: number
    name: string
    token_prefix: string
    expires_at: string
    used_at?: string | null
    revoked_at?: string | null
  }>
  onRevoke: (tokenId: number) => void
  isRevoking: boolean
}) {
  if (!tokens.length) {
    return <Alert severity="info">No enrollment tokens created.</Alert>
  }

  return (
    <Paper variant="outlined" sx={{ borderRadius: 2, overflow: 'hidden' }}>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>Name</TableCell>
            <TableCell>Prefix</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Expires</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {tokens.map((token) => {
            const tokenStatus = token.revoked_at ? 'revoked' : token.used_at ? 'used' : 'active'
            return (
              <TableRow key={token.id} hover>
                <TableCell>{token.name}</TableCell>
                <TableCell>
                  <Typography
                    sx={{
                      fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
                      fontSize: '0.82rem',
                    }}
                  >
                    {token.token_prefix}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Chip
                    label={tokenStatus}
                    color={tokenStatus === 'active' ? 'success' : 'default'}
                    size="small"
                  />
                </TableCell>
                <TableCell>{formatDate(token.expires_at)}</TableCell>
                <TableCell align="right">
                  <Tooltip title="Revoke token">
                    <span>
                      <IconButton
                        color="error"
                        onClick={() => onRevoke(token.id)}
                        disabled={isRevoking || tokenStatus !== 'active'}
                      >
                        <Ban size={18} />
                      </IconButton>
                    </span>
                  </Tooltip>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </Paper>
  )
}

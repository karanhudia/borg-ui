import { useCallback, useMemo, useState } from 'react'
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
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material'
import {
  AlertTriangle,
  Ban,
  CheckCircle,
  Copy,
  Eye,
  Info,
  Plus,
  RefreshCw,
  Terminal,
  Trash2,
  XCircle,
} from 'lucide-react'
import {
  AgentEnrollmentTokenSummary,
  AgentJobLogEntryResponse,
  AgentJobResponse,
  AgentMachineResponse,
  AgentSessionLogEntryResponse,
  managedAgentsAPI,
} from '../services/api'
import { useAuth } from '../hooks/useAuth'
import { usePlan } from '../hooks/usePlan'
import { getApiErrorDetail } from '../utils/apiErrors'
import { translateBackendKey } from '../utils/translateBackendKey'
import PageTabs from '../components/PageTabs'
import PageHeader from '../components/PageHeader'
import PlanGate from '../components/shared/PlanGate'
import LogViewerDialog, { type LogViewerFetchLogs } from '../components/shared/LogViewerDialog'
import AddAgentDialog from './managed-agents/AddAgentDialog'
import { resolveAgentServerUrl } from './managed-agents/agentServerUrl'
import {
  buildAgentInstallCommand,
  buildAgentReinstallCommand,
} from './managed-agents/agentInstallCommandText'
import {
  agentJobLogsToViewerResult,
  agentSessionLogsToViewerResult,
} from './managed-agents/logViewerAdapters'

type PageTab = 'agents' | 'jobs' | 'tokens'

const FINAL_JOB_STATUSES = new Set(['completed', 'failed', 'canceled'])
const EMPTY_AGENTS: AgentMachineResponse[] = []
const EMPTY_TOKENS: AgentEnrollmentTokenSummary[] = []
const EMPTY_JOBS: AgentJobResponse[] = []
const EMPTY_LOG_RESULT = { lines: [], total_lines: 0, has_more: false }

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

function formatBorgBinary(binary: Record<string, unknown>): string {
  const version = typeof binary.version === 'string' ? binary.version : null
  const path = typeof binary.path === 'string' ? binary.path : null
  const installSource = typeof binary.install_source === 'string' ? binary.install_source : null
  const label = version || path || 'borg'

  return installSource ? `${label} (${installSource})` : label
}

export default function ManagedAgents() {
  const queryClient = useQueryClient()
  const { hasGlobalPermission } = useAuth()
  const { can } = usePlan()
  const canManageAgents = hasGlobalPermission('settings.ssh.manage')
  const [activeTab, setActiveTab] = useState<PageTab>('agents')
  const [addAgentDialogOpen, setAddAgentDialogOpen] = useState(false)
  const [logsJob, setLogsJob] = useState<AgentJobResponse | null>(null)
  const [logsAgent, setLogsAgent] = useState<AgentMachineResponse | null>(null)
  const defaultAgentServerUrl = useMemo(
    () => resolveAgentServerUrl(undefined, window.location.origin),
    []
  )

  const hasManagedAgentsPlan = can('managed_agents')
  const canUseManagedAgents = canManageAgents && hasManagedAgentsPlan

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

  const agents = agentsQuery.data?.data ?? EMPTY_AGENTS
  const tokens = tokensQuery.data?.data ?? EMPTY_TOKENS
  const jobs = jobsQuery.data?.data ?? EMPTY_JOBS
  const selectedLogsJob = useMemo(
    () => (logsJob ? jobs.find((job) => job.id === logsJob.id) || logsJob : null),
    [jobs, logsJob]
  )
  const selectedLogsAgent = useMemo(
    () => (logsAgent ? agents.find((agent) => agent.id === logsAgent.id) || logsAgent : null),
    [agents, logsAgent]
  )

  const agentsById = useMemo(() => {
    return new Map(agents.map((agent) => [agent.id, agent]))
  }, [agents])

  const [manualRefreshInFlight, setManualRefreshInFlight] = useState(false)
  const refreshAll = async () => {
    setManualRefreshInFlight(true)
    try {
      await Promise.all([agentsQuery.refetch(), tokensQuery.refetch(), jobsQuery.refetch()])
    } finally {
      setManualRefreshInFlight(false)
    }
  }

  const createEnrollmentMutation = useMutation({
    mutationFn: managedAgentsAPI.createEnrollmentToken,
    onSuccess: () => {
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

  const deleteAgentMutation = useMutation({
    mutationFn: managedAgentsAPI.deleteAgent,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['managed-agents'] })
      toast.success('Agent deleted')
    },
    onError: (error: unknown) => {
      toast.error(extractBackendMessage(error, 'Failed to delete agent'))
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

  if (!hasManagedAgentsPlan) {
    return (
      <Box>
        <PageHeader
          title="Managed Agents"
          subtitle="Lightweight machines connected to this Borg UI server"
        />
        <PlanGate feature="managed_agents">
          <Box />
        </PlanGate>
      </Box>
    )
  }

  const handleCopy = async (value: string) => {
    await navigator.clipboard.writeText(value)
    toast.success('Copied')
  }

  const setupCommand = buildAgentInstallCommand(
    defaultAgentServerUrl,
    '<enrollment-token>',
    '<machine-name>'
  )

  const isLoading = agentsQuery.isLoading || tokensQuery.isLoading || jobsQuery.isLoading

  return (
    <Box>
      <PageHeader
        title="Managed Agents"
        subtitle="Lightweight machines connected to this Borg UI server"
        actions={
          <>
            <IconButton
              onClick={() => void refreshAll()}
              aria-label={manualRefreshInFlight ? 'Refreshing agents' : 'Refresh'}
              title={manualRefreshInFlight ? 'Refreshing agents' : 'Refresh'}
              disabled={manualRefreshInFlight}
            >
              <RefreshCw size={20} />
            </IconButton>
            <Button
              variant="contained"
              startIcon={<Plus size={18} />}
              onClick={() => setAddAgentDialogOpen(true)}
              sx={{ width: { xs: '100%', md: 'auto' } }}
            >
              Add Agent
            </Button>
          </>
        }
      />

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
          serverUrl={defaultAgentServerUrl}
          onCopy={handleCopy}
          onRevoke={(agent) => revokeAgentMutation.mutate(agent.id)}
          onDelete={(agent) => deleteAgentMutation.mutate(agent.id)}
          onViewLogs={setLogsAgent}
          isRevoking={revokeAgentMutation.isPending}
          isDeleting={deleteAgentMutation.isPending}
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

      <AddAgentDialog
        open={addAgentDialogOpen}
        onClose={() => setAddAgentDialogOpen(false)}
        defaultServerUrl={defaultAgentServerUrl}
        agents={agents}
        onCreateToken={async (payload) => {
          const response = await createEnrollmentMutation.mutateAsync(payload)
          return response.data
        }}
        creatingToken={createEnrollmentMutation.isPending}
        onCopy={handleCopy}
      />

      <AgentJobLogsDialog job={selectedLogsJob} onClose={() => setLogsJob(null)} />

      <AgentSessionLogsDialog agent={selectedLogsAgent} onClose={() => setLogsAgent(null)} />
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
  const manualInstallCommand = [
    'git clone https://github.com/karanhudia/borg-ui.git',
    'cd borg-ui',
    'python3.11 -m venv .venv',
    '. .venv/bin/activate',
    'pip install .',
  ].join('\n')
  const runCommand = 'sudo systemctl status borg-ui-agent'
  const linuxStartupCommand = [
    'sudo cp agent/install/systemd/borg-ui-agent.service /etc/systemd/system/',
    'sudo systemctl daemon-reload',
    'sudo systemctl enable --now borg-ui-agent',
  ].join('\n')

  return (
    <Stack spacing={2.5} sx={{ mt: 1 }}>
      <Box>
        <Typography variant="subtitle2" fontWeight={700} gutterBottom>
          1. Run the Linux installer
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 1 }}>
          Run this on the Linux machine that owns the files Borg should back up. The installer
          installs dependencies, registers the agent, and enables the systemd service. By default,
          the service runs as the user who invoked sudo, so repository and source paths must be
          accessible to that user.
        </Typography>
        <CopyableCodeBlock
          value={command}
          copyLabel="Copy install command"
          onCopy={() => onCopy(command)}
        />
      </Box>

      <Box>
        <Typography variant="subtitle2" fontWeight={700} gutterBottom>
          2. Server URL and token
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 1 }}>
          The server URL must be reachable from the client machine. localhost only works when the
          agent and Borg UI are on the same machine; remote clients should use the Borg UI host
          name, IP address, or HTTPS URL they can reach. Enrollment tokens are temporary setup
          credentials; the enrolled agent keeps its own credential until revoked or deleted.
        </Typography>
      </Box>

      <Box>
        <Typography variant="subtitle2" fontWeight={700} gutterBottom>
          3. Manual troubleshooting
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 1 }}>
          Manual installation remains useful for troubleshooting. The agent source is in the{' '}
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
          value={manualInstallCommand}
          copyLabel="Copy install commands"
          onCopy={() => onCopy(manualInstallCommand)}
        />
      </Box>

      <Box>
        <Typography variant="subtitle2" fontWeight={700} gutterBottom>
          4. Service checks
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 1 }}>
          The installer enables systemd by default so the agent survives reboot. Use these commands
          only when inspecting or repairing a manual installation.
        </Typography>
        <CopyableCodeBlock
          value={runCommand}
          copyLabel="Copy status command"
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
            color: 'primary.main',
            borderColor: (theme) => alpha(theme.palette.primary.main, 0.45),
            bgcolor: (theme) => alpha(theme.palette.primary.main, 0.08),
            '&:hover': {
              borderColor: 'primary.main',
              bgcolor: (theme) => alpha(theme.palette.primary.main, 0.14),
            },
            '&:focus-visible': {
              outline: '2px solid',
              outlineColor: 'primary.main',
              outlineOffset: 2,
            },
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

export function AgentDeleteConfirmationDialog({
  agent,
  open,
  isDeleting,
  onCancel,
  onConfirm,
}: {
  agent: AgentMachineResponse | null
  open: boolean
  isDeleting: boolean
  onCancel: () => void
  onConfirm: (agent: AgentMachineResponse) => void
}) {
  return (
    <Dialog open={open} onClose={onCancel} fullWidth maxWidth="xs">
      <DialogTitle>Delete agent</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ mt: 0.5 }}>
          <Typography fontWeight={700}>{getAgentLabel(agent || undefined)}</Typography>
          <Typography color="text.secondary">
            Deleting removes it from the fleet list. The local service may still run until removed
            on the client.
          </Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel}>Cancel</Button>
        <Button
          color="error"
          variant="contained"
          disabled={isDeleting || !agent}
          onClick={() => {
            if (!agent) return
            onConfirm(agent)
          }}
        >
          Delete agent
        </Button>
      </DialogActions>
    </Dialog>
  )
}

export function AgentReinstallDialog({
  agent,
  open,
  serverUrl,
  onCancel,
  onCopy,
}: {
  agent: AgentMachineResponse | null
  open: boolean
  serverUrl: string
  onCancel: () => void
  onCopy: (value: string) => void
}) {
  const command = buildAgentReinstallCommand(serverUrl)

  return (
    <Dialog open={open} onClose={onCancel} fullWidth maxWidth="md">
      <DialogTitle>Reinstall agent</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 0.5 }}>
          <Box>
            <Typography fontWeight={700}>{getAgentLabel(agent || undefined)}</Typography>
            <Typography color="text.secondary" sx={{ mt: 0.5 }}>
              Run this on the enrolled machine to update the Borg UI agent package and restart the
              systemd service. No enrollment token or registration step is required.
            </Typography>
          </Box>
          <CopyableCodeBlock
            value={command}
            copyLabel="Copy reinstall command"
            onCopy={() => onCopy(command)}
          />
          <Alert severity="info" sx={{ borderRadius: 1.5 }}>
            The script preserves the existing agent config at{' '}
            <Box component="code">/etc/borg-ui-agent/config.toml</Box>.
          </Alert>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel}>Close</Button>
      </DialogActions>
    </Dialog>
  )
}

export function AgentList({
  agents,
  serverUrl,
  onCopy,
  onRevoke,
  onDelete,
  onViewLogs,
  isRevoking,
  isDeleting,
}: {
  agents: AgentMachineResponse[]
  serverUrl: string
  onCopy: (value: string) => void
  onRevoke: (agent: AgentMachineResponse) => void
  onDelete: (agent: AgentMachineResponse) => void
  onViewLogs: (agent: AgentMachineResponse) => void
  isRevoking: boolean
  isDeleting: boolean
}) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const [deleteTarget, setDeleteTarget] = useState<AgentMachineResponse | null>(null)
  const [reinstallTarget, setReinstallTarget] = useState<AgentMachineResponse | null>(null)

  if (!agents.length) {
    return <Alert severity="info">No agents enrolled.</Alert>
  }

  return (
    <>
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', lg: 'repeat(2, minmax(0, 1fr))' },
          gap: 2,
        }}
      >
        {agents.map((agent) => {
          const accent = getAgentStatusAccent(agent.status)
          const borgVersions = agent.borg_versions ?? []
          const hasUsableBorg = borgVersions.length > 0
          const borgValue = hasUsableBorg ? borgVersions.map(formatBorgBinary).join(', ') : 'None'
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

                {!hasUsableBorg && (
                  <Alert
                    severity="warning"
                    icon={<AlertTriangle size={16} />}
                    sx={{
                      mb: 1.5,
                      borderRadius: 1.5,
                      border: '1px solid',
                      borderColor: alpha(theme.palette.warning.main, 0.28),
                      '& .MuiAlert-icon': { alignItems: 'center' },
                    }}
                  >
                    <Typography variant="body2" fontWeight={700}>
                      No usable Borg binary reported
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Install Borg on this agent or regenerate the setup command with Borg
                      installation enabled.
                    </Typography>
                  </Alert>
                )}

                <Box
                  sx={{
                    mt: 'auto',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'flex-end',
                    gap: 0.25,
                    pt: { xs: 1.5, sm: 1.25 },
                    borderTop: '1px solid',
                    borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                  }}
                >
                  <Tooltip title="View agent logs" arrow>
                    <IconButton
                      size="small"
                      aria-label="View agent logs"
                      onClick={() => onViewLogs(agent)}
                      sx={{
                        width: { xs: 40, sm: 34 },
                        height: { xs: 40, sm: 34 },
                        borderRadius: 1.5,
                        color: alpha(theme.palette.info.main, 0.75),
                        '&:hover': {
                          color: theme.palette.info.main,
                          bgcolor: alpha(theme.palette.info.main, isDark ? 0.15 : 0.1),
                        },
                      }}
                    >
                      <Eye size={16} />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Reinstall agent" arrow>
                    <IconButton
                      size="small"
                      aria-label="Reinstall agent"
                      onClick={() => setReinstallTarget(agent)}
                      sx={{
                        width: { xs: 40, sm: 34 },
                        height: { xs: 40, sm: 34 },
                        borderRadius: 1.5,
                        color: alpha(theme.palette.primary.main, 0.75),
                        '&:hover': {
                          color: theme.palette.primary.main,
                          bgcolor: alpha(theme.palette.primary.main, isDark ? 0.15 : 0.1),
                        },
                      }}
                    >
                      <RefreshCw size={16} />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Revoke access" arrow>
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
                  <Tooltip title="Delete agent" arrow>
                    <span>
                      <IconButton
                        size="small"
                        aria-label="Delete agent"
                        onClick={() => setDeleteTarget(agent)}
                        disabled={isDeleting}
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
                        <Trash2 size={16} />
                      </IconButton>
                    </span>
                  </Tooltip>
                </Box>
              </Box>
            </Box>
          )
        })}
      </Box>
      <AgentDeleteConfirmationDialog
        open={!!deleteTarget}
        agent={deleteTarget}
        isDeleting={isDeleting}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={(agent) => {
          onDelete(agent)
          setDeleteTarget(null)
        }}
      />
      <AgentReinstallDialog
        open={!!reinstallTarget}
        agent={reinstallTarget}
        serverUrl={serverUrl}
        onCopy={onCopy}
        onCancel={() => setReinstallTarget(null)}
      />
    </>
  )
}

export function AgentSessionLogsDialog({
  agent,
  logs,
  loading,
  onClose,
}: {
  agent: AgentMachineResponse | null
  logs?: AgentSessionLogEntryResponse[]
  loading?: boolean
  onClose: () => void
}) {
  const handleFetchLogs = useCallback<LogViewerFetchLogs>(
    async (offset: number) => {
      if (!agent || loading) return EMPTY_LOG_RESULT
      if (logs) return agentSessionLogsToViewerResult(logs, offset)

      const response = await managedAgentsAPI.listAgentLogs(agent.id)
      return agentSessionLogsToViewerResult(response.data, offset)
    },
    [agent, loading, logs]
  )

  const status = agent?.status === 'online' && !logs ? 'running' : 'completed'

  return (
    <LogViewerDialog
      job={agent ? { id: agent.id, status, type: 'agent' } : null}
      open={!!agent}
      onClose={onClose}
      title={agent ? `Agent Logs - ${getAgentLabel(agent)}` : 'Agent Logs'}
      jobTypeLabel="Agent"
      onFetchLogs={handleFetchLogs}
    />
  )
}

export function AgentJobLogsDialog({
  job,
  logs,
  onClose,
}: {
  job: AgentJobResponse | null
  logs?: AgentJobLogEntryResponse[]
  onClose: () => void
}) {
  const handleFetchLogs = useCallback<LogViewerFetchLogs>(
    async (offset: number) => {
      if (!job) return EMPTY_LOG_RESULT
      if (logs) return agentJobLogsToViewerResult(logs, offset)

      const response = await managedAgentsAPI.listJobLogs(job.id)
      return agentJobLogsToViewerResult(response.data, offset)
    },
    [job, logs]
  )

  return (
    <LogViewerDialog
      job={job ? { ...job, type: 'agent job' } : null}
      open={!!job}
      onClose={onClose}
      title={job ? `Agent Job Logs - Job #${job.id}` : 'Agent Job Logs'}
      jobTypeLabel="Agent Job"
      onFetchLogs={handleFetchLogs}
    />
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
                      <Eye size={18} />
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
    expires_at: string | null
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

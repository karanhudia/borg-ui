import { useCallback, useEffect, useMemo, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import {
  Alert,
  alpha,
  Box,
  Button,
  Chip,
  CircularProgress,
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
  Activity,
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
  AgentDiagnosticsRequest,
  AgentDiagnosticsResponse,
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
import ResponsiveDialog from '../components/shared/ResponsiveDialog'
import DiagnosticsTcpTargetFields from '../components/shared/DiagnosticsTcpTargetFields'
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
import { useAnalytics } from '../hooks/useAnalytics'
import { useFeatureAnalytics } from '../hooks/useFeatureAnalytics'

type PageTab = 'agents' | 'jobs' | 'tokens'

const FINAL_JOB_STATUSES = new Set(['completed', 'failed', 'canceled'])
const MANAGED_AGENTS_ANALYTICS_SECTION = 'managed_agents'
const EMPTY_AGENTS: AgentMachineResponse[] = []
const EMPTY_TOKENS: AgentEnrollmentTokenSummary[] = []
const EMPTY_JOBS: AgentJobResponse[] = []
const EMPTY_LOG_RESULT = { lines: [], total_lines: 0, has_more: false }

function formatDate(value: string | null | undefined, neverLabel: string): string {
  if (!value) return neverLabel
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

function getAgentLabel(agent: AgentMachineResponse | undefined, unknownLabel: string): string {
  if (!agent) return unknownLabel
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

function formatElapsedMs(value: number | null | undefined, notReportedLabel: string): string {
  if (typeof value !== 'number') return notReportedLabel
  return `${Math.round(value)} ms`
}

function parseDiagnosticsPort(value: string): number | null {
  const trimmed = value.trim()
  if (!/^\d+$/.test(trimmed)) return null
  const port = Number.parseInt(trimmed, 10)
  return Number.isInteger(port) && port >= 1 && port <= 65535 ? port : null
}

function parseDiagnosticsTimeout(value: string): number | null {
  const timeout = Number.parseFloat(value.trim())
  return Number.isFinite(timeout) && timeout >= 0.5 && timeout <= 10 ? timeout : null
}

function getDiagnosticsTargetError(
  hostValue: string,
  portValue: string,
  timeoutValue: string,
  messages: { invalidPort: string; invalidTimeout: string }
): string | null {
  if (!hostValue.trim()) return null
  if (parseDiagnosticsPort(portValue) === null) {
    return messages.invalidPort
  }
  if (parseDiagnosticsTimeout(timeoutValue) === null) {
    return messages.invalidTimeout
  }
  return null
}

function buildDiagnosticsPayload(
  hostValue: string,
  portValue: string,
  timeoutValue: string
): AgentDiagnosticsRequest {
  const host = hostValue.trim()
  if (!host) return {}
  const port = parseDiagnosticsPort(portValue)
  const timeout = parseDiagnosticsTimeout(timeoutValue)
  if (port === null || timeout === null) return {}

  return {
    target: {
      host,
      port,
      timeout_seconds: timeout,
    },
  }
}

function sessionStatusLabel(status: string, labels: Record<string, string>): string {
  switch (status) {
    case 'success':
      return labels.healthy
    case 'offline':
      return labels.offline
    case 'timeout':
      return labels.timedOut
    default:
      return labels.failed
  }
}

function tcpStatusLabel(status: string, labels: Record<string, string>): string {
  return status === 'success' ? labels.reachable : labels.failed
}

export function ManagedAgentsPreview({
  defaultAgentServerUrl,
  activeTab = 'agents',
  agents = EMPTY_AGENTS,
  tokens = EMPTY_TOKENS,
  jobs = EMPTY_JOBS,
  isLoading = false,
}: {
  defaultAgentServerUrl: string
  activeTab?: PageTab
  agents?: AgentMachineResponse[]
  tokens?: AgentEnrollmentTokenSummary[]
  jobs?: AgentJobResponse[]
  isLoading?: boolean
}) {
  const { t } = useTranslation()
  const setupCommand = buildAgentInstallCommand(
    defaultAgentServerUrl,
    '<enrollment-token>',
    '<machine-name>'
  )
  const agentsById = useMemo(() => {
    return new Map(agents.map((agent) => [agent.id, agent]))
  }, [agents])

  return (
    <Box>
      <PageHeader
        title={t('managedAgents.page.title')}
        subtitle={t('managedAgents.page.subtitle')}
        actions={
          <>
            <IconButton
              aria-label={t('managedAgents.page.refresh')}
              title={t('managedAgents.page.refresh')}
            >
              <RefreshCw size={20} />
            </IconButton>
            <Button variant="contained" startIcon={<Plus size={18} />}>
              {t('managedAgents.page.addAgent')}
            </Button>
          </>
        }
      />

      <AgentSetupGuide command={setupCommand} onCopy={() => {}} />

      <PageTabs value={activeTab} onChange={() => {}}>
        <Tab label={t('managedAgents.page.tabs.agents')} value="agents" />
        <Tab label={t('managedAgents.page.tabs.jobs')} value="jobs" />
        <Tab label={t('managedAgents.page.tabs.tokens')} value="tokens" />
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
          onCopy={() => {}}
          onRevoke={() => {}}
          onDelete={() => {}}
          onViewLogs={() => {}}
          isRevoking={false}
          isDeleting={false}
        />
      ) : null}

      {!isLoading && activeTab === 'jobs' ? (
        <JobsTable
          jobs={jobs}
          agentsById={agentsById}
          onCancel={() => {}}
          onViewLogs={() => {}}
          isCanceling={false}
        />
      ) : null}

      {!isLoading && activeTab === 'tokens' ? (
        <TokensTable tokens={tokens} onRevoke={() => {}} isRevoking={false} />
      ) : null}
    </Box>
  )
}

export function ManagedAgentsPlanGate({
  defaultAgentServerUrl,
  activeTab = 'agents',
  agents = EMPTY_AGENTS,
  tokens = EMPTY_TOKENS,
  jobs = EMPTY_JOBS,
  isLoading = false,
}: {
  defaultAgentServerUrl: string
  activeTab?: PageTab
  agents?: AgentMachineResponse[]
  tokens?: AgentEnrollmentTokenSummary[]
  jobs?: AgentJobResponse[]
  isLoading?: boolean
}) {
  const { t } = useTranslation()

  return (
    <PlanGate
      feature="managed_agents"
      message={t('managedAgents.planGate.message')}
      surface={MANAGED_AGENTS_ANALYTICS_SECTION}
      operation="view_page_gate"
      preview={
        <ManagedAgentsPreview
          defaultAgentServerUrl={defaultAgentServerUrl}
          activeTab={activeTab}
          agents={agents}
          tokens={tokens}
          jobs={jobs}
          isLoading={isLoading}
        />
      }
    >
      <Box />
    </PlanGate>
  )
}

export default function ManagedAgents() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { hasGlobalPermission } = useAuth()
  const { trackSystem, EventAction } = useAnalytics()
  const { trackFeatureUsed } = useFeatureAnalytics()
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
  const canReadManagedAgents = canManageAgents

  const agentsQuery = useQuery({
    queryKey: ['managed-agents'],
    queryFn: managedAgentsAPI.listAgents,
    enabled: canReadManagedAgents,
    refetchInterval: 15000,
  })

  const tokensQuery = useQuery({
    queryKey: ['managed-agent-enrollment-tokens'],
    queryFn: managedAgentsAPI.listEnrollmentTokens,
    enabled: canReadManagedAgents,
  })

  const jobsQuery = useQuery({
    queryKey: ['managed-agent-jobs'],
    queryFn: managedAgentsAPI.listJobs,
    enabled: canReadManagedAgents,
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
  const isLoading = agentsQuery.isLoading || tokensQuery.isLoading || jobsQuery.isLoading

  const [manualRefreshInFlight, setManualRefreshInFlight] = useState(false)
  const refreshAll = async () => {
    trackSystem(EventAction.START, {
      section: MANAGED_AGENTS_ANALYTICS_SECTION,
      operation: 'refresh',
    })
    setManualRefreshInFlight(true)
    try {
      await Promise.all([agentsQuery.refetch(), tokensQuery.refetch(), jobsQuery.refetch()])
    } finally {
      setManualRefreshInFlight(false)
    }
  }

  const createEnrollmentMutation = useMutation({
    mutationFn: managedAgentsAPI.createEnrollmentToken,
    onSuccess: (_response, payload) => {
      queryClient.invalidateQueries({ queryKey: ['managed-agent-enrollment-tokens'] })
      trackSystem(EventAction.CREATE, {
        section: MANAGED_AGENTS_ANALYTICS_SECTION,
        operation: 'create_enrollment_token',
        has_default_path: Boolean(payload.default_path),
        expires_never: Boolean(payload.expires_never),
      })
      trackFeatureUsed('managed_agents', {
        surface: MANAGED_AGENTS_ANALYTICS_SECTION,
        operation: 'create_enrollment_token',
        has_default_path: Boolean(payload.default_path),
        expires_never: Boolean(payload.expires_never),
      })
      toast.success(t('managedAgents.page.toasts.tokenCreated'))
    },
    onError: (error: unknown) => {
      toast.error(extractBackendMessage(error, t('managedAgents.add.errors.createToken')))
    },
  })

  const revokeEnrollmentMutation = useMutation({
    mutationFn: managedAgentsAPI.revokeEnrollmentToken,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['managed-agent-enrollment-tokens'] })
      trackSystem(EventAction.DELETE, {
        section: MANAGED_AGENTS_ANALYTICS_SECTION,
        operation: 'revoke_enrollment_token',
      })
      trackFeatureUsed('managed_agents', {
        surface: MANAGED_AGENTS_ANALYTICS_SECTION,
        operation: 'revoke_enrollment_token',
      })
      toast.success(t('managedAgents.page.toasts.tokenRevoked'))
    },
    onError: (error: unknown) => {
      toast.error(extractBackendMessage(error, t('managedAgents.page.errors.revokeToken')))
    },
  })

  const revokeAgentMutation = useMutation({
    mutationFn: managedAgentsAPI.revokeAgent,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['managed-agents'] })
      trackSystem(EventAction.DELETE, {
        section: MANAGED_AGENTS_ANALYTICS_SECTION,
        operation: 'revoke_agent',
      })
      trackFeatureUsed('managed_agents', {
        surface: MANAGED_AGENTS_ANALYTICS_SECTION,
        operation: 'revoke_agent',
      })
      toast.success(t('managedAgents.page.toasts.agentRevoked'))
    },
    onError: (error: unknown) => {
      toast.error(extractBackendMessage(error, t('managedAgents.page.errors.revokeAgent')))
    },
  })

  const deleteAgentMutation = useMutation({
    mutationFn: managedAgentsAPI.deleteAgent,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['managed-agents'] })
      trackSystem(EventAction.DELETE, {
        section: MANAGED_AGENTS_ANALYTICS_SECTION,
        operation: 'delete_agent',
      })
      trackFeatureUsed('managed_agents', {
        surface: MANAGED_AGENTS_ANALYTICS_SECTION,
        operation: 'delete_agent',
      })
      toast.success(t('managedAgents.page.toasts.agentDeleted'))
    },
    onError: (error: unknown) => {
      toast.error(extractBackendMessage(error, t('managedAgents.page.errors.deleteAgent')))
    },
  })

  const cancelJobMutation = useMutation({
    mutationFn: managedAgentsAPI.cancelJob,
    onSuccess: (_response, jobId) => {
      queryClient.invalidateQueries({ queryKey: ['managed-agent-jobs'] })
      trackSystem(EventAction.STOP, {
        section: MANAGED_AGENTS_ANALYTICS_SECTION,
        operation: 'cancel_job',
        job_id_present: Boolean(jobId),
      })
      trackFeatureUsed('managed_agents', {
        surface: MANAGED_AGENTS_ANALYTICS_SECTION,
        operation: 'cancel_job',
        job_id_present: Boolean(jobId),
      })
      toast.success(t('managedAgents.page.toasts.cancellationRequested'))
    },
    onError: (error: unknown) => {
      toast.error(extractBackendMessage(error, t('managedAgents.page.errors.cancelJob')))
    },
  })

  if (!canManageAgents) {
    return <Navigate to="/dashboard" replace />
  }

  if (!hasManagedAgentsPlan) {
    return (
      <ManagedAgentsPlanGate
        defaultAgentServerUrl={defaultAgentServerUrl}
        activeTab={activeTab}
        agents={agents}
        tokens={tokens}
        jobs={jobs}
        isLoading={isLoading}
      />
    )
  }

  const handleCopy = async (value: string, source = 'unknown') => {
    await navigator.clipboard.writeText(value)
    trackSystem(EventAction.VIEW, {
      section: MANAGED_AGENTS_ANALYTICS_SECTION,
      operation: 'copy_command',
      source,
    })
    trackFeatureUsed('managed_agents', {
      surface: MANAGED_AGENTS_ANALYTICS_SECTION,
      operation: 'copy_command',
      source,
    })
    toast.success(t('managedAgents.page.toasts.copied'))
  }

  const setupCommand = buildAgentInstallCommand(
    defaultAgentServerUrl,
    '<enrollment-token>',
    '<machine-name>'
  )

  return (
    <Box>
      <PageHeader
        title={t('managedAgents.page.title')}
        subtitle={t('managedAgents.page.subtitle')}
        actions={
          <>
            <IconButton
              onClick={() => void refreshAll()}
              aria-label={
                manualRefreshInFlight
                  ? t('managedAgents.page.refreshing')
                  : t('managedAgents.page.refresh')
              }
              title={
                manualRefreshInFlight
                  ? t('managedAgents.page.refreshing')
                  : t('managedAgents.page.refresh')
              }
              disabled={manualRefreshInFlight}
            >
              <RefreshCw size={20} />
            </IconButton>
            <Button
              variant="contained"
              startIcon={<Plus size={18} />}
              onClick={() => {
                trackSystem(EventAction.VIEW, {
                  section: MANAGED_AGENTS_ANALYTICS_SECTION,
                  operation: 'open_add_agent_dialog',
                })
                trackFeatureUsed('managed_agents', {
                  surface: MANAGED_AGENTS_ANALYTICS_SECTION,
                  operation: 'open_add_agent_dialog',
                })
                setAddAgentDialogOpen(true)
              }}
              sx={{ width: { xs: '100%', md: 'auto' } }}
            >
              {t('managedAgents.page.addAgent')}
            </Button>
          </>
        }
      />

      <AgentSetupGuide command={setupCommand} onCopy={handleCopy} />

      <PageTabs
        value={activeTab}
        onChange={(_, value: PageTab) => {
          trackSystem(EventAction.FILTER, {
            section: MANAGED_AGENTS_ANALYTICS_SECTION,
            operation: 'change_tab',
            tab: value,
          })
          setActiveTab(value)
        }}
      >
        <Tab label={t('managedAgents.page.tabs.agents')} value="agents" />
        <Tab label={t('managedAgents.page.tabs.jobs')} value="jobs" />
        <Tab label={t('managedAgents.page.tabs.tokens')} value="tokens" />
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
          onViewLogs={(agent) => {
            trackSystem(EventAction.VIEW, {
              section: MANAGED_AGENTS_ANALYTICS_SECTION,
              operation: 'view_agent_logs',
              status: agent.status,
            })
            trackFeatureUsed('managed_agents', {
              surface: MANAGED_AGENTS_ANALYTICS_SECTION,
              operation: 'view_agent_logs',
              status: agent.status,
            })
            setLogsAgent(agent)
          }}
          onRunDiagnostics={async (agent, payload) => {
            trackSystem(EventAction.START, {
              section: MANAGED_AGENTS_ANALYTICS_SECTION,
              operation: 'run_agent_diagnostics',
              status: agent.status,
              has_target: Boolean(payload.target),
            })
            trackFeatureUsed('managed_agents', {
              surface: MANAGED_AGENTS_ANALYTICS_SECTION,
              operation: 'run_agent_diagnostics',
              status: agent.status,
              has_target: Boolean(payload.target),
            })
            const response = await managedAgentsAPI.runDiagnostics(agent.id, payload)
            return response.data
          }}
          isRevoking={revokeAgentMutation.isPending}
          isDeleting={deleteAgentMutation.isPending}
        />
      ) : null}

      {!isLoading && activeTab === 'jobs' ? (
        <JobsTable
          jobs={jobs}
          agentsById={agentsById}
          onCancel={(job) => cancelJobMutation.mutate(job.id)}
          onViewLogs={(job) => {
            trackSystem(EventAction.VIEW, {
              section: MANAGED_AGENTS_ANALYTICS_SECTION,
              operation: 'view_job_logs',
              job_type: getJobKind(job),
              status: job.status,
            })
            trackFeatureUsed('managed_agents', {
              surface: MANAGED_AGENTS_ANALYTICS_SECTION,
              operation: 'view_job_logs',
              job_type: getJobKind(job),
              status: job.status,
            })
            setLogsJob(job)
          }}
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
  const { t } = useTranslation()
  const [helpOpen, setHelpOpen] = useState(false)

  return (
    <Box sx={{ mb: 3 }}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1}
        sx={{
          alignItems: { xs: 'stretch', sm: 'center' },
          justifyContent: 'space-between',
          mb: 1,
        }}
      >
        <Stack
          direction="row"
          spacing={1}
          sx={{
            alignItems: 'center',
            color: 'text.secondary',
          }}
        >
          <Terminal size={16} />
          <Typography variant="body2">{t('managedAgents.setupGuide.summary')}</Typography>
        </Stack>
        <Button
          variant="text"
          size="small"
          startIcon={<Info size={16} />}
          onClick={() => setHelpOpen(true)}
        >
          {t('managedAgents.setupGuide.help')}
        </Button>
      </Stack>

      <CopyableCodeBlock
        value={command}
        copyLabel={t('managedAgents.setupGuide.copySetupCommand')}
        onCopy={() => onCopy(command)}
      />

      <ResponsiveDialog
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
        fullWidth
        maxWidth="md"
        footer={
          <DialogActions>
            <Button onClick={() => setHelpOpen(false)}>{t('common.buttons.close')}</Button>
          </DialogActions>
        }
      >
        <DialogTitle>{t('managedAgents.setupGuide.title')}</DialogTitle>
        <DialogContent>
          <AgentSetupHelpContent command={command} onCopy={onCopy} />
        </DialogContent>
      </ResponsiveDialog>
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
  const { t } = useTranslation()
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
        <Typography
          variant="subtitle2"
          gutterBottom
          sx={{
            fontWeight: 700,
          }}
        >
          {t('managedAgents.setupGuide.steps.install.title')}
        </Typography>
        <Typography
          sx={{
            color: 'text.secondary',
            mb: 1,
          }}
        >
          {t('managedAgents.setupGuide.steps.install.description')}
        </Typography>
        <CopyableCodeBlock
          value={command}
          copyLabel={t('managedAgents.installCommand.copy')}
          onCopy={() => onCopy(command)}
        />
      </Box>

      <Box>
        <Typography
          variant="subtitle2"
          gutterBottom
          sx={{
            fontWeight: 700,
          }}
        >
          {t('managedAgents.setupGuide.steps.server.title')}
        </Typography>
        <Typography
          sx={{
            color: 'text.secondary',
            mb: 1,
          }}
        >
          {t('managedAgents.setupGuide.steps.server.description')}
        </Typography>
      </Box>

      <Box>
        <Typography
          variant="subtitle2"
          gutterBottom
          sx={{
            fontWeight: 700,
          }}
        >
          {t('managedAgents.setupGuide.steps.troubleshooting.title')}
        </Typography>
        <Typography
          sx={{
            color: 'text.secondary',
            mb: 1,
          }}
        >
          {t('managedAgents.setupGuide.steps.troubleshooting.descriptionPrefix')}{' '}
          <MuiLink
            href="https://github.com/karanhudia/borg-ui/tree/main/agent"
            target="_blank"
            rel="noreferrer"
          >
            {t('managedAgents.setupGuide.steps.troubleshooting.link')}
          </MuiLink>
          .
        </Typography>
        <CopyableCodeBlock
          value={manualInstallCommand}
          copyLabel={t('managedAgents.setupGuide.copyInstallCommands')}
          onCopy={() => onCopy(manualInstallCommand)}
        />
      </Box>

      <Box>
        <Typography
          variant="subtitle2"
          gutterBottom
          sx={{
            fontWeight: 700,
          }}
        >
          {t('managedAgents.setupGuide.steps.service.title')}
        </Typography>
        <Typography
          sx={{
            color: 'text.secondary',
            mb: 1,
          }}
        >
          {t('managedAgents.setupGuide.steps.service.description')}
        </Typography>
        <CopyableCodeBlock
          value={runCommand}
          copyLabel={t('managedAgents.setupGuide.copyStatusCommand')}
          onCopy={() => onCopy(runCommand)}
        />
        <Box sx={{ mt: 1 }}>
          <CopyableCodeBlock
            value={linuxStartupCommand}
            copyLabel={t('managedAgents.setupGuide.copySystemdCommands')}
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

export function AgentDiagnosticsDialog({
  agent,
  open,
  initialResult = null,
  onClose,
  onRunDiagnostics,
}: {
  agent: AgentMachineResponse | null
  open: boolean
  initialResult?: AgentDiagnosticsResponse | null
  onClose: () => void
  onRunDiagnostics?: (
    agent: AgentMachineResponse,
    payload: AgentDiagnosticsRequest
  ) => Promise<AgentDiagnosticsResponse>
}) {
  const { t } = useTranslation()
  const [targetHost, setTargetHost] = useState('')
  const [targetPort, setTargetPort] = useState('')
  const [targetTimeout, setTargetTimeout] = useState('3')
  const [result, setResult] = useState<AgentDiagnosticsResponse | null>(initialResult)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const diagnosticsMessages = {
    invalidPort: t('managedAgents.page.diagnostics.invalidPort'),
    invalidTimeout: t('managedAgents.page.diagnostics.invalidTimeout'),
  }
  const targetError = getDiagnosticsTargetError(
    targetHost,
    targetPort,
    targetTimeout,
    diagnosticsMessages
  )
  const hasTarget = Boolean(targetHost.trim())
  const portInvalid = hasTarget && parseDiagnosticsPort(targetPort) === null
  const timeoutInvalid = hasTarget && parseDiagnosticsTimeout(targetTimeout) === null

  useEffect(() => {
    if (!open) return
    setResult(initialResult)
    setErrorMessage(null)
    setRunning(false)
  }, [initialResult, open])

  const runDiagnostics = async () => {
    if (!agent || !onRunDiagnostics) return
    const validationError = getDiagnosticsTargetError(
      targetHost,
      targetPort,
      targetTimeout,
      diagnosticsMessages
    )
    if (validationError) {
      setErrorMessage(validationError)
      return
    }
    setRunning(true)
    setErrorMessage(null)
    try {
      const nextResult = await onRunDiagnostics(
        agent,
        buildDiagnosticsPayload(targetHost, targetPort, targetTimeout)
      )
      setResult(nextResult)
    } catch (error) {
      setErrorMessage(extractBackendMessage(error, t('managedAgents.page.errors.runDiagnostics')))
    } finally {
      setRunning(false)
    }
  }

  const diagnosticAgent = result?.agent
  const borgVersions = diagnosticAgent?.borg_versions ?? agent?.borg_versions ?? []
  const capabilities = diagnosticAgent?.capabilities ?? agent?.capabilities ?? []
  const lastError = diagnosticAgent?.last_error ?? agent?.last_error ?? null

  const footer = (
    <DialogActions sx={{ px: 3, py: 2 }}>
      <Button onClick={onClose}>{t('common.buttons.close')}</Button>
      <Button
        variant="contained"
        onClick={() => void runDiagnostics()}
        disabled={!agent || running || !onRunDiagnostics || !!targetError}
        startIcon={
          running ? <CircularProgress color="inherit" size={16} /> : <Activity size={16} />
        }
      >
        {running
          ? t('managedAgents.page.diagnostics.running')
          : t('managedAgents.page.diagnostics.runCheck')}
      </Button>
    </DialogActions>
  )

  return (
    <ResponsiveDialog open={open} onClose={onClose} fullWidth maxWidth="md" footer={footer}>
      <DialogTitle>{t('managedAgents.page.diagnostics.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2.25} sx={{ pt: 0.5, pb: 1 }}>
          <Box>
            <Typography
              sx={{
                fontWeight: 700,
              }}
            >
              {getAgentLabel(agent || undefined, t('managedAgents.page.unknownAgent'))}
            </Typography>
            <Typography
              variant="body2"
              sx={{
                color: 'text.secondary',
                mt: 0.25,
              }}
            >
              {t('managedAgents.page.diagnostics.description')}
            </Typography>
          </Box>

          <DiagnosticsTcpTargetFields
            targetHost={targetHost}
            targetPort={targetPort}
            targetTimeout={targetTimeout}
            onTargetHostChange={setTargetHost}
            onTargetPortChange={setTargetPort}
            onTargetTimeoutChange={setTargetTimeout}
            hasTarget={hasTarget}
            portInvalid={portInvalid}
            timeoutInvalid={timeoutInvalid}
            timeoutInputProps={{ min: 0.5, max: 10, step: 0.5 }}
            labels={{
              summary: t('managedAgents.page.diagnostics.advancedSummary'),
              description: t('managedAgents.page.diagnostics.advancedDescription'),
              host: t('managedAgents.page.diagnostics.serviceHost'),
              hostPlaceholder: 'postgres.internal',
              hostHelper: t('managedAgents.page.diagnostics.serviceHostHelper'),
              port: t('managedAgents.page.diagnostics.servicePort'),
              portPlaceholder: '5432',
              portError: '1-65535',
              timeout: t('managedAgents.page.diagnostics.timeout'),
              timeoutHelper: t('managedAgents.page.diagnostics.seconds'),
              timeoutError: t('managedAgents.page.diagnostics.timeoutRange'),
            }}
          />

          {targetError && (
            <Alert severity="warning" role="alert" sx={{ borderRadius: 1.5 }}>
              {targetError}
            </Alert>
          )}

          {errorMessage && (
            <Alert severity="error" role="alert" sx={{ borderRadius: 1.5 }}>
              {errorMessage}
            </Alert>
          )}

          <Box
            sx={{
              border: '1px solid',
              borderColor: 'divider',
              borderRadius: 1.5,
              overflow: 'hidden',
            }}
          >
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' },
              }}
            >
              {[
                [
                  t('managedAgents.page.table.status'),
                  diagnosticAgent?.status ?? agent?.status ?? 'unknown',
                ],
                [
                  t('managedAgents.page.lastSeen'),
                  formatDate(
                    diagnosticAgent?.last_seen_at ?? agent?.last_seen_at,
                    t('managedAgents.page.never')
                  ),
                ],
                [
                  t('managedAgents.page.agentVersion'),
                  diagnosticAgent?.agent_version ?? agent?.agent_version ?? '—',
                ],
                [
                  t('managedAgents.page.borg'),
                  borgVersions.length
                    ? borgVersions.map(formatBorgBinary).join(', ')
                    : t('managedAgents.page.none'),
                ],
              ].map(([label, value], index) => (
                <Box
                  key={label}
                  sx={{
                    px: 1.5,
                    py: 1.25,
                    borderRight: { xs: 0, sm: index % 2 === 0 ? '1px solid' : 0 },
                    borderBottom: index < 2 ? '1px solid' : 0,
                    borderColor: 'divider',
                    minWidth: 0,
                  }}
                >
                  <Typography
                    variant="caption"
                    sx={{
                      color: 'text.secondary',
                      fontWeight: 700,
                    }}
                  >
                    {label}
                  </Typography>
                  <Typography
                    noWrap
                    title={String(value)}
                    sx={{
                      fontWeight: 600,
                    }}
                  >
                    {value}
                  </Typography>
                </Box>
              ))}
            </Box>
          </Box>

          <Stack spacing={1}>
            <Typography
              variant="caption"
              sx={{
                color: 'text.secondary',
                fontWeight: 700,
              }}
            >
              {t('managedAgents.page.capabilities')}
            </Typography>
            <Stack
              direction="row"
              spacing={0.75}
              useFlexGap
              sx={{
                flexWrap: 'wrap',
              }}
            >
              {capabilities.length ? (
                capabilities.map((capability) => (
                  <Chip key={capability} label={capability} size="small" variant="outlined" />
                ))
              ) : (
                <Chip
                  label={t('managedAgents.page.noneReported')}
                  size="small"
                  variant="outlined"
                />
              )}
            </Stack>
          </Stack>

          {lastError && (
            <Alert severity="warning" icon={<AlertTriangle size={16} />} sx={{ borderRadius: 1.5 }}>
              {lastError}
            </Alert>
          )}

          {result ? (
            <Stack spacing={1.25} aria-live="polite">
              <DiagnosticResultRow
                title={sessionStatusLabel(result.session.status, {
                  healthy: t('managedAgents.page.diagnostics.sessionHealthy'),
                  offline: t('managedAgents.page.diagnostics.agentOffline'),
                  timedOut: t('managedAgents.page.diagnostics.timedOut'),
                  failed: t('managedAgents.page.diagnostics.sessionFailed'),
                })}
                elapsed={result.session.elapsed_ms}
                error={result.session.error}
                message={result.session.message}
                severity={result.session.status === 'success' ? 'success' : 'warning'}
              />
              {result.tcp ? (
                <DiagnosticResultRow
                  title={tcpStatusLabel(result.tcp.status, {
                    reachable: t('managedAgents.page.diagnostics.tcpReachable'),
                    failed: t('managedAgents.page.diagnostics.tcpFailed'),
                  })}
                  elapsed={result.tcp.elapsed_ms}
                  target={`${result.tcp.target.host}:${result.tcp.target.port}`}
                  error={result.tcp.error}
                  message={result.tcp.message}
                  severity={result.tcp.status === 'success' ? 'success' : 'error'}
                />
              ) : null}
            </Stack>
          ) : (
            <Alert severity="info" sx={{ borderRadius: 1.5 }}>
              {t('managedAgents.page.diagnostics.emptyResult')}
            </Alert>
          )}
        </Stack>
      </DialogContent>
    </ResponsiveDialog>
  )
}

function DiagnosticResultRow({
  title,
  elapsed,
  error,
  message,
  target,
  severity,
}: {
  title: string
  elapsed?: number | null
  error?: string | null
  message?: string | null
  target?: string
  severity: 'success' | 'warning' | 'error'
}) {
  const { t } = useTranslation()
  return (
    <Box
      sx={{
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 1.5,
        px: 1.5,
        py: 1.25,
      }}
    >
      <Stack
        direction="row"
        spacing={1}
        sx={{
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <Stack
          direction="row"
          spacing={0.75}
          sx={{
            alignItems: 'center',
            minWidth: 0,
          }}
        >
          {severity === 'success' ? (
            <CheckCircle size={16} />
          ) : severity === 'error' ? (
            <XCircle size={16} />
          ) : (
            <AlertTriangle size={16} />
          )}
          <Typography
            sx={{
              fontWeight: 700,
            }}
          >
            {title}
          </Typography>
        </Stack>
        <Chip
          label={formatElapsedMs(elapsed, t('managedAgents.page.notReported'))}
          size="small"
          variant="outlined"
        />
      </Stack>
      {target && (
        <Typography
          variant="body2"
          sx={{
            color: 'text.secondary',
            mt: 0.75,
          }}
        >
          {target}
        </Typography>
      )}
      {error && (
        <Typography
          variant="body2"
          sx={{ mt: 0.75, fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace' }}
        >
          {error}
        </Typography>
      )}
      {message && (
        <Typography
          variant="body2"
          sx={{
            color: 'text.secondary',
            mt: 0.5,
          }}
        >
          {message}
        </Typography>
      )}
    </Box>
  )
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
  const { t } = useTranslation()
  return (
    <ResponsiveDialog
      open={open}
      onClose={onCancel}
      fullWidth
      maxWidth="xs"
      footer={
        <DialogActions>
          <Button onClick={onCancel}>{t('common.buttons.cancel')}</Button>
          <Button
            color="error"
            variant="contained"
            disabled={isDeleting || !agent}
            onClick={() => {
              if (!agent) return
              onConfirm(agent)
            }}
          >
            {t('managedAgents.page.deleteDialog.confirm')}
          </Button>
        </DialogActions>
      }
    >
      <DialogTitle>{t('managedAgents.page.deleteDialog.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ mt: 0.5 }}>
          <Typography
            sx={{
              fontWeight: 700,
            }}
          >
            {getAgentLabel(agent || undefined, t('managedAgents.page.unknownAgent'))}
          </Typography>
          <Typography
            sx={{
              color: 'text.secondary',
            }}
          >
            {t('managedAgents.page.deleteDialog.description')}
          </Typography>
        </Stack>
      </DialogContent>
    </ResponsiveDialog>
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
  const { t } = useTranslation()
  const command = buildAgentReinstallCommand(serverUrl)

  return (
    <ResponsiveDialog
      open={open}
      onClose={onCancel}
      fullWidth
      maxWidth="md"
      footer={
        <DialogActions>
          <Button onClick={onCancel}>{t('common.buttons.close')}</Button>
        </DialogActions>
      }
    >
      <DialogTitle>{t('managedAgents.page.reinstallDialog.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 0.5 }}>
          <Box>
            <Typography
              sx={{
                fontWeight: 700,
              }}
            >
              {getAgentLabel(agent || undefined, t('managedAgents.page.unknownAgent'))}
            </Typography>
            <Typography
              sx={{
                color: 'text.secondary',
                mt: 0.5,
              }}
            >
              {t('managedAgents.page.reinstallDialog.description')}
            </Typography>
          </Box>
          <CopyableCodeBlock
            value={command}
            copyLabel={t('managedAgents.page.reinstallDialog.copyCommand')}
            onCopy={() => onCopy(command)}
          />
          <Alert severity="info" sx={{ borderRadius: 1.5 }}>
            {t('managedAgents.page.reinstallDialog.configPreserved')}{' '}
            <Box component="code">/etc/borg-ui-agent/config.toml</Box>.
          </Alert>
        </Stack>
      </DialogContent>
    </ResponsiveDialog>
  )
}

export function AgentList({
  agents,
  serverUrl,
  onCopy,
  onRevoke,
  onDelete,
  onViewLogs,
  onRunDiagnostics,
  isRevoking,
  isDeleting,
}: {
  agents: AgentMachineResponse[]
  serverUrl: string
  onCopy: (value: string) => void
  onRevoke: (agent: AgentMachineResponse) => void
  onDelete: (agent: AgentMachineResponse) => void
  onViewLogs: (agent: AgentMachineResponse) => void
  onRunDiagnostics?: (
    agent: AgentMachineResponse,
    payload: AgentDiagnosticsRequest
  ) => Promise<AgentDiagnosticsResponse>
  isRevoking: boolean
  isDeleting: boolean
}) {
  const theme = useTheme()
  const { t } = useTranslation()
  const { trackSystem, EventAction } = useAnalytics()
  const isDark = theme.palette.mode === 'dark'
  const [deleteTarget, setDeleteTarget] = useState<AgentMachineResponse | null>(null)
  const [reinstallTarget, setReinstallTarget] = useState<AgentMachineResponse | null>(null)
  const [diagnosticsTarget, setDiagnosticsTarget] = useState<AgentMachineResponse | null>(null)
  const handleRunDiagnostics =
    onRunDiagnostics ??
    (async (agent: AgentMachineResponse): Promise<AgentDiagnosticsResponse> => ({
      agent: {
        id: agent.id,
        name: agent.name,
        agent_id: agent.agent_id,
        hostname: agent.hostname,
        status: agent.status,
        last_seen_at: agent.last_seen_at,
        agent_version: agent.agent_version,
        borg_versions: agent.borg_versions,
        capabilities: agent.capabilities,
        last_error: agent.last_error,
      },
      session: {
        status: 'failed',
        elapsed_ms: null,
        error: 'diagnostics_unavailable',
        message: t('managedAgents.page.diagnostics.unavailable'),
      },
      tcp: null,
    }))

  if (!agents.length) {
    return <Alert severity="info">{t('managedAgents.page.emptyAgents')}</Alert>
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
          const borgValue = hasUsableBorg
            ? borgVersions.map(formatBorgBinary).join(', ')
            : t('managedAgents.page.none')
          const stats = [
            {
              label: t('managedAgents.page.os'),
              value: [agent.os, agent.arch].filter(Boolean).join(' / ') || '—',
            },
            { label: t('managedAgents.agent'), value: agent.agent_version || '—' },
            {
              label: t('managedAgents.page.lastSeen'),
              value: formatDate(agent.last_seen_at, t('managedAgents.page.never')),
            },
            { label: t('managedAgents.page.borg'), value: borgValue },
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
                    noWrap
                    title={getAgentLabel(agent, t('managedAgents.page.unknownAgent'))}
                    sx={{
                      fontWeight: 700,
                      lineHeight: 1.3,
                      mb: 0.25,
                    }}
                  >
                    {getAgentLabel(agent, t('managedAgents.page.unknownAgent'))}
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
                    <Typography
                      variant="body2"
                      sx={{
                        fontWeight: 700,
                      }}
                    >
                      {t('managedAgents.page.noBorg.title')}
                    </Typography>
                    <Typography
                      variant="caption"
                      sx={{
                        color: 'text.secondary',
                      }}
                    >
                      {t('managedAgents.page.noBorg.description')}
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
                  <Tooltip title={t('managedAgents.page.actions.runDiagnostics')} arrow>
                    <IconButton
                      size="small"
                      aria-label={t('managedAgents.page.actions.runDiagnostics')}
                      onClick={() => {
                        trackSystem(EventAction.START, {
                          section: MANAGED_AGENTS_ANALYTICS_SECTION,
                          operation: 'open_diagnostics_dialog',
                          status: agent.status,
                        })
                        setDiagnosticsTarget(agent)
                      }}
                      sx={{
                        width: { xs: 40, sm: 34 },
                        height: { xs: 40, sm: 34 },
                        borderRadius: 1.5,
                        color: alpha(theme.palette.success.main, 0.75),
                        '&:hover': {
                          color: theme.palette.success.main,
                          bgcolor: alpha(theme.palette.success.main, isDark ? 0.15 : 0.1),
                        },
                      }}
                    >
                      <Activity size={16} />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title={t('managedAgents.page.actions.viewAgentLogs')} arrow>
                    <IconButton
                      size="small"
                      aria-label={t('managedAgents.page.actions.viewAgentLogs')}
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
                  <Tooltip title={t('managedAgents.page.actions.reinstallAgent')} arrow>
                    <IconButton
                      size="small"
                      aria-label={t('managedAgents.page.actions.reinstallAgent')}
                      onClick={() => {
                        trackSystem(EventAction.VIEW, {
                          section: MANAGED_AGENTS_ANALYTICS_SECTION,
                          operation: 'open_reinstall_dialog',
                          status: agent.status,
                          has_borg_versions: Boolean(agent.borg_versions?.length),
                        })
                        setReinstallTarget(agent)
                      }}
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
                  <Tooltip title={t('managedAgents.page.actions.revokeAccess')} arrow>
                    <span>
                      <IconButton
                        size="small"
                        aria-label={t('managedAgents.page.actions.revokeAgent')}
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
                  <Tooltip title={t('managedAgents.page.actions.deleteAgent')} arrow>
                    <span>
                      <IconButton
                        size="small"
                        aria-label={t('managedAgents.page.actions.deleteAgent')}
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
      <AgentDiagnosticsDialog
        open={!!diagnosticsTarget}
        agent={diagnosticsTarget}
        onClose={() => setDiagnosticsTarget(null)}
        onRunDiagnostics={handleRunDiagnostics}
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
  const { t } = useTranslation()
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
      title={
        agent
          ? t('managedAgents.page.logs.agentTitle', {
              name: getAgentLabel(agent, t('managedAgents.page.unknownAgent')),
            })
          : t('managedAgents.page.logs.agent')
      }
      jobTypeLabel={t('managedAgents.agent')}
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
  const { t } = useTranslation()
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
      title={
        job
          ? t('managedAgents.page.logs.jobTitle', { id: job.id })
          : t('managedAgents.page.logs.job')
      }
      jobTypeLabel={t('managedAgents.page.logs.job')}
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
  const { t } = useTranslation()
  if (!jobs.length) {
    return <Alert severity="info">{t('managedAgents.page.emptyJobs')}</Alert>
  }

  return (
    <Paper variant="outlined" sx={{ borderRadius: 2, overflow: 'hidden' }}>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>{t('managedAgents.page.table.job')}</TableCell>
            <TableCell>{t('managedAgents.agent')}</TableCell>
            <TableCell>{t('managedAgents.page.table.status')}</TableCell>
            <TableCell>{t('managedAgents.page.table.progress')}</TableCell>
            <TableCell>{t('managedAgents.page.table.updated')}</TableCell>
            <TableCell align="right">{t('managedAgents.page.table.actions')}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {jobs.map((job) => {
            const agent = agentsById.get(job.agent_machine_id)
            const canCancel = !FINAL_JOB_STATUSES.has(job.status)
            return (
              <TableRow key={job.id} hover>
                <TableCell>
                  <Typography
                    sx={{
                      fontWeight: 700,
                    }}
                  >
                    #{job.id}
                  </Typography>
                  <Typography
                    variant="caption"
                    sx={{
                      color: 'text.secondary',
                    }}
                  >
                    {getJobKind(job)}
                  </Typography>
                </TableCell>
                <TableCell>{getAgentLabel(agent, t('managedAgents.page.unknownAgent'))}</TableCell>
                <TableCell>
                  <Chip label={job.status} color={statusChipColor(job.status)} size="small" />
                </TableCell>
                <TableCell sx={{ minWidth: 160 }}>
                  <LinearProgress
                    variant="determinate"
                    value={Math.max(0, Math.min(100, job.progress_percent ?? 0))}
                    sx={{ borderRadius: 1, height: 7 }}
                  />
                  <Typography
                    variant="caption"
                    sx={{
                      color: 'text.secondary',
                    }}
                  >
                    {Math.round(job.progress_percent ?? 0)}%
                  </Typography>
                </TableCell>
                <TableCell>{formatDate(job.updated_at, t('managedAgents.page.never'))}</TableCell>
                <TableCell align="right">
                  <Tooltip title={t('managedAgents.page.actions.viewLogs')}>
                    <IconButton onClick={() => onViewLogs(job)}>
                      <Eye size={18} />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title={t('managedAgents.page.actions.cancelJob')}>
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
  const { t } = useTranslation()
  if (!tokens.length) {
    return <Alert severity="info">{t('managedAgents.page.emptyTokens')}</Alert>
  }

  return (
    <Paper variant="outlined" sx={{ borderRadius: 2, overflow: 'hidden' }}>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>{t('managedAgents.page.table.name')}</TableCell>
            <TableCell>{t('managedAgents.page.table.prefix')}</TableCell>
            <TableCell>{t('managedAgents.page.table.status')}</TableCell>
            <TableCell>{t('managedAgents.page.table.expires')}</TableCell>
            <TableCell align="right">{t('managedAgents.page.table.actions')}</TableCell>
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
                <TableCell>{formatDate(token.expires_at, t('managedAgents.page.never'))}</TableCell>
                <TableCell align="right">
                  <Tooltip title={t('managedAgents.page.actions.revokeToken')}>
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

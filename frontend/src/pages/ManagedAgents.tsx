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
  Divider,
  FormControl,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Select,
  Skeleton,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material'
import { Ban, Copy, Laptop, Play, Plus, RefreshCw, Server, Terminal, XCircle } from 'lucide-react'
import {
  AgentBackupJobCreate,
  AgentEnrollmentTokenSummary,
  AgentJobLogEntryResponse,
  AgentJobResponse,
  AgentMachineResponse,
  managedAgentsAPI,
} from '../services/api'
import { useAuth } from '../hooks/useAuth'
import { getApiErrorDetail } from '../utils/apiErrors'
import { translateBackendKey } from '../utils/translateBackendKey'

type PageTab = 'agents' | 'jobs' | 'tokens'

const FINAL_JOB_STATUSES = new Set(['completed', 'failed', 'canceled'])
const EMPTY_AGENTS: AgentMachineResponse[] = []
const EMPTY_TOKENS: AgentEnrollmentTokenSummary[] = []
const EMPTY_JOBS: AgentJobResponse[] = []
const EMPTY_LOGS: AgentJobLogEntryResponse[] = []

const emptyBackupForm = {
  repository_path: '',
  archive_name: '',
  source_paths: '',
  borg_version: 1 as 1 | 2,
  compression: 'lz4',
  exclude_patterns: '',
  custom_flags: '',
  remote_path: '',
  passphrase: '',
}

function formatDate(value?: string | null): string {
  if (!value) return 'Never'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function parseLines(value: string): string[] {
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
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
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const queryClient = useQueryClient()
  const { hasGlobalPermission } = useAuth()
  const canManageAgents = hasGlobalPermission('settings.ssh.manage')
  const [activeTab, setActiveTab] = useState<PageTab>('agents')
  const [enrollmentDialogOpen, setEnrollmentDialogOpen] = useState(false)
  const [tokenName, setTokenName] = useState('Agent enrollment')
  const [tokenExpiryMinutes, setTokenExpiryMinutes] = useState(60)
  const [createdToken, setCreatedToken] = useState<string | null>(null)
  const [backupDialogAgent, setBackupDialogAgent] = useState<AgentMachineResponse | null>(null)
  const [backupForm, setBackupForm] = useState(emptyBackupForm)
  const [logsJob, setLogsJob] = useState<AgentJobResponse | null>(null)

  const agentsQuery = useQuery({
    queryKey: ['managed-agents'],
    queryFn: managedAgentsAPI.listAgents,
    enabled: canManageAgents,
    refetchInterval: 15000,
  })

  const tokensQuery = useQuery({
    queryKey: ['managed-agent-enrollment-tokens'],
    queryFn: managedAgentsAPI.listEnrollmentTokens,
    enabled: canManageAgents,
  })

  const jobsQuery = useQuery({
    queryKey: ['managed-agent-jobs'],
    queryFn: managedAgentsAPI.listJobs,
    enabled: canManageAgents,
    refetchInterval: 5000,
  })

  const logsQuery = useQuery({
    queryKey: ['managed-agent-job-logs', logsJob?.id],
    queryFn: () => managedAgentsAPI.listJobLogs(logsJob!.id),
    enabled: canManageAgents && !!logsJob,
    refetchInterval: logsJob && !FINAL_JOB_STATUSES.has(logsJob.status) ? 2000 : false,
  })

  const agents = agentsQuery.data?.data ?? EMPTY_AGENTS
  const tokens = tokensQuery.data?.data ?? EMPTY_TOKENS
  const jobs = jobsQuery.data?.data ?? EMPTY_JOBS
  const logs = logsQuery.data?.data ?? EMPTY_LOGS

  const agentsById = useMemo(() => {
    return new Map(agents.map((agent) => [agent.id, agent]))
  }, [agents])

  const stats = {
    total: agents.length,
    online: agents.filter((agent) => agent.status === 'online').length,
    running: jobs.filter((job) => job.status === 'running').length,
  }

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

  const createBackupMutation = useMutation({
    mutationFn: ({ agentId, data }: { agentId: number; data: AgentBackupJobCreate }) =>
      managedAgentsAPI.createBackupJob(agentId, data),
    onSuccess: () => {
      setBackupDialogAgent(null)
      setBackupForm(emptyBackupForm)
      queryClient.invalidateQueries({ queryKey: ['managed-agent-jobs'] })
      toast.success('Backup job queued')
      setActiveTab('jobs')
    },
    onError: (error: unknown) => {
      toast.error(extractBackendMessage(error, 'Failed to queue backup job'))
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

  const handleOpenBackupDialog = (agent: AgentMachineResponse) => {
    setBackupDialogAgent(agent)
    setBackupForm({
      ...emptyBackupForm,
      archive_name: `${agent.name || agent.hostname || 'agent'}-{now}`,
    })
  }

  const handleQueueBackup = () => {
    if (!backupDialogAgent) return

    const secrets: Record<string, unknown> = {}
    if (backupForm.passphrase.trim()) {
      secrets.BORG_PASSPHRASE = { value: backupForm.passphrase.trim() }
    }

    createBackupMutation.mutate({
      agentId: backupDialogAgent.id,
      data: {
        repository_path: backupForm.repository_path.trim(),
        archive_name: backupForm.archive_name.trim(),
        source_paths: parseLines(backupForm.source_paths),
        borg_version: backupForm.borg_version,
        compression: backupForm.compression.trim() || 'lz4',
        exclude_patterns: parseLines(backupForm.exclude_patterns),
        custom_flags: parseLines(backupForm.custom_flags),
        remote_path: backupForm.remote_path.trim() || null,
        secrets,
      },
    })
  }

  const registrationCommand = createdToken
    ? `borg-ui-agent register --server ${window.location.origin} --token ${createdToken} --name <machine-name>`
    : ''

  const isLoading = agentsQuery.isLoading || tokensQuery.isLoading || jobsQuery.isLoading

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
            variant="outlined"
            startIcon={<Plus size={18} />}
            onClick={() => {
              setCreatedToken(null)
              setEnrollmentDialogOpen(true)
            }}
          >
            Enrollment Token
          </Button>
        </Stack>
      </Stack>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, 1fr)' },
          borderRadius: 2,
          border: '1px solid',
          borderColor: 'divider',
          overflow: 'hidden',
          mb: 3,
          bgcolor: isDark ? alpha('#fff', 0.025) : alpha('#000', 0.018),
        }}
      >
        {[
          { label: 'Agents', value: stats.total, icon: Laptop },
          { label: 'Online', value: stats.online, icon: Server },
          { label: 'Running Jobs', value: stats.running, icon: Play },
        ].map((stat, index) => {
          const Icon = stat.icon
          return (
            <Box
              key={stat.label}
              sx={{
                px: 2,
                py: 1.75,
                borderRight: { xs: 0, sm: index < 2 ? '1px solid' : 0 },
                borderBottom: { xs: index < 2 ? '1px solid' : 0, sm: 0 },
                borderColor: 'divider',
              }}
            >
              <Stack direction="row" spacing={0.75} alignItems="center" color="text.secondary">
                <Icon size={15} />
                <Typography variant="caption" fontWeight={700} textTransform="uppercase">
                  {stat.label}
                </Typography>
              </Stack>
              <Typography variant="h5" fontWeight={700} sx={{ mt: 0.5 }}>
                {stat.value}
              </Typography>
            </Box>
          )
        })}
      </Box>

      <Paper
        variant="outlined"
        sx={{
          mb: 3,
          borderRadius: 2,
          bgcolor: 'background.paper',
          overflow: 'hidden',
        }}
      >
        <Tabs value={activeTab} onChange={(_, value) => setActiveTab(value as PageTab)}>
          <Tab label="Agents" value="agents" />
          <Tab label="Jobs" value="jobs" />
          <Tab label="Enrollment Tokens" value="tokens" />
        </Tabs>
      </Paper>

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
          onQueueBackup={handleOpenBackupDialog}
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
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.75 }}>
                  <Box
                    component="code"
                    sx={{
                      flex: 1,
                      display: 'block',
                      p: 1.5,
                      borderRadius: 1,
                      bgcolor: 'action.hover',
                      overflowX: 'auto',
                      fontSize: '0.8rem',
                    }}
                  >
                    {createdToken}
                  </Box>
                  <Tooltip title="Copy token">
                    <IconButton onClick={() => handleCopy(createdToken)}>
                      <Copy size={18} />
                    </IconButton>
                  </Tooltip>
                </Stack>
                <Typography variant="caption" color="text.secondary" fontWeight={700}>
                  Command
                </Typography>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.75 }}>
                  <Box
                    component="code"
                    sx={{
                      flex: 1,
                      display: 'block',
                      p: 1.5,
                      borderRadius: 1,
                      bgcolor: 'action.hover',
                      overflowX: 'auto',
                      fontSize: '0.8rem',
                    }}
                  >
                    {registrationCommand}
                  </Box>
                  <Tooltip title="Copy command">
                    <IconButton onClick={() => handleCopy(registrationCommand)}>
                      <Copy size={18} />
                    </IconButton>
                  </Tooltip>
                </Stack>
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

      <Dialog
        open={!!backupDialogAgent}
        onClose={() => setBackupDialogAgent(null)}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle>Queue Agent Backup</DialogTitle>
        <DialogContent>
          <Stack spacing={2.25} sx={{ mt: 1 }}>
            <Alert severity="info">
              {backupDialogAgent ? getAgentLabel(backupDialogAgent) : ''}
            </Alert>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <TextField
                label="Repository Path"
                value={backupForm.repository_path}
                onChange={(event) =>
                  setBackupForm((prev) => ({ ...prev, repository_path: event.target.value }))
                }
                fullWidth
              />
              <TextField
                label="Archive Name"
                value={backupForm.archive_name}
                onChange={(event) =>
                  setBackupForm((prev) => ({ ...prev, archive_name: event.target.value }))
                }
                fullWidth
              />
            </Stack>
            <TextField
              label="Source Paths"
              value={backupForm.source_paths}
              onChange={(event) =>
                setBackupForm((prev) => ({ ...prev, source_paths: event.target.value }))
              }
              minRows={3}
              multiline
              fullWidth
            />
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <FormControl fullWidth>
                <InputLabel id="agent-borg-version-label">Borg Version</InputLabel>
                <Select
                  labelId="agent-borg-version-label"
                  label="Borg Version"
                  value={backupForm.borg_version}
                  onChange={(event) =>
                    setBackupForm((prev) => ({
                      ...prev,
                      borg_version: Number(event.target.value) as 1 | 2,
                    }))
                  }
                >
                  <MenuItem value={1}>Borg 1</MenuItem>
                  <MenuItem value={2}>Borg 2</MenuItem>
                </Select>
              </FormControl>
              <TextField
                label="Compression"
                value={backupForm.compression}
                onChange={(event) =>
                  setBackupForm((prev) => ({ ...prev, compression: event.target.value }))
                }
                fullWidth
              />
            </Stack>
            <TextField
              label="Exclude Patterns"
              value={backupForm.exclude_patterns}
              onChange={(event) =>
                setBackupForm((prev) => ({ ...prev, exclude_patterns: event.target.value }))
              }
              minRows={2}
              multiline
              fullWidth
            />
            <TextField
              label="Custom Flags"
              value={backupForm.custom_flags}
              onChange={(event) =>
                setBackupForm((prev) => ({ ...prev, custom_flags: event.target.value }))
              }
              minRows={2}
              multiline
              fullWidth
            />
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <TextField
                label="Remote Borg Path"
                value={backupForm.remote_path}
                onChange={(event) =>
                  setBackupForm((prev) => ({ ...prev, remote_path: event.target.value }))
                }
                fullWidth
              />
              <TextField
                label="Repository Passphrase"
                type="password"
                value={backupForm.passphrase}
                onChange={(event) =>
                  setBackupForm((prev) => ({ ...prev, passphrase: event.target.value }))
                }
                fullWidth
              />
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBackupDialogAgent(null)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleQueueBackup}
            disabled={
              createBackupMutation.isPending ||
              !backupForm.repository_path.trim() ||
              !backupForm.archive_name.trim() ||
              parseLines(backupForm.source_paths).length === 0
            }
          >
            Queue Backup
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

function AgentList({
  agents,
  onQueueBackup,
  onRevoke,
  isRevoking,
}: {
  agents: AgentMachineResponse[]
  onQueueBackup: (agent: AgentMachineResponse) => void
  onRevoke: (agent: AgentMachineResponse) => void
  isRevoking: boolean
}) {
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
      {agents.map((agent) => (
        <Paper key={agent.id} variant="outlined" sx={{ borderRadius: 2, p: 2 }}>
          <Stack spacing={2}>
            <Stack
              direction="row"
              spacing={1.5}
              alignItems="flex-start"
              justifyContent="space-between"
            >
              <Box sx={{ minWidth: 0 }}>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.75 }}>
                  <Laptop size={18} />
                  <Typography variant="h6" fontWeight={700} noWrap>
                    {getAgentLabel(agent)}
                  </Typography>
                </Stack>
                <Typography
                  color="text.secondary"
                  sx={{
                    fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
                    fontSize: '0.78rem',
                  }}
                  noWrap
                >
                  {agent.agent_id}
                </Typography>
              </Box>
              <Chip label={agent.status} color={statusChipColor(agent.status)} size="small" />
            </Stack>
            <Divider />
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)' },
                gap: 1.5,
              }}
            >
              <Meta label="OS" value={[agent.os, agent.arch].filter(Boolean).join(' / ') || '-'} />
              <Meta label="Agent" value={agent.agent_version || '-'} />
              <Meta label="Last Seen" value={formatDate(agent.last_seen_at)} />
              <Meta
                label="Borg"
                value={
                  agent.borg_versions?.length
                    ? agent.borg_versions
                        .map((binary) => String(binary.version || binary.path || 'borg'))
                        .join(', ')
                    : '-'
                }
              />
            </Box>
            {agent.last_error ? <Alert severity="error">{agent.last_error}</Alert> : null}
            <Stack direction="row" spacing={1} justifyContent="flex-end">
              <Button
                variant="outlined"
                startIcon={<Play size={16} />}
                onClick={() => onQueueBackup(agent)}
                disabled={agent.status === 'revoked' || agent.status === 'disabled'}
              >
                Backup
              </Button>
              <Tooltip title="Revoke agent">
                <span>
                  <IconButton
                    color="error"
                    onClick={() => onRevoke(agent)}
                    disabled={isRevoking || agent.status === 'revoked'}
                  >
                    <Ban size={18} />
                  </IconButton>
                </span>
              </Tooltip>
            </Stack>
          </Stack>
        </Paper>
      ))}
    </Box>
  )
}

function JobsTable({
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

function TokensTable({
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

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ minWidth: 0 }}>
      <Typography variant="caption" color="text.secondary" fontWeight={700}>
        {label}
      </Typography>
      <Typography noWrap>{value}</Typography>
    </Box>
  )
}

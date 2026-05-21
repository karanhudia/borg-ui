import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { Laptop, Monitor, Server, Terminal } from 'lucide-react'
import type {
  AgentEnrollmentTokenCreate,
  AgentEnrollmentTokenCreated,
  AgentMachineResponse,
} from '../../services/api'
import AgentInstallCommand from './AgentInstallCommand'
import { isLocalAgentServerUrl, normalizeAgentServerUrl } from './agentServerUrl'

type WizardStep = 0 | 1 | 2 | 3
type ExpiryOption = '1h' | '24h' | '7d' | '30d' | 'never'

const expiryOptions: Array<{ value: ExpiryOption; label: string }> = [
  { value: '1h', label: '1 hour' },
  { value: '24h', label: '24 hours' },
  { value: '7d', label: '7 days' },
  { value: '30d', label: '30 days' },
  { value: 'never', label: 'Never' },
]

function expiryPayload(option: ExpiryOption): Omit<AgentEnrollmentTokenCreate, 'name'> {
  switch (option) {
    case '1h':
      return { expires_in_hours: 1 }
    case '24h':
      return { expires_in_hours: 24 }
    case '30d':
      return { expires_in_days: 30 }
    case 'never':
      return { expires_never: true }
    case '7d':
    default:
      return { expires_in_days: 7 }
  }
}

function findConnectedAgent(
  agents: AgentMachineResponse[],
  initialAgentIds: Set<number>,
  token: AgentEnrollmentTokenCreated | null,
  agentName: string
) {
  if (!token) return null
  if (token.used_by_agent_id) {
    return agents.find((agent) => agent.id === token.used_by_agent_id) || null
  }
  return (
    agents.find(
      (agent) =>
        !initialAgentIds.has(agent.id) &&
        [agent.name, agent.hostname, agent.agent_id].some((value) => value === agentName)
    ) || null
  )
}

export default function AddAgentDialog({
  open,
  onClose,
  defaultServerUrl,
  agents,
  onCreateToken,
  creatingToken,
  onCopy,
  initialStep = 0,
  initialAgentName = 'borg-ui-agent',
  initialCreatedToken = null,
}: {
  open: boolean
  onClose: () => void
  defaultServerUrl: string
  agents: AgentMachineResponse[]
  onCreateToken: (payload: AgentEnrollmentTokenCreate) => Promise<AgentEnrollmentTokenCreated>
  creatingToken: boolean
  onCopy: (value: string) => void
  initialStep?: WizardStep
  initialAgentName?: string
  initialCreatedToken?: AgentEnrollmentTokenCreated | null
}) {
  const [step, setStep] = useState<WizardStep>(0)
  const [agentName, setAgentName] = useState(initialAgentName)
  const [expiry, setExpiry] = useState<ExpiryOption>('7d')
  const [serverUrl, setServerUrl] = useState(defaultServerUrl)
  const [createdToken, setCreatedToken] = useState<AgentEnrollmentTokenCreated | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [initialAgentIds, setInitialAgentIds] = useState<Set<number>>(new Set())
  const dialogWasOpenRef = useRef(false)

  useEffect(() => {
    if (!open) {
      dialogWasOpenRef.current = false
      return
    }
    if (dialogWasOpenRef.current) return
    dialogWasOpenRef.current = true
    setStep(initialStep)
    setAgentName(initialAgentName)
    setExpiry('7d')
    setServerUrl(defaultServerUrl)
    setCreatedToken(initialCreatedToken)
    setError(null)
    setInitialAgentIds(new Set(agents.map((agent) => agent.id)))
  }, [open, defaultServerUrl, agents, initialAgentName, initialCreatedToken, initialStep])

  const normalizedServerUrl = useMemo(() => {
    try {
      return normalizeAgentServerUrl(serverUrl.trim())
    } catch {
      return serverUrl.trim()
    }
  }, [serverUrl])

  const connectedAgent = findConnectedAgent(agents, initialAgentIds, createdToken, agentName)
  const serverUrlIsInvalid = !normalizedServerUrl.startsWith('http')
  const canContinue =
    step === 1 ? agentName.trim().length > 0 : step === 2 ? !serverUrlIsInvalid : true

  const handleGenerate = async () => {
    setError(null)
    try {
      const token = await onCreateToken({
        name: agentName.trim(),
        ...expiryPayload(expiry),
      })
      setCreatedToken(token)
      setStep(3)
    } catch (err) {
      const message =
        err && typeof err === 'object' && 'message' in err
          ? String((err as { message?: string }).message)
          : 'Failed to create enrollment token'
      setError(message)
    }
  }

  const renderPlatformStep = () => (
    <Stack spacing={1.5}>
      <Typography color="text.secondary">
        Choose the client platform. Linux and Raspberry Pi OS are available in this phase.
      </Typography>
      <Box
        sx={{
          display: 'grid',
          gap: 1.25,
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, 1fr))' },
        }}
      >
        <Paper
          variant="outlined"
          sx={{
            p: 1.5,
            borderColor: 'primary.main',
            bgcolor: 'action.hover',
            borderRadius: 1,
          }}
        >
          <Stack spacing={1}>
            <Stack direction="row" spacing={1} alignItems="center">
              <Server size={18} />
              <Typography fontWeight={700}>Linux / Raspberry Pi</Typography>
            </Stack>
            <Chip size="small" color="primary" label="Selected" sx={{ alignSelf: 'flex-start' }} />
          </Stack>
        </Paper>
        {[
          { label: 'macOS', Icon: Laptop },
          { label: 'Windows', Icon: Monitor },
        ].map(({ label, Icon }) => (
          <Paper
            key={label}
            variant="outlined"
            sx={{ p: 1.5, borderRadius: 1, opacity: 0.62, bgcolor: 'background.paper' }}
          >
            <Stack spacing={1}>
              <Stack direction="row" spacing={1} alignItems="center">
                <Icon size={18} />
                <Typography fontWeight={700}>{label}</Typography>
              </Stack>
              <Chip size="small" label="Coming later" sx={{ alignSelf: 'flex-start' }} />
            </Stack>
          </Paper>
        ))}
      </Box>
    </Stack>
  )

  const renderDetailsStep = () => (
    <Stack spacing={2}>
      <TextField
        label="Agent name"
        value={agentName}
        onChange={(event) => setAgentName(event.target.value)}
        fullWidth
        autoFocus
      />
      <FormControl fullWidth>
        <InputLabel id="agent-token-expiry-label">Token expiry</InputLabel>
        <Select
          labelId="agent-token-expiry-label"
          label="Token expiry"
          value={expiry}
          onChange={(event) => setExpiry(event.target.value as ExpiryOption)}
        >
          {expiryOptions.map((option) => (
            <MenuItem key={option.value} value={option.value}>
              {option.label}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
    </Stack>
  )

  const renderServerStep = () => (
    <Stack spacing={2}>
      <TextField
        label="Server URL"
        value={serverUrl}
        onChange={(event) => setServerUrl(event.target.value)}
        error={serverUrlIsInvalid}
        helperText="This URL must be reachable from the agent machine."
        fullWidth
        autoFocus
      />
      {isLocalAgentServerUrl(normalizedServerUrl) ? (
        <Alert severity="warning">
          localhost only works when the agent runs on the same machine as Borg UI. Remote machines
          need a reachable host name, IP address, or HTTPS URL.
        </Alert>
      ) : null}
    </Stack>
  )

  const renderCommandStep = () =>
    createdToken ? (
      <AgentInstallCommand
        serverUrl={normalizedServerUrl}
        token={createdToken.token}
        agentName={agentName.trim()}
        connectedAgent={connectedAgent}
        onCopy={onCopy}
      />
    ) : null

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md" aria-labelledby="add-agent-title">
      <DialogTitle id="add-agent-title">
        <Stack direction="row" spacing={1} alignItems="center">
          <Terminal size={19} />
          <Typography variant="h6" fontWeight={700}>
            Add Agent
          </Typography>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2.5} sx={{ mt: 0.5 }}>
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            {['Platform', 'Details', 'Server URL', 'Install command'].map((label, index) => (
              <Chip
                key={label}
                label={label}
                color={step === index ? 'primary' : index < step ? 'success' : 'default'}
                variant={step === index ? 'filled' : 'outlined'}
                size="small"
              />
            ))}
          </Stack>
          {step === 0
            ? renderPlatformStep()
            : step === 1
              ? renderDetailsStep()
              : step === 2
                ? renderServerStep()
                : renderCommandStep()}
          {error ? <Alert severity="error">{error}</Alert> : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{step === 3 ? 'Close' : 'Cancel'}</Button>
        <Box sx={{ flex: 1 }} />
        <Button
          disabled={step === 0 || creatingToken}
          onClick={() => setStep((step - 1) as WizardStep)}
        >
          Back
        </Button>
        {step < 2 ? (
          <Button
            variant="contained"
            onClick={() => setStep((step + 1) as WizardStep)}
            disabled={!canContinue}
          >
            Next
          </Button>
        ) : step === 2 ? (
          <Button
            variant="contained"
            onClick={handleGenerate}
            disabled={!canContinue || creatingToken}
          >
            Generate install command
          </Button>
        ) : null}
      </DialogActions>
    </Dialog>
  )
}

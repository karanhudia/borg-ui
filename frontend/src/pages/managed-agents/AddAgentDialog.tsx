import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  DialogActions,
  FormControl,
  FormControlLabel,
  FormHelperText,
  FormLabel,
  InputLabel,
  MenuItem,
  Paper,
  Radio,
  RadioGroup,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { AlertTriangle, Globe, Laptop, Monitor, Server, Settings, Terminal } from 'lucide-react'
import WizardDialog, { type WizardStep } from '../../components/shared/WizardDialog'
import type {
  AgentEnrollmentTokenCreate,
  AgentEnrollmentTokenCreated,
  AgentMachineResponse,
} from '../../services/api'
import AgentInstallCommand from './AgentInstallCommand'
import type { AgentServiceUserMode, BorgInstallMode } from './agentInstallCommandText'
import { isLocalAgentServerUrl, normalizeAgentServerUrl } from './agentServerUrl'

type WizardStepIndex = 0 | 1 | 2

const wizardSteps: WizardStep[] = [
  { key: 'location', label: 'Target', icon: <Globe size={16} /> },
  { key: 'config', label: 'Details', icon: <Settings size={16} /> },
  { key: 'review', label: 'Install', icon: <Terminal size={16} /> },
]

function InlineWarning({ children }: { children: ReactNode }) {
  return (
    <Box
      component="span"
      sx={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 0.75,
        minWidth: 0,
      }}
    >
      <Box
        component="span"
        aria-hidden
        sx={{
          flexShrink: 0,
          display: 'inline-flex',
          alignItems: 'center',
          height: '1.5em',
          color: 'warning.main',
        }}
      >
        <AlertTriangle size={14} />
      </Box>
      <Box component="span" sx={{ minWidth: 0 }}>
        {children}
      </Box>
    </Box>
  )
}

type ExpiryOption = '1h' | '24h' | '7d' | '30d' | 'never'

const expiryOptions: Array<{ value: ExpiryOption; label: string }> = [
  { value: '1h', label: '1 hour' },
  { value: '24h', label: '24 hours' },
  { value: '7d', label: '7 days' },
  { value: '30d', label: '30 days' },
  { value: 'never', label: 'Never' },
]

const borgInstallOptions: Array<{
  value: BorgInstallMode
  label: string
  description: string
}> = [
  {
    value: 'borg1',
    label: 'Borg 1.x',
    description: "Default. Installs or verifies Borg 1 as 'borg'.",
  },
  {
    value: 'borg2',
    label: 'Borg 2.x beta only',
    description: "Advanced experimental option. Installs or verifies Borg 2 as 'borg2'.",
  },
  {
    value: 'both',
    label: 'Borg 1.x and Borg 2.x beta',
    description: "Advanced experimental option. Keeps Borg 1 as 'borg' and Borg 2 as 'borg2'.",
  },
  {
    value: 'skip',
    label: 'Skip Borg install',
    description: 'Use this when Borg is managed separately on the agent machine.',
  },
]

const serviceUserOptions: Array<{
  value: AgentServiceUserMode
  label: string
  description: string
}> = [
  {
    value: 'current',
    label: 'Installing user',
    description: 'The agent can access the same files as the user running the installer.',
  },
  {
    value: 'dedicated',
    label: 'Dedicated borg-ui-agent user',
    description: 'Use a separate low-privilege service account for stricter isolation.',
  },
  {
    value: 'root',
    label: 'Root',
    description: 'Use only when the agent must back up root-owned paths.',
  },
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
  initialBorgInstallMode = 'borg1',
  initialServiceUserMode = 'current',
}: {
  open: boolean
  onClose: () => void
  defaultServerUrl: string
  agents: AgentMachineResponse[]
  onCreateToken: (payload: AgentEnrollmentTokenCreate) => Promise<AgentEnrollmentTokenCreated>
  creatingToken: boolean
  onCopy: (value: string) => void
  initialStep?: WizardStepIndex
  initialAgentName?: string
  initialCreatedToken?: AgentEnrollmentTokenCreated | null
  initialBorgInstallMode?: BorgInstallMode
  initialServiceUserMode?: AgentServiceUserMode
}) {
  const [step, setStep] = useState<WizardStepIndex>(0)
  const [agentName, setAgentName] = useState(initialAgentName)
  const [expiry, setExpiry] = useState<ExpiryOption>('7d')
  const [borgInstallMode, setBorgInstallMode] = useState<BorgInstallMode>(initialBorgInstallMode)
  const [serviceUserMode, setServiceUserMode] =
    useState<AgentServiceUserMode>(initialServiceUserMode)
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
    setBorgInstallMode(initialBorgInstallMode)
    setServiceUserMode(initialServiceUserMode)
    setServerUrl(defaultServerUrl)
    setCreatedToken(initialCreatedToken)
    setError(null)
    setInitialAgentIds(new Set(agents.map((agent) => agent.id)))
  }, [
    open,
    defaultServerUrl,
    agents,
    initialAgentName,
    initialCreatedToken,
    initialStep,
    initialBorgInstallMode,
    initialServiceUserMode,
  ])

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
    step === 0 ? !serverUrlIsInvalid : step === 1 ? agentName.trim().length > 0 : true
  const selectedServiceUserOption =
    serviceUserOptions.find((option) => option.value === serviceUserMode) || serviceUserOptions[0]
  const isRootServiceUser = serviceUserMode === 'root'

  const handleGenerate = async () => {
    setError(null)
    try {
      const token = await onCreateToken({
        name: agentName.trim(),
        ...expiryPayload(expiry),
      })
      setCreatedToken(token)
      setStep(2)
    } catch (err) {
      const message =
        err && typeof err === 'object' && 'message' in err
          ? String((err as { message?: string }).message)
          : 'Failed to create enrollment token'
      setError(message)
    }
  }

  const renderTargetStep = () => (
    <Stack spacing={2.5}>
      <Stack spacing={1.25}>
        <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 0.6 }}>
          Platform
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
                <Typography fontWeight={700}>Linux</Typography>
              </Stack>
              <Chip
                size="small"
                color="primary"
                label="Selected"
                sx={{ alignSelf: 'flex-start' }}
              />
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
      <Stack spacing={1.25}>
        <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 0.6 }}>
          Server URL
        </Typography>
        <TextField
          label="Server URL"
          value={serverUrl}
          onChange={(event) => setServerUrl(event.target.value)}
          error={serverUrlIsInvalid}
          helperText={
            isLocalAgentServerUrl(normalizedServerUrl) && !serverUrlIsInvalid ? (
              <InlineWarning>
                localhost only works when the agent runs on the same machine as Borg UI. Remote
                machines need a reachable host name, IP, or HTTPS URL.
              </InlineWarning>
            ) : (
              'This URL must be reachable from the agent machine.'
            )
          }
          FormHelperTextProps={{
            component: 'div',
            sx: {
              mx: 0,
              ...(isLocalAgentServerUrl(normalizedServerUrl) && !serverUrlIsInvalid
                ? { color: 'warning.main' }
                : null),
            },
          }}
          fullWidth
        />
      </Stack>
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
      <FormControl fullWidth>
        <InputLabel id="agent-service-user-label">Service user</InputLabel>
        <Select
          labelId="agent-service-user-label"
          label="Service user"
          value={serviceUserMode}
          renderValue={(value) =>
            serviceUserOptions.find((option) => option.value === value)?.label || 'Installing user'
          }
          onChange={(event) => setServiceUserMode(event.target.value as AgentServiceUserMode)}
        >
          {serviceUserOptions.map((option) => (
            <MenuItem key={option.value} value={option.value}>
              <Stack spacing={0.25}>
                <Typography fontWeight={700}>{option.label}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {option.description}
                </Typography>
              </Stack>
            </MenuItem>
          ))}
        </Select>
        <FormHelperText
          component="div"
          sx={{ mx: 0, color: isRootServiceUser ? 'warning.main' : undefined }}
        >
          {isRootServiceUser ? (
            <InlineWarning>
              Root mode lets this agent run root-level Borg operations. Use it only for root-owned
              paths.
            </InlineWarning>
          ) : (
            selectedServiceUserOption.description
          )}
        </FormHelperText>
      </FormControl>
      <FormControl component="fieldset">
        <FormLabel component="legend">Borg installation</FormLabel>
        <RadioGroup
          value={borgInstallMode}
          onChange={(event) => setBorgInstallMode(event.target.value as BorgInstallMode)}
          sx={{
            mt: 1,
            display: 'grid',
            gap: 1,
            gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' },
          }}
        >
          {borgInstallOptions.map((option) => {
            const selected = borgInstallMode === option.value
            return (
              <FormControlLabel
                key={option.value}
                value={option.value}
                control={<Radio />}
                label={
                  <Stack spacing={0.35} sx={{ minWidth: 0 }}>
                    <Typography fontWeight={700}>{option.label}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {option.description}
                    </Typography>
                  </Stack>
                }
                sx={{
                  m: 0,
                  p: 1.25,
                  alignItems: 'flex-start',
                  border: '1px solid',
                  borderColor: selected ? 'primary.main' : 'divider',
                  borderRadius: 1,
                  bgcolor: selected ? 'action.hover' : 'background.paper',
                  cursor: 'pointer',
                  transition: 'border-color 180ms ease, background-color 180ms ease',
                  '&:hover': {
                    borderColor: selected ? 'primary.main' : 'text.secondary',
                    bgcolor: 'action.hover',
                  },
                  '& .MuiFormControlLabel-label': { width: '100%' },
                }}
              />
            )
          })}
        </RadioGroup>
      </FormControl>
    </Stack>
  )

  const renderCommandStep = () =>
    createdToken ? (
      <AgentInstallCommand
        serverUrl={normalizedServerUrl}
        token={createdToken.token}
        agentName={agentName.trim()}
        borgInstallMode={borgInstallMode}
        serviceUserMode={serviceUserMode}
        connectedAgent={connectedAgent}
        onCopy={onCopy}
      />
    ) : null

  return (
    <WizardDialog
      open={open}
      onClose={onClose}
      title={
        <Stack direction="row" spacing={1} alignItems="center">
          <Terminal size={19} />
          <span>Add Agent</span>
        </Stack>
      }
      steps={wizardSteps}
      currentStep={step}
      onStepClick={(idx) => {
        if (idx === 2 && !createdToken) return
        setStep(idx as WizardStepIndex)
      }}
      footer={
        <DialogActions sx={{ px: { xs: 1, sm: 3 }, pb: { xs: 1, sm: 2 } }}>
          <Button onClick={onClose}>{step === 2 ? 'Close' : 'Cancel'}</Button>
          <Box sx={{ flex: 1 }} />
          <Button
            disabled={step === 0 || creatingToken}
            onClick={() => setStep((step - 1) as WizardStepIndex)}
          >
            Back
          </Button>
          {step === 0 ? (
            <Button variant="contained" onClick={() => setStep(1)} disabled={!canContinue}>
              Next
            </Button>
          ) : step === 1 ? (
            <Button
              variant="contained"
              onClick={handleGenerate}
              disabled={!canContinue || creatingToken}
            >
              Generate install command
            </Button>
          ) : null}
        </DialogActions>
      }
    >
      <Stack spacing={2.5}>
        {step === 0 ? renderTargetStep() : step === 1 ? renderDetailsStep() : renderCommandStep()}
        {error ? <Alert severity="error">{error}</Alert> : null}
      </Stack>
    </WizardDialog>
  )
}

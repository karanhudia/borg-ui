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
import { useTranslation } from 'react-i18next'
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

const expiryOptions: ExpiryOption[] = ['1h', '24h', '7d', '30d', 'never']

const borgInstallOptions: BorgInstallMode[] = ['borg1', 'borg2', 'both', 'skip']

const serviceUserOptions: AgentServiceUserMode[] = ['current', 'dedicated', 'root']

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
  const { t } = useTranslation()
  const wizardSteps: WizardStep[] = [
    { key: 'location', label: t('managedAgents.add.steps.target'), icon: <Globe size={16} /> },
    { key: 'config', label: t('managedAgents.add.steps.details'), icon: <Settings size={16} /> },
    { key: 'review', label: t('managedAgents.add.steps.install'), icon: <Terminal size={16} /> },
  ]
  const [step, setStep] = useState<WizardStepIndex>(0)
  const [agentName, setAgentName] = useState(initialAgentName)
  const [expiry, setExpiry] = useState<ExpiryOption>('7d')
  const [borgInstallMode, setBorgInstallMode] = useState<BorgInstallMode>(initialBorgInstallMode)
  const [serviceUserMode, setServiceUserMode] =
    useState<AgentServiceUserMode>(initialServiceUserMode)
  const [defaultPath, setDefaultPath] = useState('')
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
    setDefaultPath('')
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
  const selectedServiceUserOption = serviceUserOptions.includes(serviceUserMode)
    ? serviceUserMode
    : serviceUserOptions[0]
  const isRootServiceUser = serviceUserMode === 'root'

  const handleGenerate = async () => {
    setError(null)
    try {
      const trimmedDefaultPath = defaultPath.trim()
      const token = await onCreateToken({
        name: agentName.trim(),
        ...(trimmedDefaultPath ? { default_path: trimmedDefaultPath } : {}),
        ...expiryPayload(expiry),
      })
      setCreatedToken(token)
      setStep(2)
    } catch (err) {
      const message =
        err && typeof err === 'object' && 'message' in err
          ? String((err as { message?: string }).message)
          : t('managedAgents.add.errors.createToken')
      setError(message)
    }
  }

  const renderTargetStep = () => (
    <Stack spacing={2.5}>
      <Stack spacing={1.25}>
        <Typography
          variant="overline"
          sx={{
            color: 'text.secondary',
            letterSpacing: 0.6,
          }}
        >
          {t('managedAgents.add.platform')}
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
              <Stack
                direction="row"
                spacing={1}
                sx={{
                  alignItems: 'center',
                }}
              >
                <Server size={18} />
                <Typography
                  sx={{
                    fontWeight: 700,
                  }}
                >
                  {t('managedAgents.add.platforms.linux')}
                </Typography>
              </Stack>
              <Chip
                size="small"
                color="primary"
                label={t('managedAgents.add.selected')}
                sx={{ alignSelf: 'flex-start' }}
              />
            </Stack>
          </Paper>
          {[
            { label: t('managedAgents.add.platforms.macos'), Icon: Laptop },
            { label: t('managedAgents.add.platforms.windows'), Icon: Monitor },
          ].map(({ label, Icon }) => (
            <Paper
              key={label}
              variant="outlined"
              sx={{ p: 1.5, borderRadius: 1, opacity: 0.62, bgcolor: 'background.paper' }}
            >
              <Stack spacing={1}>
                <Stack
                  direction="row"
                  spacing={1}
                  sx={{
                    alignItems: 'center',
                  }}
                >
                  <Icon size={18} />
                  <Typography
                    sx={{
                      fontWeight: 700,
                    }}
                  >
                    {label}
                  </Typography>
                </Stack>
                <Chip
                  size="small"
                  label={t('managedAgents.add.comingLater')}
                  sx={{ alignSelf: 'flex-start' }}
                />
              </Stack>
            </Paper>
          ))}
        </Box>
      </Stack>
      <Stack spacing={1.25}>
        <Typography
          variant="overline"
          sx={{
            color: 'text.secondary',
            letterSpacing: 0.6,
          }}
        >
          {t('managedAgents.add.serverUrl')}
        </Typography>
        <TextField
          label={t('managedAgents.add.serverUrl')}
          value={serverUrl}
          onChange={(event) => setServerUrl(event.target.value)}
          error={serverUrlIsInvalid}
          helperText={
            isLocalAgentServerUrl(normalizedServerUrl) && !serverUrlIsInvalid ? (
              <InlineWarning>{t('managedAgents.add.localhostWarning')}</InlineWarning>
            ) : (
              t('managedAgents.add.serverUrlHelper')
            )
          }
          fullWidth
          slotProps={{
            formHelperText: {
              component: 'div',
              sx: {
                mx: 0,
                ...(isLocalAgentServerUrl(normalizedServerUrl) && !serverUrlIsInvalid
                  ? { color: 'warning.main' }
                  : null),
              },
            },
          }}
        />
      </Stack>
    </Stack>
  )

  const renderDetailsStep = () => (
    <Stack spacing={2}>
      <TextField
        label={t('managedAgents.add.agentName')}
        value={agentName}
        onChange={(event) => setAgentName(event.target.value)}
        fullWidth
        autoFocus
      />
      <TextField
        label={t('managedAgents.add.defaultPath')}
        value={defaultPath}
        onChange={(event) => setDefaultPath(event.target.value)}
        placeholder="/home/karanhudia"
        helperText={t('managedAgents.add.defaultPathHelper')}
        fullWidth
      />
      <FormControl fullWidth>
        <InputLabel id="agent-token-expiry-label">{t('managedAgents.add.tokenExpiry')}</InputLabel>
        <Select
          labelId="agent-token-expiry-label"
          label={t('managedAgents.add.tokenExpiry')}
          value={expiry}
          onChange={(event) => setExpiry(event.target.value as ExpiryOption)}
        >
          {expiryOptions.map((option) => (
            <MenuItem key={option} value={option}>
              {t(`managedAgents.add.expiry.${option}`)}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      <FormControl fullWidth>
        <InputLabel id="agent-service-user-label">{t('managedAgents.add.serviceUser')}</InputLabel>
        <Select
          labelId="agent-service-user-label"
          label={t('managedAgents.add.serviceUser')}
          value={serviceUserMode}
          renderValue={(value) => t(`managedAgents.add.serviceUsers.${value}.label`)}
          onChange={(event) => setServiceUserMode(event.target.value as AgentServiceUserMode)}
        >
          {serviceUserOptions.map((option) => (
            <MenuItem key={option} value={option}>
              <Stack spacing={0.25}>
                <Typography
                  sx={{
                    fontWeight: 700,
                  }}
                >
                  {t(`managedAgents.add.serviceUsers.${option}.label`)}
                </Typography>
                <Typography
                  variant="body2"
                  sx={{
                    color: 'text.secondary',
                  }}
                >
                  {t(`managedAgents.add.serviceUsers.${option}.description`)}
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
            <InlineWarning>{t('managedAgents.add.rootWarning')}</InlineWarning>
          ) : (
            t(`managedAgents.add.serviceUsers.${selectedServiceUserOption}.description`)
          )}
        </FormHelperText>
      </FormControl>
      <FormControl component="fieldset">
        <FormLabel component="legend">{t('managedAgents.add.borgInstallation')}</FormLabel>
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
            const selected = borgInstallMode === option
            return (
              <FormControlLabel
                key={option}
                value={option}
                control={<Radio />}
                label={
                  <Stack spacing={0.35} sx={{ minWidth: 0 }}>
                    <Typography
                      sx={{
                        fontWeight: 700,
                      }}
                    >
                      {t(`managedAgents.add.borgOptions.${option}.label`)}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        color: 'text.secondary',
                      }}
                    >
                      {t(`managedAgents.add.borgOptions.${option}.description`)}
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
        <Stack
          direction="row"
          spacing={1}
          sx={{
            alignItems: 'center',
          }}
        >
          <Terminal size={19} />
          <span>{t('managedAgents.add.title')}</span>
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
          <Button onClick={onClose}>
            {step === 2 ? t('common.buttons.close') : t('common.buttons.cancel')}
          </Button>
          <Box sx={{ flex: 1 }} />
          <Button
            disabled={step === 0 || creatingToken}
            onClick={() => setStep((step - 1) as WizardStepIndex)}
          >
            {t('common.buttons.back')}
          </Button>
          {step === 0 ? (
            <Button variant="contained" onClick={() => setStep(1)} disabled={!canContinue}>
              {t('common.buttons.next')}
            </Button>
          ) : step === 1 ? (
            <Button
              variant="contained"
              onClick={handleGenerate}
              disabled={!canContinue || creatingToken}
            >
              {t('managedAgents.add.generateInstallCommand')}
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

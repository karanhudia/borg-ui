import {
  Box,
  TextField,
  FormControl,
  FormControlLabel,
  Checkbox,
  InputLabel,
  Select,
  MenuItem,
  Typography,
  Alert,
  InputAdornment,
  IconButton,
  alpha,
  ButtonBase,
  Tooltip,
  Chip,
  Stack,
} from '@mui/material'
import { Cloud, Laptop } from 'lucide-react'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'
import { useTranslation } from 'react-i18next'
import PlanGate from '../PlanGate'
import { getDestinations, type DestinationKey } from './destinations'
import {
  formatDirectRcloneUrl,
  normalizeRcloneRemotePath,
  parseDirectRcloneUrl,
} from './directRclonePath'
import RichSelectRow from './RichSelectRow'

interface SSHConnection {
  id: number
  host: string
  username: string
  port: number
  ssh_key_id: number
  default_path?: string
  mount_point?: string
  status: string
}

interface AgentMachine {
  id: number
  name: string
  hostname?: string | null
  status: string
}

interface RcloneRemote {
  id: number
  name: string
  provider: string
  last_test_status?: string | null
}

interface RcloneStatus {
  available: boolean
  version?: string | null
  error?: string | null
}

export interface LocationStepData {
  name: string
  borgVersion?: 1 | 2
  repositoryMode: 'full' | 'observe'
  repositoryLocation: 'local' | 'ssh' | 'rclone'
  executionTarget?: 'local' | 'agent'
  agentMachineId?: number | ''
  path: string
  repoSshConnectionId: number | ''
  rcloneRemoteId?: number | ''
  rcloneRemotePath?: string
  bypassLock: boolean
}

interface WizardStepLocationProps {
  mode: 'create' | 'edit' | 'import'
  data: LocationStepData
  sshConnections: SSHConnection[]
  agentMachines?: AgentMachine[]
  rcloneRemotes?: RcloneRemote[]
  rcloneStatus?: RcloneStatus | null
  dataSource?: 'local' | 'remote'
  sourceSshConnectionId?: number | ''
  onChange: (data: Partial<LocationStepData>) => void
  onBrowsePath: () => void
  onBrowseDirectRclonePath?: () => void
}

export default function WizardStepLocation({
  mode,
  data,
  sshConnections,
  agentMachines = [],
  rcloneRemotes = [],
  rcloneStatus = null,
  dataSource,
  sourceSshConnectionId,
  onChange,
  onBrowsePath,
  onBrowseDirectRclonePath,
}: WizardStepLocationProps) {
  const { t } = useTranslation()
  const executionTarget = data.executionTarget ?? 'local'
  const agentMachineId = data.agentMachineId ?? ''
  const isAgentExecution = executionTarget === 'agent'
  const isDirectRclone = data.repositoryLocation === 'rclone'
  const borgVersion = data.borgVersion ?? 1
  const parsedDirectRclonePath = isDirectRclone ? parseDirectRcloneUrl(data.path) : null
  const selectedDirectRcloneRemote =
    data.rcloneRemoteId === '' || data.rcloneRemoteId == null
      ? parsedDirectRclonePath
        ? rcloneRemotes.find((remote) => remote.name === parsedDirectRclonePath.remoteName)
        : undefined
      : rcloneRemotes.find((remote) => remote.id === data.rcloneRemoteId)
  const directRcloneRemotePath = data.rcloneRemotePath ?? parsedDirectRclonePath?.remotePath ?? ''
  const directRcloneRemoteSelectEnabled =
    isDirectRclone && rcloneStatus?.available === true && rcloneRemotes.length > 0
  const directRcloneBrowseEnabled =
    directRcloneRemoteSelectEnabled &&
    Boolean(selectedDirectRcloneRemote) &&
    Boolean(onBrowseDirectRclonePath)

  // Legacy v1 repos with an attached remote data source can't be retargeted to another
  // remote — remote-to-remote was never supported in the v1 mapping model.
  const isLegacyRemoteSource = mode === 'edit' && dataSource === 'remote' && !!sourceSshConnectionId
  const isRemoteLocationDisabled = isLegacyRemoteSource
  const isAgentLocationDisabled = isLegacyRemoteSource

  const queueableAgents = agentMachines.filter(
    (agent) => agent.status !== 'revoked' && agent.status !== 'disabled'
  )

  const destinations = getDestinations({ isRemoteLocationDisabled, isAgentLocationDisabled })

  const selectedDestinationKey: DestinationKey = isAgentExecution
    ? 'agent'
    : data.repositoryLocation === 'ssh'
      ? 'ssh'
      : 'server'

  const handleDestinationChange = (key: DestinationKey) => {
    if (key === 'ssh' && isRemoteLocationDisabled) return
    if (key === 'agent' && isAgentLocationDisabled) return

    if (key === 'agent') {
      onChange({
        repositoryLocation: 'local',
        executionTarget: 'agent',
        repoSshConnectionId: '',
      })
      return
    }

    onChange({
      repositoryLocation: key === 'ssh' ? 'ssh' : 'local',
      executionTarget: 'local',
      agentMachineId: '',
      repoSshConnectionId: key === 'ssh' ? data.repoSshConnectionId : '',
    })
  }

  const handleDirectRcloneChange = (checked: boolean) => {
    onChange({
      borgVersion: 2,
      repositoryLocation: checked ? 'rclone' : 'local',
      executionTarget: 'local',
      agentMachineId: '',
      repoSshConnectionId: '',
    })
  }

  const handleDirectRcloneRemoteChange = (remoteId: string) => {
    const remote = rcloneRemotes.find((item) => String(item.id) === remoteId)
    if (!remote) {
      onChange({
        rcloneRemoteId: '',
      })
      return
    }

    const remotePath = normalizeRcloneRemotePath(directRcloneRemotePath)
    onChange({
      rcloneRemoteId: remote.id,
      rcloneRemotePath: remotePath,
      path: formatDirectRcloneUrl(remote.name, remotePath),
    })
  }

  const handleDirectRclonePathChange = (value: string) => {
    const parsed = parseDirectRcloneUrl(value)
    const matchingRemote = parsed
      ? rcloneRemotes.find((remote) => remote.name === parsed.remoteName)
      : undefined

    onChange({
      path: value,
      ...(parsed
        ? {
            rcloneRemoteId: matchingRemote?.id ?? '',
            rcloneRemotePath: parsed.remotePath,
          }
        : {}),
    })
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {/* Name Input */}
      <TextField
        label={t('wizard.location.repositoryNameLabel')}
        value={data.name}
        onChange={(e) => onChange({ name: e.target.value })}
        required
        fullWidth
        helperText={t('wizard.location.repositoryNameHelper')}
      />

      {/* Borg Version Selector — only shown on create/import, not edit */}
      {mode !== 'edit' && (
        <PlanGate feature="borg_v2" disabled>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
              <Typography variant="body2" color="text.secondary" sx={{ flexShrink: 0 }}>
                Borg Version
              </Typography>
              <Box
                sx={{
                  display: 'flex',
                  p: '3px',
                  bgcolor: 'action.hover',
                  borderRadius: '10px',
                  gap: '2px',
                }}
              >
                {([1, 2] as const).map((v) => {
                  const selected = (data.borgVersion ?? 1) === v
                  return (
                    <ButtonBase
                      key={v}
                      onClick={() => onChange({ borgVersion: v })}
                      sx={{
                        px: 1.75,
                        py: 0.5,
                        borderRadius: '8px',
                        bgcolor: selected ? 'background.paper' : 'transparent',
                        boxShadow: selected ? 1 : 0,
                        fontWeight: selected ? 700 : 400,
                        fontSize: '0.8rem',
                        color: selected ? 'text.primary' : 'text.secondary',
                        transition: 'all 0.15s ease',
                        fontFamily: 'monospace',
                        letterSpacing: 0.3,
                      }}
                    >
                      v{v}
                    </ButtonBase>
                  )
                })}
              </Box>
              {(data.borgVersion ?? 1) === 2 && (
                <Tooltip title={t('wizard.location.borgV2Warning')} arrow placement="right">
                  <Chip
                    label="Beta"
                    size="small"
                    color="warning"
                    variant="outlined"
                    sx={{ height: 22, fontWeight: 600, cursor: 'help' }}
                  />
                </Tooltip>
              )}
            </Box>
          </Box>
        </PlanGate>
      )}

      {/* Repository Mode for Import */}
      {mode === 'import' && (
        <FormControl fullWidth>
          <InputLabel>{t('wizard.location.repositoryModeLabel')}</InputLabel>
          <Select
            value={data.repositoryMode}
            label={t('wizard.location.repositoryModeLabel')}
            onChange={(e) => onChange({ repositoryMode: e.target.value as 'full' | 'observe' })}
          >
            <MenuItem value="full">
              <Box>
                <Typography variant="body2" fontWeight={600}>
                  {t('wizard.location.fullRepository')}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {t('wizard.location.fullRepositoryDesc')}
                </Typography>
              </Box>
            </MenuItem>
            <MenuItem value="observe">
              <Box>
                <Typography variant="body2" fontWeight={600}>
                  {t('wizard.location.observabilityOnly')}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {t('wizard.location.observabilityOnlyDesc')}
                </Typography>
              </Box>
            </MenuItem>
          </Select>
        </FormControl>
      )}

      {mode === 'import' && data.repositoryMode === 'observe' && (
        <Typography variant="body2" color="text.secondary">
          {t('wizard.location.observabilityInfo')}
        </Typography>
      )}

      {/* Read-only storage access option for observe mode */}
      {data.repositoryMode === 'observe' && (
        <FormControlLabel
          control={
            <Checkbox
              checked={data.bypassLock}
              onChange={(e) => onChange({ bypassLock: e.target.checked })}
            />
          }
          label={
            <Box>
              <Typography variant="body2">{t('wizard.location.readOnlyStorageLabel')}</Typography>
              <Typography variant="caption" color="text.secondary">
                {t('wizard.location.readOnlyStorageDesc')}
              </Typography>
            </Box>
          }
        />
      )}

      {/* Destination picker */}
      {!isDirectRclone && (
        <FormControl fullWidth>
          <InputLabel id="destination-select-label">{t('wizard.location.whereToStore')}</InputLabel>
          <Select
            labelId="destination-select-label"
            id="destination-select"
            value={selectedDestinationKey}
            label={t('wizard.location.whereToStore')}
            onChange={(e) => handleDestinationChange(e.target.value as DestinationKey)}
            renderValue={(value) => {
              const dest = destinations.find((d) => d.key === value)
              if (!dest) return null
              return (
                <RichSelectRow
                  icon={dest.icon}
                  primary={t(dest.labelKey)}
                  secondary={t(dest.descriptionKey)}
                />
              )
            }}
            sx={{ '& .MuiSelect-select': { minHeight: 36 } }}
          >
            {destinations.map((dest) => (
              <MenuItem key={dest.key} value={dest.key} disabled={dest.disabled} sx={{ py: 1 }}>
                <RichSelectRow
                  icon={dest.icon}
                  primary={t(dest.labelKey)}
                  secondary={t(dest.descriptionKey)}
                />
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      )}

      {isRemoteLocationDisabled && (
        <Typography variant="body2" color="text.secondary">
          <strong>{t('wizard.dataSource.remoteToRemoteTitle')}</strong>{' '}
          {t('wizard.location.remoteDisabledInfo')}
        </Typography>
      )}

      {/* Agent sub-form */}
      {isAgentExecution && !isDirectRclone && (
        <Stack spacing={1.25}>
          {queueableAgents.length === 0 ? (
            <Alert severity="warning">{t('wizard.location.noActiveManagedAgents')}</Alert>
          ) : (
            <FormControl fullWidth>
              <InputLabel id="managed-agent-select-label">
                {t('wizard.location.managedAgentSelectLabel')}
              </InputLabel>
              <Select
                labelId="managed-agent-select-label"
                id="managed-agent-select"
                value={agentMachineId === '' ? '' : String(agentMachineId)}
                label={t('wizard.location.managedAgentSelectLabel')}
                onChange={(e) => {
                  const value = e.target.value
                  onChange({ agentMachineId: value ? Number(value) : '' })
                }}
                renderValue={(selected) => {
                  if (!selected) return null
                  const agent = queueableAgents.find((a) => String(a.id) === selected)
                  if (!agent) return null
                  return renderAgentRow(agent)
                }}
                sx={{ '& .MuiSelect-select': { minHeight: 36 } }}
              >
                {queueableAgents.map((agent) => (
                  <MenuItem key={agent.id} value={String(agent.id)} sx={{ py: 1 }}>
                    {renderAgentRow(agent)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}
          <Typography variant="body2" color="text.secondary">
            {t('wizard.location.agentStorageNote')}
          </Typography>
        </Stack>
      )}

      {/* SSH sub-form */}
      {!isAgentExecution && data.repositoryLocation === 'ssh' && (
        <>
          {!Array.isArray(sshConnections) || sshConnections.length === 0 ? (
            <Alert severity="warning">{t('wizard.noSshConnections')}</Alert>
          ) : (
            <FormControl fullWidth>
              <InputLabel>{t('wizard.location.selectSshConnection')}</InputLabel>
              <Select
                value={data.repoSshConnectionId === '' ? '' : String(data.repoSshConnectionId)}
                label={t('wizard.location.selectSshConnection')}
                onChange={(e) => {
                  const value = e.target.value
                  if (value) {
                    onChange({ repoSshConnectionId: Number(value) })
                  }
                }}
                renderValue={(selected) => {
                  if (!selected) return null
                  const conn = sshConnections.find((c) => String(c.id) === selected)
                  if (!conn) return null
                  return renderSshRow(conn, t('wizard.location.connected'))
                }}
                sx={{ '& .MuiSelect-select': { minHeight: 36 } }}
              >
                {sshConnections.map((conn) => (
                  <MenuItem key={conn.id} value={String(conn.id)} sx={{ py: 1 }}>
                    {renderSshRow(conn, t('wizard.location.connected'))}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}
        </>
      )}

      {borgVersion === 2 && (
        <Box
          sx={{
            border: '1px solid',
            borderColor: isDirectRclone ? 'warning.main' : 'divider',
            bgcolor: (theme) => alpha(theme.palette.warning.main, isDirectRclone ? 0.08 : 0.03),
            borderRadius: 1,
            p: 2,
            display: 'flex',
            flexDirection: 'column',
            gap: 1,
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
            <Typography variant="subtitle2" fontWeight={700}>
              {t('wizard.location.directRcloneAdvancedTitle')}
            </Typography>
            <Chip
              label="Borg 2"
              size="small"
              variant="outlined"
              color="warning"
              sx={{ height: 20, fontSize: '0.68rem', fontWeight: 700 }}
            />
          </Box>
          <FormControlLabel
            control={
              <Checkbox
                checked={isDirectRclone}
                onChange={(event) => handleDirectRcloneChange(event.target.checked)}
              />
            }
            label={
              <Box>
                <Typography variant="body2" fontWeight={600}>
                  {t('wizard.location.directRcloneLabel')}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {t('wizard.location.directRcloneHelper')}
                </Typography>
              </Box>
            }
          />
        </Box>
      )}

      {isDirectRclone && (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          {rcloneStatus && !rcloneStatus.available && (
            <Alert severity="warning">
              {rcloneStatus.error || t('wizard.location.rcloneUnavailable')}
            </Alert>
          )}

          {directRcloneRemoteSelectEnabled && (
            <FormControl fullWidth>
              <InputLabel id="direct-rclone-remote-label">
                {t('wizard.location.rcloneRemoteLabel')}
              </InputLabel>
              <Select
                labelId="direct-rclone-remote-label"
                id="direct-rclone-remote"
                value={selectedDirectRcloneRemote ? String(selectedDirectRcloneRemote.id) : ''}
                label={t('wizard.location.rcloneRemoteLabel')}
                onChange={(event) => handleDirectRcloneRemoteChange(event.target.value)}
                renderValue={(selected) => {
                  const remote = rcloneRemotes.find((item) => String(item.id) === selected)
                  if (!remote) return null
                  return renderRcloneRemoteRow(remote)
                }}
                sx={{ '& .MuiSelect-select': { minHeight: 36 } }}
              >
                {rcloneRemotes.map((remote) => (
                  <MenuItem key={remote.id} value={String(remote.id)} sx={{ py: 1 }}>
                    {renderRcloneRemoteRow(remote)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}

          {rcloneStatus?.available === true && rcloneRemotes.length === 0 && (
            <Alert severity="info">{t('wizard.location.rcloneNoRemotes')}</Alert>
          )}
        </Box>
      )}

      {/* Path Input */}
      <TextField
        label={
          isDirectRclone
            ? t('wizard.location.directRclonePathLabel')
            : t('wizard.location.repositoryPathLabel')
        }
        value={data.path}
        onChange={(e) =>
          isDirectRclone
            ? handleDirectRclonePathChange(e.target.value)
            : onChange({ path: e.target.value })
        }
        placeholder={
          isDirectRclone
            ? t('wizard.location.directRclonePathPlaceholder')
            : data.repositoryLocation === 'local'
              ? '/backups/my-repo'
              : '/path/on/remote/server'
        }
        required
        fullWidth
        helperText={
          isDirectRclone
            ? t('wizard.location.directRclonePathHelper')
            : t('wizard.location.repositoryPathHelper')
        }
        InputProps={{
          endAdornment: (
            <InputAdornment position="end">
              <IconButton
                onClick={isDirectRclone ? onBrowseDirectRclonePath : onBrowsePath}
                edge="end"
                size="small"
                title={
                  isDirectRclone
                    ? t('wizard.cloudMirror.browseRemote')
                    : t('wizard.location.browseFilesystem')
                }
                aria-label={
                  isDirectRclone
                    ? t('wizard.cloudMirror.browseRemote')
                    : t('wizard.location.browseFilesystem')
                }
                disabled={
                  isDirectRclone
                    ? !directRcloneBrowseEnabled
                    : (isAgentExecution && !data.agentMachineId) ||
                      (data.repositoryLocation === 'ssh' && !data.repoSshConnectionId)
                }
              >
                <FolderOpenIcon fontSize="small" />
              </IconButton>
            </InputAdornment>
          ),
        }}
      />
    </Box>
  )
}

function renderRcloneRemoteRow(remote: RcloneRemote) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
      <Cloud size={16} />
      <Typography variant="body2">{remote.name}</Typography>
      <Chip
        size="small"
        label={remote.provider}
        variant="outlined"
        sx={{ height: 20, fontSize: '0.65rem' }}
      />
      {remote.last_test_status && (
        <Typography variant="caption" color="text.secondary">
          {remote.last_test_status}
        </Typography>
      )}
    </Box>
  )
}

function StatusDot({ color }: { color: string }) {
  return (
    <Box
      sx={{
        width: 8,
        height: 8,
        borderRadius: '50%',
        bgcolor: color,
        flexShrink: 0,
      }}
    />
  )
}

function renderAgentRow(agent: AgentMachine) {
  const isOnline = agent.status === 'online'
  const displayName = agent.hostname || agent.name
  const metaSecondary = agent.hostname && agent.name !== agent.hostname ? agent.name : undefined
  const secondary = [metaSecondary, agent.status].filter(Boolean).join(' · ')

  return (
    <RichSelectRow
      icon={<Laptop size={16} />}
      primary={displayName}
      secondary={secondary}
      indicator={<StatusDot color={isOnline ? 'success.main' : 'text.disabled'} />}
    />
  )
}

function renderSshRow(conn: SSHConnection, connectedLabel: string) {
  const secondary = `Port ${conn.port}${conn.mount_point ? ` • ${conn.mount_point}` : ''}`
  return (
    <RichSelectRow
      icon={<Cloud size={16} />}
      primary={`${conn.username}@${conn.host}`}
      secondary={secondary}
      indicator={
        conn.status === 'connected' ? (
          <Box title={connectedLabel} sx={{ display: 'flex' }}>
            <StatusDot color="success.main" />
          </Box>
        ) : undefined
      }
    />
  )
}

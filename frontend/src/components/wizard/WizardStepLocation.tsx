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
  Card,
  CardContent,
  CardActionArea,
  InputAdornment,
  IconButton,
  alpha,
  ButtonBase,
  Tooltip,
  Chip,
} from '@mui/material'
import { Server, Cloud, Laptop } from 'lucide-react'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'
import { useTranslation } from 'react-i18next'
import PlanGate from '../PlanGate'

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

export interface LocationStepData {
  name: string
  borgVersion?: 1 | 2
  repositoryMode: 'full' | 'observe'
  repositoryLocation: 'local' | 'ssh' | 'rclone'
  executionTarget?: 'local' | 'agent'
  agentMachineId?: number | ''
  path: string
  repoSshConnectionId: number | ''
  bypassLock: boolean
  rcloneRemoteId?: number | ''
  rcloneRemotePath?: string
  rcloneSyncPolicy?: 'after_success' | 'manual' | 'scheduled'
  rcloneExtraFlags?: string
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

interface WizardStepLocationProps {
  mode: 'create' | 'edit' | 'import'
  data: LocationStepData
  sshConnections: SSHConnection[]
  agentMachines?: AgentMachine[]
  rcloneRemotes?: RcloneRemote[]
  rcloneStatus?: RcloneStatus | null
  dataSource?: 'local' | 'remote' // Data source from step 2
  sourceSshConnectionId?: number | '' // Source SSH connection ID
  onChange: (data: Partial<LocationStepData>) => void
  onBrowsePath: () => void
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
}: WizardStepLocationProps) {
  const { t } = useTranslation()
  const executionTarget = data.executionTarget ?? 'local'
  const agentMachineId = data.agentMachineId ?? ''
  const isAgentExecution = executionTarget === 'agent'

  // Disable SSH repository location if data source is remote (prevent remote-to-remote)
  // Only enforce this in edit mode when we know the data source
  const isRemoteLocationDisabled =
    isAgentExecution || (mode === 'edit' && dataSource === 'remote' && !!sourceSshConnectionId)
  const isRcloneAvailable = rcloneStatus?.available !== false

  const handleLocationChange = (location: 'local' | 'ssh' | 'rclone') => {
    if (location === 'ssh' && isRemoteLocationDisabled) {
      return // Don't allow switching to SSH if data source is remote
    }
    if (location === 'rclone' && !isRcloneAvailable) {
      return
    }
    onChange({
      repositoryLocation: location,
      repoSshConnectionId: location === 'ssh' ? data.repoSshConnectionId : '',
      path: location === 'rclone' ? data.rcloneRemotePath || data.path : data.path,
    })
  }

  const queueableAgents = agentMachines.filter(
    (agent) => agent.status !== 'revoked' && agent.status !== 'disabled'
  )

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

      {/* Repository Ownership Selection */}
      <Box
        sx={{
          display: 'flex',
          alignItems: { xs: 'stretch', sm: 'center' },
          gap: 1.5,
          flexDirection: { xs: 'column', sm: 'row' },
          minHeight: { sm: 40 },
        }}
      >
        <Typography variant="body2" color="text.secondary" sx={{ flexShrink: 0 }}>
          {t('wizard.location.executionTargetLabel')}
        </Typography>
        <Box
          sx={{
            display: 'flex',
            p: '3px',
            bgcolor: 'action.hover',
            borderRadius: '10px',
            gap: '2px',
            width: { xs: '100%', sm: 'auto' },
          }}
        >
          {[
            {
              value: 'local' as const,
              label: t('wizard.location.executionTargetLocal'),
              icon: Server,
            },
            { value: 'agent' as const, label: t('wizard.location.managedAgent'), icon: Laptop },
          ].map((option) => {
            const selected = executionTarget === option.value
            const Icon = option.icon
            return (
              <ButtonBase
                key={option.value}
                onClick={() =>
                  onChange(
                    option.value === 'agent'
                      ? {
                          executionTarget: 'agent',
                          repositoryLocation: 'local',
                          repoSshConnectionId: '',
                        }
                      : { executionTarget: 'local', agentMachineId: '' }
                  )
                }
                sx={{
                  px: 1.5,
                  py: 0.65,
                  borderRadius: '8px',
                  bgcolor: selected ? 'background.paper' : 'transparent',
                  boxShadow: selected ? 1 : 0,
                  fontWeight: selected ? 700 : 500,
                  fontSize: '0.8rem',
                  color: selected ? 'text.primary' : 'text.secondary',
                  transition: 'background-color 0.15s ease, color 0.15s ease',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 0.75,
                  flex: { xs: 1, sm: '0 0 auto' },
                }}
              >
                <Icon size={14} />
                {option.label}
              </ButtonBase>
            )
          })}
        </Box>
        {isAgentExecution &&
          (queueableAgents.length === 0 ? (
            <Alert severity="warning" sx={{ flex: 1 }}>
              {t('wizard.location.noActiveManagedAgents')}
            </Alert>
          ) : (
            <FormControl sx={{ minWidth: { xs: '100%', sm: 260 }, flex: 1 }} size="small">
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
                sx={{
                  '& .MuiSelect-select': {
                    display: 'flex',
                    alignItems: 'center',
                  },
                }}
              >
                {queueableAgents.map((agent) => (
                  <MenuItem key={agent.id} value={String(agent.id)}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                      <Laptop size={16} style={{ flexShrink: 0, opacity: 0.7 }} />
                      <Typography variant="body2" noWrap>
                        {agent.hostname || agent.name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" noWrap>
                        · {agent.status}
                      </Typography>
                    </Box>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          ))}
      </Box>

      {/* Location Selection Cards — hidden in agent mode (only filesystem storage supported) */}
      {!isAgentExecution && (
        <Box>
          <Typography variant="subtitle2" gutterBottom sx={{ mb: 2, fontWeight: 600 }}>
            {t('wizard.location.whereToStore')}
          </Typography>
          <Box
            sx={{
              display: 'flex',
              gap: 2,
              p: 0.5,
              m: -0.5,
              flexDirection: { xs: 'column', sm: 'row' },
            }}
          >
            <Card
              variant="outlined"
              sx={{
                flex: 1,
                border: data.repositoryLocation === 'local' ? 2 : 1,
                borderColor: data.repositoryLocation === 'local' ? 'primary.main' : 'divider',
                boxShadow:
                  data.repositoryLocation === 'local'
                    ? (theme) => `0 4px 12px ${alpha(theme.palette.primary.main, 0.2)}`
                    : 'none',
                bgcolor:
                  data.repositoryLocation === 'local'
                    ? (theme) => alpha(theme.palette.primary.main, 0.08)
                    : 'background.paper',
                transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                transform: data.repositoryLocation === 'local' ? 'translateY(-2px)' : 'none',
                '&:hover': {
                  transform: 'translateY(-2px)',
                  boxShadow: (theme) => `0 4px 12px ${alpha(theme.palette.text.primary, 0.08)}`,
                  borderColor:
                    data.repositoryLocation === 'local' ? 'primary.main' : 'text.primary',
                },
              }}
            >
              <CardActionArea onClick={() => handleLocationChange('local')} sx={{ p: 1 }}>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
                    <Box
                      sx={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        width: 48,
                        height: 48,
                        borderRadius: 3,
                        bgcolor:
                          data.repositoryLocation === 'local' ? 'primary.main' : 'action.hover',
                        color: data.repositoryLocation === 'local' ? 'white' : 'text.secondary',
                        transition: 'all 0.3s ease',
                        boxShadow:
                          data.repositoryLocation === 'local'
                            ? (theme) => `0 4px 12px ${alpha(theme.palette.primary.main, 0.4)}`
                            : 'none',
                      }}
                    >
                      <Server size={28} />
                    </Box>
                    <Box>
                      <Typography variant="h6" sx={{ fontSize: '1rem', fontWeight: 600 }}>
                        {t('wizard.borgUiServer')}
                      </Typography>
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{ fontSize: '0.8125rem' }}
                      >
                        {t('wizard.location.borgUiServerDesc')}
                      </Typography>
                    </Box>
                  </Box>
                </CardContent>
              </CardActionArea>
            </Card>

            <Card
              variant="outlined"
              sx={{
                flex: 1,
                border: data.repositoryLocation === 'ssh' ? 2 : 1,
                borderColor: data.repositoryLocation === 'ssh' ? 'primary.main' : 'divider',
                boxShadow:
                  data.repositoryLocation === 'ssh'
                    ? (theme) => `0 4px 12px ${alpha(theme.palette.primary.main, 0.2)}`
                    : 'none',
                bgcolor:
                  data.repositoryLocation === 'ssh'
                    ? (theme) => alpha(theme.palette.primary.main, 0.08)
                    : 'background.paper',
                opacity: isRemoteLocationDisabled ? 0.5 : 1,
                transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                transform: data.repositoryLocation === 'ssh' ? 'translateY(-2px)' : 'none',
                '&:hover': !isRemoteLocationDisabled
                  ? {
                      transform: 'translateY(-2px)',
                      boxShadow: (theme) => `0 4px 12px ${alpha(theme.palette.text.primary, 0.08)}`,
                      borderColor:
                        data.repositoryLocation === 'ssh' ? 'primary.main' : 'text.primary',
                    }
                  : {},
              }}
            >
              <CardActionArea
                onClick={() => handleLocationChange('ssh')}
                disabled={isRemoteLocationDisabled}
                sx={{ p: 1 }}
              >
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
                    <Box
                      sx={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        width: 48,
                        height: 48,
                        borderRadius: 3,
                        bgcolor:
                          data.repositoryLocation === 'ssh' ? 'primary.main' : 'action.hover',
                        color: data.repositoryLocation === 'ssh' ? 'white' : 'text.secondary',
                        transition: 'all 0.3s ease',
                        boxShadow:
                          data.repositoryLocation === 'ssh'
                            ? (theme) => `0 4px 12px ${alpha(theme.palette.primary.main, 0.4)}`
                            : 'none',
                      }}
                    >
                      <Cloud size={28} />
                    </Box>
                    <Box>
                      <Typography variant="h6" sx={{ fontSize: '1rem', fontWeight: 600 }}>
                        {t('wizard.remoteClient')}
                      </Typography>
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{ fontSize: '0.8125rem' }}
                      >
                        {t('wizard.location.remoteClientDesc')}
                      </Typography>
                    </Box>
                  </Box>
                </CardContent>
              </CardActionArea>
            </Card>

            <Card
              variant="outlined"
              sx={{
                flex: 1,
                border: data.repositoryLocation === 'rclone' ? 2 : 1,
                borderColor: data.repositoryLocation === 'rclone' ? 'primary.main' : 'divider',
                boxShadow:
                  data.repositoryLocation === 'rclone'
                    ? (theme) => `0 4px 12px ${alpha(theme.palette.primary.main, 0.2)}`
                    : 'none',
                bgcolor:
                  data.repositoryLocation === 'rclone'
                    ? (theme) => alpha(theme.palette.primary.main, 0.08)
                    : 'background.paper',
                opacity: isRcloneAvailable ? 1 : 0.6,
                transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                transform:
                  data.repositoryLocation === 'rclone' && isRcloneAvailable
                    ? 'translateY(-2px)'
                    : 'none',
                '&:hover': {
                  transform: isRcloneAvailable ? 'translateY(-2px)' : 'none',
                  boxShadow: isRcloneAvailable
                    ? (theme) => `0 4px 12px ${alpha(theme.palette.text.primary, 0.08)}`
                    : 'none',
                  borderColor:
                    data.repositoryLocation === 'rclone' || !isRcloneAvailable
                      ? data.repositoryLocation === 'rclone'
                        ? 'primary.main'
                        : 'divider'
                      : 'text.primary',
                },
              }}
            >
              <CardActionArea
                onClick={() => handleLocationChange('rclone')}
                disabled={!isRcloneAvailable}
                aria-disabled={!isRcloneAvailable}
                sx={{ p: 1 }}
              >
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
                    <Box
                      sx={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        width: 48,
                        height: 48,
                        borderRadius: 3,
                        bgcolor:
                          data.repositoryLocation === 'rclone' ? 'primary.main' : 'action.hover',
                        color: data.repositoryLocation === 'rclone' ? 'white' : 'text.secondary',
                        transition: 'all 0.3s ease',
                        boxShadow:
                          data.repositoryLocation === 'rclone'
                            ? (theme) => `0 4px 12px ${alpha(theme.palette.primary.main, 0.4)}`
                            : 'none',
                      }}
                    >
                      <Cloud size={28} />
                    </Box>
                    <Box>
                      <Typography variant="h6" sx={{ fontSize: '1rem', fontWeight: 600 }}>
                        {t('wizard.location.rcloneStorage')}
                      </Typography>
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{ fontSize: '0.8125rem' }}
                      >
                        {t('wizard.location.rcloneStorageDesc')}
                      </Typography>
                    </Box>
                  </Box>
                </CardContent>
              </CardActionArea>
            </Card>
          </Box>

          {/* Warning when remote location is disabled due to remote data source */}
          {isRemoteLocationDisabled && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
              <strong>{t('wizard.dataSource.remoteToRemoteTitle')}</strong>{' '}
              {t('wizard.location.remoteDisabledInfo')}
            </Typography>
          )}
        </Box>
      )}

      {isAgentExecution && (
        <Typography variant="body2" color="text.secondary">
          {t('wizard.location.agentStorageNote')}
        </Typography>
      )}

      {/* SSH Connection Selection */}
      {data.repositoryLocation === 'ssh' && (
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
                sx={{
                  '& .MuiSelect-select': {
                    py: '16.5px',
                    display: 'flex',
                    alignItems: 'center',
                  },
                }}
              >
                {sshConnections.map((conn) => (
                  <MenuItem key={conn.id} value={String(conn.id)}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                      <Cloud size={16} />
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="body2">
                          {conn.username}@{conn.host}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          Port {conn.port}
                          {conn.mount_point && ` • ${conn.mount_point}`}
                        </Typography>
                      </Box>
                      {conn.status === 'connected' && (
                        <Box
                          sx={{
                            width: 8,
                            height: 8,
                            borderRadius: '50%',
                            bgcolor: 'success.main',
                          }}
                          title={t('wizard.location.connected')}
                        />
                      )}
                    </Box>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}
        </>
      )}

      {data.repositoryLocation === 'rclone' && (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {rcloneStatus && !rcloneStatus.available && (
            <Alert severity="warning">
              {rcloneStatus.error || t('wizard.location.rcloneUnavailable')}
            </Alert>
          )}
          <FormControl fullWidth disabled={!isRcloneAvailable}>
            <InputLabel id="rclone-remote-label">
              {t('wizard.location.rcloneRemoteLabel')}
            </InputLabel>
            <Select
              labelId="rclone-remote-label"
              id="rclone-remote"
              value={
                data.rcloneRemoteId === '' || data.rcloneRemoteId == null
                  ? ''
                  : String(data.rcloneRemoteId)
              }
              label={t('wizard.location.rcloneRemoteLabel')}
              onChange={(e) => {
                const value = e.target.value
                onChange({ rcloneRemoteId: value ? Number(value) : '' })
              }}
            >
              {rcloneRemotes.map((remote) => (
                <MenuItem key={remote.id} value={String(remote.id)}>
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
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {rcloneRemotes.length === 0 && (
            <Alert severity="info">{t('wizard.location.rcloneNoRemotes')}</Alert>
          )}

          <TextField
            label={t('wizard.location.rcloneRemotePathLabel')}
            value={data.rcloneRemotePath || ''}
            onChange={(e) => {
              onChange({ rcloneRemotePath: e.target.value })
            }}
            placeholder="borg-ui/repositories/app"
            required
            fullWidth
            disabled={!isRcloneAvailable}
            helperText={t('wizard.location.rcloneRemotePathHelper')}
          />

          <TextField
            label={t('wizard.location.rcloneCachePreviewLabel')}
            value="/data/rclone-cache/repositories/<repository-id>"
            fullWidth
            disabled={!isRcloneAvailable}
            InputProps={{ readOnly: true }}
            helperText={t('wizard.location.rcloneCachePreviewHelper')}
          />

          <FormControl fullWidth disabled={!isRcloneAvailable}>
            <InputLabel id="rclone-sync-policy-label">
              {t('wizard.location.rcloneSyncPolicyLabel')}
            </InputLabel>
            <Select
              labelId="rclone-sync-policy-label"
              id="rclone-sync-policy"
              value={data.rcloneSyncPolicy || 'after_success'}
              label={t('wizard.location.rcloneSyncPolicyLabel')}
              onChange={(e) =>
                onChange({
                  rcloneSyncPolicy: e.target.value as 'after_success' | 'manual' | 'scheduled',
                })
              }
            >
              <MenuItem value="after_success">
                {t('wizard.location.rcloneSyncAfterSuccess')}
              </MenuItem>
              <MenuItem value="manual">{t('wizard.location.rcloneSyncManual')}</MenuItem>
              <MenuItem value="scheduled">{t('wizard.location.rcloneSyncScheduled')}</MenuItem>
            </Select>
          </FormControl>

          <TextField
            label={t('wizard.location.rcloneExtraFlagsLabel')}
            value={data.rcloneExtraFlags || ''}
            onChange={(e) => onChange({ rcloneExtraFlags: e.target.value })}
            placeholder="--fast-list"
            fullWidth
            disabled={!isRcloneAvailable}
            helperText={t('wizard.location.rcloneExtraFlagsHelper')}
          />

          <Alert severity="info" icon={<Cloud size={18} />}>
            {t('wizard.location.rcloneRoutePreview')}
          </Alert>
        </Box>
      )}

      {/* Path Input */}
      {data.repositoryLocation !== 'rclone' && (
        <TextField
          label={t('wizard.location.repositoryPathLabel')}
          value={data.path}
          onChange={(e) => onChange({ path: e.target.value })}
          placeholder={
            data.repositoryLocation === 'local' ? '/backups/my-repo' : '/path/on/remote/server'
          }
          required
          fullWidth
          helperText={t('wizard.location.repositoryPathHelper')}
          InputProps={{
            endAdornment: (
              <InputAdornment position="end">
                <IconButton
                  onClick={onBrowsePath}
                  edge="end"
                  size="small"
                  title={t('wizard.location.browseFilesystem')}
                  disabled={
                    (isAgentExecution && !data.agentMachineId) ||
                    (data.repositoryLocation === 'ssh' && !data.repoSshConnectionId)
                  }
                >
                  <FolderOpenIcon fontSize="small" />
                </IconButton>
              </InputAdornment>
            ),
          }}
        />
      )}
    </Box>
  )
}

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
import type { SxProps, Theme } from '@mui/material/styles'
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
}

interface WizardStepLocationProps {
  mode: 'create' | 'edit' | 'import'
  data: LocationStepData
  sshConnections: SSHConnection[]
  agentMachines?: AgentMachine[]
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
  dataSource,
  sourceSshConnectionId,
  onChange,
  onBrowsePath,
}: WizardStepLocationProps) {
  const { t } = useTranslation()
  const executionTarget = data.executionTarget ?? 'local'
  const agentMachineId = data.agentMachineId ?? ''
  const isAgentExecution = executionTarget === 'agent'
  const isDirectRclone = data.repositoryLocation === 'rclone'
  const borgVersion = data.borgVersion ?? 1

  // Legacy v1 repos with an attached remote data source: prevent switching the repository
  // to another remote target. Remote-to-remote was never supported in the v1 mapping model.
  // New repositories carry no source/destination coupling — that lives in backup plans now —
  // so cards are freely interchangeable.
  const isLegacyRemoteSource = mode === 'edit' && dataSource === 'remote' && !!sourceSshConnectionId
  const isRemoteLocationDisabled = isLegacyRemoteSource
  const isAgentLocationDisabled = isLegacyRemoteSource

  const handleLocationChange = (location: 'local' | 'ssh') => {
    if (location === 'ssh' && isRemoteLocationDisabled) {
      return
    }
    onChange({
      repositoryLocation: location,
      executionTarget: 'local',
      agentMachineId: '',
      repoSshConnectionId: location === 'ssh' ? data.repoSshConnectionId : '',
    })
  }

  const handleAgentLocationChange = () => {
    if (isAgentLocationDisabled) {
      return
    }
    onChange({
      repositoryLocation: 'local',
      executionTarget: 'agent',
      repoSshConnectionId: '',
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

  const queueableAgents = agentMachines.filter(
    (agent) => agent.status !== 'revoked' && agent.status !== 'disabled'
  )
  const locationCardSx = (selected: boolean, disabled = false): SxProps<Theme> => ({
    flex: 1,
    minWidth: 0,
    border: '1px solid',
    borderColor: selected ? 'primary.main' : 'divider',
    boxShadow: selected
      ? (theme: Theme) =>
          `0 0 0 1px ${alpha(theme.palette.primary.main, 0.34)}, 0 2px 8px ${alpha(theme.palette.primary.main, 0.12)}`
      : 'none',
    bgcolor: selected
      ? (theme: Theme) => alpha(theme.palette.primary.main, 0.07)
      : 'background.paper',
    opacity: disabled ? 0.56 : 1,
    transition: 'border-color 180ms ease, box-shadow 180ms ease, background-color 180ms ease',
    '&:hover': disabled
      ? {}
      : {
          borderColor: selected ? 'primary.main' : 'text.secondary',
          boxShadow: (theme: Theme) =>
            selected
              ? `0 0 0 1px ${alpha(theme.palette.primary.main, 0.4)}, 0 3px 10px ${alpha(theme.palette.primary.main, 0.14)}`
              : `0 2px 8px ${alpha(theme.palette.text.primary, 0.08)}`,
        },
  })
  const locationActionSx: SxProps<Theme> = { p: 1.25, height: '100%', alignItems: 'stretch' }
  const locationContentSx: SxProps<Theme> = {
    p: 0,
    width: '100%',
    '&:last-child': { pb: 0 },
  }
  const locationIconSx = (selected: boolean): SxProps<Theme> => ({
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 36,
    height: 36,
    borderRadius: 1.5,
    flexShrink: 0,
    bgcolor: selected ? 'primary.main' : 'action.hover',
    color: selected ? 'white' : 'text.secondary',
    transition: 'background-color 180ms ease, color 180ms ease, box-shadow 180ms ease',
    boxShadow: selected
      ? (theme: Theme) => `0 2px 8px ${alpha(theme.palette.primary.main, 0.26)}`
      : 'none',
  })
  const locationTitleSx: SxProps<Theme> = { fontSize: '0.95rem', lineHeight: 1.25, fontWeight: 700 }
  const locationDescSx: SxProps<Theme> = {
    fontSize: '0.76rem',
    lineHeight: 1.35,
    display: '-webkit-box',
    WebkitLineClamp: 2,
    WebkitBoxOrient: 'vertical',
    overflow: 'hidden',
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

      {/* Location Selection Cards */}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <Typography variant="subtitle2" gutterBottom sx={{ mb: 2, fontWeight: 600 }}>
          {t('wizard.location.whereToStore')}
        </Typography>
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' },
            gap: 2,
            p: 0.5,
            m: -0.5,
          }}
        >
          <Card
            variant="outlined"
            sx={locationCardSx(data.repositoryLocation === 'local' && !isAgentExecution)}
          >
            <CardActionArea onClick={() => handleLocationChange('local')} sx={locationActionSx}>
              <CardContent sx={locationContentSx}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
                  <Box
                    sx={locationIconSx(data.repositoryLocation === 'local' && !isAgentExecution)}
                  >
                    <Server size={20} />
                  </Box>
                  <Box sx={{ minWidth: 0 }}>
                    <Typography variant="subtitle2" sx={locationTitleSx}>
                      {t('wizard.borgUiServer')}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={locationDescSx}>
                      {t('wizard.location.borgUiServerDesc')}
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </CardActionArea>
          </Card>

          <Card
            variant="outlined"
            sx={locationCardSx(
              data.repositoryLocation === 'ssh' && !isAgentExecution,
              isRemoteLocationDisabled
            )}
          >
            <CardActionArea
              onClick={() => handleLocationChange('ssh')}
              disabled={isRemoteLocationDisabled}
              sx={locationActionSx}
            >
              <CardContent sx={locationContentSx}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
                  <Box sx={locationIconSx(data.repositoryLocation === 'ssh' && !isAgentExecution)}>
                    <Cloud size={20} />
                  </Box>
                  <Box sx={{ minWidth: 0 }}>
                    <Typography variant="subtitle2" sx={locationTitleSx}>
                      {t('wizard.remoteClient')}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={locationDescSx}>
                      {t('wizard.location.remoteClientDesc')}
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </CardActionArea>
          </Card>

          <Card variant="outlined" sx={locationCardSx(isAgentExecution, isAgentLocationDisabled)}>
            <CardActionArea
              onClick={handleAgentLocationChange}
              disabled={isAgentLocationDisabled}
              sx={locationActionSx}
            >
              <CardContent sx={locationContentSx}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
                  <Box sx={locationIconSx(isAgentExecution)}>
                    <Laptop size={20} />
                  </Box>
                  <Box sx={{ minWidth: 0 }}>
                    <Typography variant="subtitle2" sx={locationTitleSx}>
                      {t('wizard.location.managedAgent')}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={locationDescSx}>
                      {t('wizard.location.managedAgentDesc')}
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </CardActionArea>
          </Card>
        </Box>

        {isRemoteLocationDisabled && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
            <strong>{t('wizard.dataSource.remoteToRemoteTitle')}</strong>{' '}
            {t('wizard.location.remoteDisabledInfo')}
          </Typography>
        )}
      </Box>

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
              disabled={borgVersion !== 2}
              onChange={(event) => handleDirectRcloneChange(event.target.checked)}
            />
          }
          label={
            <Box>
              <Typography variant="body2" fontWeight={600}>
                {t('wizard.location.directRcloneLabel')}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {t(
                  borgVersion === 2
                    ? 'wizard.location.directRcloneHelper'
                    : 'wizard.location.directRcloneUnavailable'
                )}
              </Typography>
            </Box>
          }
        />
      </Box>

      {isAgentExecution && (
        <>
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
          )}
          <Typography variant="body2" color="text.secondary">
            {t('wizard.location.agentStorageNote')}
          </Typography>
        </>
      )}

      {/* SSH Connection Selection */}
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

      {/* Path Input */}
      <TextField
        label={
          isDirectRclone
            ? t('wizard.location.directRclonePathLabel')
            : t('wizard.location.repositoryPathLabel')
        }
        value={data.path}
        onChange={(e) => onChange({ path: e.target.value })}
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
                onClick={onBrowsePath}
                edge="end"
                size="small"
                title={t('wizard.location.browseFilesystem')}
                disabled={
                  isDirectRclone ||
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
    </Box>
  )
}

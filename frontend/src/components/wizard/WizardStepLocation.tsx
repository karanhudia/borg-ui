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
  InputAdornment,
  IconButton,
  alpha,
  ButtonBase,
  Tooltip,
  Chip,
  Stack,
} from '@mui/material'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'
import { useTranslation } from 'react-i18next'
import PlanGate from '../PlanGate'
import { getDestinations, type DestinationKey } from './destinations'
import SshConnectionSelect from '../shared/SshConnectionSelect'
import ManagedAgentSelect from '../shared/ManagedAgentSelect'
import DestinationSelect from '../shared/DestinationSelect'

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
  dataSource?: 'local' | 'remote'
  sourceSshConnectionId?: number | ''
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

  // Legacy v1 repos with an attached remote data source can't be retargeted to another
  // remote — remote-to-remote was never supported in the v1 mapping model.
  const isLegacyRemoteSource = mode === 'edit' && dataSource === 'remote' && !!sourceSshConnectionId
  const isRemoteLocationDisabled = isLegacyRemoteSource
  const isAgentLocationDisabled = isLegacyRemoteSource

  const queueableAgents = agentMachines.filter(
    (agent) => agent.status !== 'revoked' && agent.status !== 'disabled'
  )

  const destinations = getDestinations({ t, isRemoteLocationDisabled, isAgentLocationDisabled })

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
        <DestinationSelect
          value={selectedDestinationKey}
          onChange={(key) => handleDestinationChange(key as DestinationKey)}
          destinations={destinations}
          label={t('wizard.location.whereToStore')}
          labelId="destination-select-label"
        />
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
          <ManagedAgentSelect
            value={agentMachineId}
            onChange={(id) => onChange({ agentMachineId: id })}
            agents={queueableAgents}
            label={t('wizard.location.managedAgentSelectLabel')}
            emptyMessage={t('wizard.location.noActiveManagedAgents')}
            labelId="managed-agent-select-label"
          />
          <Typography variant="body2" color="text.secondary">
            {t('wizard.location.agentStorageNote')}
          </Typography>
        </Stack>
      )}

      {/* SSH sub-form */}
      {!isAgentExecution && data.repositoryLocation === 'ssh' && (
        <SshConnectionSelect
          value={data.repoSshConnectionId}
          onChange={(id) => onChange({ repoSshConnectionId: id })}
          connections={sshConnections}
          label={t('wizard.location.selectSshConnection')}
          emptyMessage={t('wizard.noSshConnections')}
          connectedTooltip={t('wizard.location.connected')}
        />
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

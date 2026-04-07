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
} from '@mui/material'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import { Server, Cloud } from 'lucide-react'
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

export interface LocationStepData {
  name: string
  borgVersion?: 1 | 2
  repositoryMode: 'full' | 'observe'
  repositoryLocation: 'local' | 'ssh'
  path: string
  repoSshConnectionId: number | ''
  bypassLock: boolean
}

interface WizardStepLocationProps {
  mode: 'create' | 'edit' | 'import'
  data: LocationStepData
  sshConnections: SSHConnection[]
  dataSource?: 'local' | 'remote' // Data source from step 2
  sourceSshConnectionId?: number | '' // Source SSH connection ID
  onChange: (data: Partial<LocationStepData>) => void
  onBrowsePath: () => void
}

export default function WizardStepLocation({
  mode,
  data,
  sshConnections,
  dataSource,
  sourceSshConnectionId,
  onChange,
  onBrowsePath,
}: WizardStepLocationProps) {
  const { t } = useTranslation()

  // Disable SSH repository location if data source is remote (prevent remote-to-remote)
  // Only enforce this in edit mode when we know the data source
  const isRemoteLocationDisabled =
    mode === 'edit' && dataSource === 'remote' && !!sourceSshConnectionId

  const handleLocationChange = (location: 'local' | 'ssh') => {
    if (location === 'ssh' && isRemoteLocationDisabled) {
      return // Don't allow switching to SSH if data source is remote
    }
    onChange({
      repositoryLocation: location,
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
                  <InfoOutlinedIcon sx={{ fontSize: 16, color: 'info.main', cursor: 'default' }} />
                </Tooltip>
              )}
            </Box>
            {(data.borgVersion ?? 1) === 2 && (
              <Alert severity="warning" sx={{ py: 0.5 }}>
                {t('wizard.location.borgV2Warning')}
              </Alert>
            )}
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
        <Alert severity="info">{t('wizard.location.observabilityInfo')}</Alert>
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
      <Box>
        <Typography variant="subtitle2" gutterBottom sx={{ mb: 2, fontWeight: 600 }}>
          {t('wizard.location.whereToStore')}
        </Typography>
        <Box sx={{ display: 'flex', gap: 2, flexDirection: { xs: 'column', sm: 'row' } }}>
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
                borderColor: data.repositoryLocation === 'local' ? 'primary.main' : 'text.primary',
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
                      bgcolor: data.repositoryLocation === 'ssh' ? 'primary.main' : 'action.hover',
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
        </Box>

        {/* Warning when remote location is disabled due to remote data source */}
        {isRemoteLocationDisabled && (
          <Alert severity="info" sx={{ mt: 2 }}>
            <Typography variant="body2">
              <strong>{t('wizard.dataSource.remoteToRemoteTitle')}</strong>{' '}
              {t('wizard.location.remoteDisabledInfo')}
            </Typography>
          </Alert>
        )}
      </Box>

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

      {/* Path Input */}
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
                disabled={data.repositoryLocation === 'ssh' && !data.repoSshConnectionId}
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

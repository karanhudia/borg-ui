import {
  Box,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Typography,
  Alert,
  Card,
  CardContent,
  CardActionArea,
  alpha,
  Tooltip,
} from '@mui/material'
import { HardDrive, Laptop, Ban } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import SourceDirectoriesInput from '../SourceDirectoriesInput'

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

export interface DataSourceStepData {
  dataSource: 'local' | 'remote'
  sourceSshConnectionId: number | ''
  sourceDirs: string[]
}

interface WizardStepDataSourceProps {
  repositoryLocation: 'local' | 'ssh'
  repoSshConnectionId: number | ''
  repositoryMode: 'full' | 'observe'
  data: DataSourceStepData
  sshConnections: SSHConnection[]
  onChange: (data: Partial<DataSourceStepData>) => void
  onBrowseSource: () => void
  onBrowseRemoteSource: () => void
}

export default function WizardStepDataSource({
  repositoryLocation,
  repoSshConnectionId,
  repositoryMode,
  data,
  sshConnections,
  onChange,
  onBrowseSource,
  onBrowseRemoteSource,
}: WizardStepDataSourceProps) {
  const { t } = useTranslation()

  // Remote-to-remote is not allowed
  const isRemoteToRemoteDisabled = repositoryLocation === 'ssh'

  // Determine if cards should be disabled based on already selected directories
  const hasLocalDirs = data.sourceDirs.length > 0 && !data.sourceSshConnectionId
  const hasRemoteDirs = !!data.sourceSshConnectionId && data.sourceDirs.length > 0

  const handleDataSourceChange = (source: 'local' | 'remote') => {
    if (source === 'remote' && isRemoteToRemoteDisabled) {
      return
    }

    const updates: Partial<DataSourceStepData> = { dataSource: source }

    // If switching to remote and repo is on a remote client, auto-select the same client
    if (source === 'remote' && repositoryLocation === 'ssh' && repoSshConnectionId) {
      updates.sourceSshConnectionId = repoSshConnectionId
    } else if (source === 'local') {
      updates.sourceSshConnectionId = ''
    }

    onChange(updates)
  }

  const handleSourceConnectionSelect = (connectionId: number) => {
    onChange({ sourceSshConnectionId: connectionId })
  }

  // Filter available SSH connections based on repository location
  const availableConnections = sshConnections.filter((conn) => {
    // If repository is on a remote client, only show that same client
    if (repositoryLocation === 'ssh' && repoSshConnectionId) {
      return conn.id === repoSshConnectionId
    }
    return true
  })

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <Typography variant="subtitle2" gutterBottom>
        {t('wizard.dataSource.title')}
      </Typography>

      <Box
        sx={{
          display: 'flex',
          gap: 2,
          alignItems: 'stretch',
          flexDirection: { xs: 'column', sm: 'row' },
        }}
      >
        {/* Local Data Source Card */}
        <Card
          variant="outlined"
          sx={{
            flex: 1,
            border: data.dataSource === 'local' ? 2 : 1,
            borderColor: data.dataSource === 'local' ? 'primary.main' : 'divider',
            boxShadow:
              data.dataSource === 'local'
                ? (theme) => `0 4px 12px ${alpha(theme.palette.primary.main, 0.2)}`
                : 'none',
            bgcolor:
              data.dataSource === 'local'
                ? (theme) => alpha(theme.palette.primary.main, 0.08)
                : 'background.paper',
            opacity: hasRemoteDirs ? 0.5 : 1,
            display: 'flex',
            transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
            transform: data.dataSource === 'local' ? 'translateY(-2px)' : 'none',
            '&:hover': !hasRemoteDirs
              ? {
                  transform: 'translateY(-2px)',
                  boxShadow: (theme) => `0 4px 12px ${alpha(theme.palette.text.primary, 0.08)}`,
                  borderColor: data.dataSource === 'local' ? 'primary.main' : 'text.primary',
                }
              : {},
          }}
        >
          <CardActionArea
            onClick={() => handleDataSourceChange('local')}
            disabled={hasRemoteDirs}
            sx={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'stretch',
              height: '100%',
              p: 1,
            }}
          >
            <CardContent sx={{ flex: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 48,
                    height: 48,
                    borderRadius: 3,
                    bgcolor: data.dataSource === 'local' ? 'primary.main' : 'action.hover',
                    color: data.dataSource === 'local' ? 'white' : 'text.secondary',
                    transition: 'all 0.3s ease',
                    boxShadow:
                      data.dataSource === 'local'
                        ? (theme) => `0 4px 12px ${alpha(theme.palette.primary.main, 0.4)}`
                        : 'none',
                  }}
                >
                  <HardDrive size={28} />
                </Box>
                <Box>
                  <Typography variant="h6" sx={{ fontSize: '1rem', fontWeight: 600 }}>
                    {t('wizard.borgUiServer')}
                  </Typography>
                </Box>
              </Box>
              <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.8125rem' }}>
                {t('wizard.dataSource.localDescription')}
              </Typography>
              {hasRemoteDirs && (
                <Typography variant="caption" color="warning.main" sx={{ mt: 1, display: 'block' }}>
                  {t('wizard.dataSource.removeRemoteDirsFirst')}
                </Typography>
              )}
            </CardContent>
          </CardActionArea>
        </Card>

        {/* Remote Data Source Card */}
        <Tooltip
          title={
            isRemoteToRemoteDisabled ? t('wizard.dataSource.remoteToRemoteDisabledTooltip') : ''
          }
          arrow
          placement="top"
        >
          <Card
            variant="outlined"
            sx={{
              flex: 1,
              border: data.dataSource === 'remote' ? 2 : 1,
              borderColor: data.dataSource === 'remote' ? 'primary.main' : 'divider',
              boxShadow:
                data.dataSource === 'remote'
                  ? (theme) => `0 4px 12px ${alpha(theme.palette.primary.main, 0.2)}`
                  : 'none',
              bgcolor:
                data.dataSource === 'remote'
                  ? (theme) => alpha(theme.palette.primary.main, 0.08)
                  : 'background.paper',
              opacity: hasLocalDirs || isRemoteToRemoteDisabled ? 0.5 : 1,
              display: 'flex',
              transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
              transform: data.dataSource === 'remote' ? 'translateY(-2px)' : 'none',
              position: 'relative',
              '&:hover':
                !hasLocalDirs && !isRemoteToRemoteDisabled
                  ? {
                      transform: 'translateY(-2px)',
                      boxShadow: (theme) => `0 4px 12px ${alpha(theme.palette.text.primary, 0.08)}`,
                      borderColor: data.dataSource === 'remote' ? 'primary.main' : 'text.primary',
                    }
                  : {},
            }}
          >
            <CardActionArea
              onClick={() => handleDataSourceChange('remote')}
              disabled={hasLocalDirs || isRemoteToRemoteDisabled}
              sx={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'stretch',
                height: '100%',
                p: 1,
              }}
            >
              <CardContent sx={{ flex: 1 }}>
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
                        data.dataSource === 'remote' && !isRemoteToRemoteDisabled
                          ? 'primary.main'
                          : 'action.hover',
                      color:
                        data.dataSource === 'remote' && !isRemoteToRemoteDisabled
                          ? 'white'
                          : 'text.secondary',
                      transition: 'all 0.3s ease',
                      boxShadow:
                        data.dataSource === 'remote' && !isRemoteToRemoteDisabled
                          ? (theme) => `0 4px 12px ${alpha(theme.palette.primary.main, 0.4)}`
                          : 'none',
                    }}
                  >
                    {isRemoteToRemoteDisabled ? <Ban size={28} /> : <Laptop size={28} />}
                  </Box>
                  <Box>
                    <Typography variant="h6" sx={{ fontSize: '1rem', fontWeight: 600 }}>
                      {t('wizard.remoteClient')}
                    </Typography>
                  </Box>
                </Box>
                <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.8125rem' }}>
                  {isRemoteToRemoteDisabled
                    ? t('wizard.dataSource.notAvailableRemoteRepo')
                    : t('wizard.dataSource.remoteDescription')}
                </Typography>
                {hasLocalDirs && !isRemoteToRemoteDisabled && (
                  <Typography
                    variant="caption"
                    color="warning.main"
                    sx={{ mt: 1, display: 'block' }}
                  >
                    {t('wizard.dataSource.removeLocalDirsFirst')}
                  </Typography>
                )}
              </CardContent>
            </CardActionArea>
          </Card>
        </Tooltip>
      </Box>

      {/* Remote-to-remote explanation */}
      {isRemoteToRemoteDisabled && (
        <Alert severity="info">
          <Typography variant="body2">
            <strong>{t('wizard.dataSource.remoteToRemoteTitle')}</strong>{' '}
            {t('wizard.dataSource.remoteToRemoteBody')}
          </Typography>
        </Alert>
      )}

      {/* Local Data Source Configuration */}
      {data.dataSource === 'local' && (
        <SourceDirectoriesInput
          directories={data.sourceDirs}
          onChange={(newDirs) => {
            onChange({
              sourceDirs: newDirs,
              sourceSshConnectionId: newDirs.length === 0 ? '' : data.sourceSshConnectionId,
            })
          }}
          onBrowseClick={onBrowseSource}
          required={repositoryMode !== 'observe'}
        />
      )}

      {/* Remote Data Source Configuration */}
      {data.dataSource === 'remote' && !isRemoteToRemoteDisabled && (
        <>
          {!Array.isArray(sshConnections) || sshConnections.length === 0 ? (
            <Alert severity="warning">{t('wizard.noSshConnections')}</Alert>
          ) : (
            <>
              <FormControl fullWidth>
                <InputLabel>{t('wizard.dataSource.selectRemoteClient')}</InputLabel>
                <Select
                  value={
                    data.sourceSshConnectionId === '' ? '' : String(data.sourceSshConnectionId)
                  }
                  label={t('wizard.dataSource.selectRemoteClient')}
                  onChange={(e) => {
                    const value = e.target.value
                    if (value) {
                      handleSourceConnectionSelect(Number(value))
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
                  {availableConnections.map((conn) => (
                    <MenuItem key={conn.id} value={String(conn.id)}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                        <Laptop size={16} />
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
                            title="Connected"
                          />
                        )}
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              {data.sourceSshConnectionId && (
                <Box>
                  <SourceDirectoriesInput
                    directories={data.sourceDirs}
                    onChange={(newDirs) => {
                      onChange({
                        sourceDirs: newDirs,
                        sourceSshConnectionId:
                          newDirs.length === 0 ? '' : data.sourceSshConnectionId,
                      })
                    }}
                    onBrowseClick={onBrowseRemoteSource}
                    required={repositoryMode !== 'observe'}
                  />
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ mt: 0.5, display: 'block' }}
                  >
                    {t('wizard.dataSource.browseRemoteNote')}
                  </Typography>
                </Box>
              )}
            </>
          )}

          <Alert severity="info">
            <Typography variant="body2">
              <strong>Note:</strong> {t('wizard.dataSource.remoteSshNote')}
            </Typography>
          </Alert>
        </>
      )}
    </Box>
  )
}

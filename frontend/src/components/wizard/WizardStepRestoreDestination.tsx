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
  TextField,
  FormControlLabel,
  Radio,
  RadioGroup,
  Paper,
  InputAdornment,
  IconButton,
} from '@mui/material'
import { Server, Cloud, FileCheck, FolderOpen } from 'lucide-react'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'
import { useTranslation } from 'react-i18next'
import {
  DEFAULT_RESTORE_LAYOUT,
  getRestorePreviewDestination,
  type RestoreLayout,
  type RestorePathMetadata,
} from '../../utils/restorePaths'

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

export interface RestoreDestinationStepData {
  destinationType: 'local' | 'ssh'
  destinationConnectionId: number | ''
  restoreStrategy: 'original' | 'custom'
  customPath: string
  restoreLayout: RestoreLayout
}

interface WizardStepRestoreDestinationProps {
  data: RestoreDestinationStepData
  selectedItems: RestorePathMetadata[]
  sshConnections: SSHConnection[]
  repositoryType: string
  onChange: (data: Partial<RestoreDestinationStepData>) => void
  onBrowsePath: () => void
}

export default function WizardStepRestoreDestination({
  data,
  selectedItems,
  sshConnections,
  repositoryType,
  onChange,
  onBrowsePath,
}: WizardStepRestoreDestinationProps) {
  const { t } = useTranslation()
  const isSSHRepository = repositoryType === 'ssh'

  const handleLocationChange = (location: 'local' | 'ssh') => {
    // Prevent SSH-to-SSH restore
    if (isSSHRepository && location === 'ssh') {
      return
    }

    onChange({
      destinationType: location,
      destinationConnectionId: '',
    })
  }

  // Get selected SSH connection for preview
  const selectedSshConnection =
    data.destinationType === 'ssh' && data.destinationConnectionId
      ? sshConnections.find((c) => c.id === data.destinationConnectionId)
      : null

  // Build SSH URL preview
  const getSshUrlPreview = () => {
    if (!selectedSshConnection || !data.customPath) return ''
    const path = data.customPath.startsWith('/') ? data.customPath : `/${data.customPath}`
    return `ssh://${selectedSshConnection.username}@${selectedSshConnection.host}:${selectedSshConnection.port}${path}`
  }

  const sshPrefix = selectedSshConnection
    ? `ssh://${selectedSshConnection.username}@${selectedSshConnection.host}:${selectedSshConnection.port}`
    : ''

  const restoreLayout = data.restoreLayout || DEFAULT_RESTORE_LAYOUT
  const previewItems = selectedItems.slice(0, 3)
  const hiddenPreviewCount = Math.max(selectedItems.length - previewItems.length, 0)

  const getPreviewDestination = (item: RestorePathMetadata) =>
    getRestorePreviewDestination(item.path, {
      restoreStrategy: data.restoreStrategy,
      customPath: data.customPath,
      restoreLayout,
      selectedItems,
      sshPrefix,
    })

  const isContentsOnlyDirectoryPreview = (item: RestorePathMetadata) =>
    data.restoreStrategy === 'custom' &&
    restoreLayout === 'contents_only' &&
    selectedItems.length === 1 &&
    item.type === 'directory'

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {/* Header */}
      <Box>
        <Typography variant="h6" gutterBottom sx={{ fontWeight: 600 }}>
          {t('wizard.restoreDestination.title')}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t('wizard.restoreDestination.subtitle')}
        </Typography>
      </Box>

      {/* Destination Selection Cards */}
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
        <Card
          variant="outlined"
          sx={{
            flex: '1 1 200px',
            border: data.destinationType === 'local' ? 2 : 1,
            borderColor: data.destinationType === 'local' ? '#1976d2' : 'divider',
            boxShadow:
              data.destinationType === 'local' ? `0 4px 12px ${alpha('#1976d2', 0.2)}` : 'none',
            bgcolor:
              data.destinationType === 'local'
                ? (theme) => alpha('#1976d2', theme.palette.mode === 'dark' ? 0.12 : 0.08)
                : 'background.paper',
            transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
            transform: data.destinationType === 'local' ? 'translateY(-2px)' : 'none',
            '&:hover': {
              transform: 'translateY(-2px)',
              boxShadow: (theme) => `0 4px 12px ${alpha(theme.palette.text.primary, 0.08)}`,
              borderColor: data.destinationType === 'local' ? '#1976d2' : 'text.primary',
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
                    bgcolor: data.destinationType === 'local' ? '#1976d2' : 'action.hover',
                    color: data.destinationType === 'local' ? 'white' : 'text.secondary',
                    transition: 'all 0.3s ease',
                    boxShadow:
                      data.destinationType === 'local'
                        ? `0 4px 12px ${alpha('#1976d2', 0.4)}`
                        : 'none',
                  }}
                >
                  <Server size={28} />
                </Box>
                <Box>
                  <Typography variant="h6" sx={{ fontSize: '1rem', fontWeight: 600 }}>
                    {t('wizard.borgUiServer')}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.8125rem' }}>
                    {t('wizard.restoreDestination.borgUiServerDesc')}
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </CardActionArea>
        </Card>

        {!isSSHRepository && (
          <Card
            variant="outlined"
            sx={{
              flex: '1 1 200px',
              border: data.destinationType === 'ssh' ? 2 : 1,
              borderColor: data.destinationType === 'ssh' ? '#1976d2' : 'divider',
              boxShadow:
                data.destinationType === 'ssh' ? `0 4px 12px ${alpha('#1976d2', 0.2)}` : 'none',
              bgcolor:
                data.destinationType === 'ssh'
                  ? (theme) => alpha('#1976d2', theme.palette.mode === 'dark' ? 0.12 : 0.08)
                  : 'background.paper',
              transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
              transform: data.destinationType === 'ssh' ? 'translateY(-2px)' : 'none',
              '&:hover': {
                transform: 'translateY(-2px)',
                boxShadow: (theme) => `0 4px 12px ${alpha(theme.palette.text.primary, 0.08)}`,
                borderColor: data.destinationType === 'ssh' ? '#1976d2' : 'text.primary',
              },
            }}
          >
            <CardActionArea onClick={() => handleLocationChange('ssh')} sx={{ p: 1 }}>
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
                      bgcolor: data.destinationType === 'ssh' ? '#1976d2' : 'action.hover',
                      color: data.destinationType === 'ssh' ? 'white' : 'text.secondary',
                      transition: 'all 0.3s ease',
                      boxShadow:
                        data.destinationType === 'ssh'
                          ? `0 4px 12px ${alpha('#1976d2', 0.4)}`
                          : 'none',
                    }}
                  >
                    <Cloud size={28} />
                  </Box>
                  <Box>
                    <Typography variant="h6" sx={{ fontSize: '1rem', fontWeight: 600 }}>
                      {t('wizard.restoreDestination.remoteMachine')}
                    </Typography>
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{ fontSize: '0.8125rem' }}
                    >
                      {t('wizard.restoreDestination.remoteMachineDesc')}
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </CardActionArea>
          </Card>
        )}
      </Box>

      {/* SSH Repository Info Alert */}
      {isSSHRepository && (
        <Alert severity="info">{t('wizard.restoreDestination.sshToSshNotSupported')}</Alert>
      )}

      {/* SSH Connection Selection (shown first so strategy options appear below) */}
      {data.destinationType === 'ssh' && (
        <>
          {!Array.isArray(sshConnections) || sshConnections.length === 0 ? (
            <Alert severity="warning">{t('wizard.noSshConnections')}</Alert>
          ) : (
            <FormControl fullWidth>
              <InputLabel>{t('wizard.restoreDestination.selectSshConnection')}</InputLabel>
              <Select
                value={
                  data.destinationConnectionId === '' ? '' : String(data.destinationConnectionId)
                }
                label={t('wizard.restoreDestination.selectSshConnection')}
                onChange={(e) => {
                  const value = e.target.value
                  if (value) {
                    onChange({ destinationConnectionId: Number(value) })
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
                          title="Connected"
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

      {/* Original vs Custom Location (shown for local, or SSH once a connection is selected) */}
      {(data.destinationType === 'local' ||
        (data.destinationType === 'ssh' && data.destinationConnectionId)) && (
        <FormControl>
          <RadioGroup
            value={data.restoreStrategy}
            onChange={(e) => onChange({ restoreStrategy: e.target.value as 'original' | 'custom' })}
          >
            <Paper
              variant="outlined"
              sx={{
                p: 2,
                mb: 2,
                border: data.restoreStrategy === 'original' ? 2 : 1,
                borderColor: data.restoreStrategy === 'original' ? '#1976d2' : 'divider',
                bgcolor:
                  data.restoreStrategy === 'original'
                    ? (theme) => alpha('#1976d2', theme.palette.mode === 'dark' ? 0.12 : 0.08)
                    : 'background.paper',
                transition: 'all 0.2s',
                cursor: 'pointer',
                '&:hover': {
                  borderColor: data.restoreStrategy === 'original' ? '#1976d2' : 'text.primary',
                },
              }}
              onClick={() => onChange({ restoreStrategy: 'original' })}
            >
              <FormControlLabel
                value="original"
                control={<Radio />}
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <FileCheck size={18} />
                    <Box>
                      <Typography variant="body1" fontWeight={600}>
                        {t('wizard.restoreDestination.restoreToOriginal')}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {data.destinationType === 'ssh'
                          ? t('wizard.restoreDestination.restoreToOriginalDescRemote')
                          : t('wizard.restoreDestination.restoreToOriginalDescLocal')}
                      </Typography>
                    </Box>
                  </Box>
                }
                sx={{ m: 0, width: '100%' }}
              />
            </Paper>

            <Paper
              variant="outlined"
              sx={{
                p: 2,
                border: data.restoreStrategy === 'custom' ? 2 : 1,
                borderColor: data.restoreStrategy === 'custom' ? '#1976d2' : 'divider',
                bgcolor:
                  data.restoreStrategy === 'custom'
                    ? (theme) => alpha('#1976d2', theme.palette.mode === 'dark' ? 0.12 : 0.08)
                    : 'background.paper',
                transition: 'all 0.2s',
                cursor: 'pointer',
                '&:hover': {
                  borderColor: data.restoreStrategy === 'custom' ? '#1976d2' : 'text.primary',
                },
              }}
              onClick={() => onChange({ restoreStrategy: 'custom' })}
            >
              <FormControlLabel
                value="custom"
                control={<Radio />}
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <FolderOpen size={18} />
                    <Box>
                      <Typography variant="body1" fontWeight={600}>
                        {t('wizard.restoreDestination.restoreToCustom')}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {t('wizard.restoreDestination.restoreToCustomDesc')}
                      </Typography>
                    </Box>
                  </Box>
                }
                sx={{ m: 0, width: '100%' }}
              />
            </Paper>
          </RadioGroup>
        </FormControl>
      )}

      {/* Custom Path Input (shown for any destination type when custom strategy is selected) */}
      {data.restoreStrategy === 'custom' && (
        <>
          <TextField
            label={t('wizard.restoreDestination.customPathLabel')}
            value={data.customPath}
            onChange={(e) => onChange({ customPath: e.target.value })}
            placeholder={
              data.destinationType === 'ssh'
                ? '/mnt/backup/restored'
                : '/Users/yourusername/restored'
            }
            required
            fullWidth
            helperText={
              data.destinationType === 'ssh'
                ? t('wizard.restoreDestination.customPathHelperRemote')
                : t('wizard.restoreDestination.customPathHelperLocal')
            }
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    onClick={onBrowsePath}
                    edge="end"
                    size="small"
                    title={
                      data.destinationType === 'ssh'
                        ? t('wizard.restoreDestination.browseRemoteFilesystem')
                        : t('wizard.restoreDestination.browseFilesystem')
                    }
                  >
                    <FolderOpenIcon fontSize="small" />
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />

          <FormControl component="fieldset">
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
              {t('wizard.restoreDestination.pathLayout')}
            </Typography>
            <RadioGroup
              value={restoreLayout}
              onChange={(e) => onChange({ restoreLayout: e.target.value as RestoreLayout })}
            >
              <Paper
                variant="outlined"
                sx={{
                  p: 1.5,
                  mb: 1,
                  borderColor: restoreLayout === 'preserve_path' ? '#1976d2' : 'divider',
                  bgcolor:
                    restoreLayout === 'preserve_path'
                      ? (theme) => alpha('#1976d2', theme.palette.mode === 'dark' ? 0.12 : 0.06)
                      : 'background.paper',
                  cursor: 'pointer',
                  transition: 'border-color 0.2s, background-color 0.2s',
                  '&:hover': { borderColor: '#1976d2' },
                }}
                onClick={() => onChange({ restoreLayout: 'preserve_path' })}
              >
                <FormControlLabel
                  value="preserve_path"
                  control={<Radio size="small" />}
                  label={
                    <Box>
                      <Typography variant="body2" fontWeight={600}>
                        {t('wizard.restoreDestination.preserveArchivePath')}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {t('wizard.restoreDestination.preserveArchivePathDesc')}
                      </Typography>
                    </Box>
                  }
                  sx={{ m: 0, width: '100%' }}
                />
              </Paper>

              <Paper
                variant="outlined"
                sx={{
                  p: 1.5,
                  borderColor: restoreLayout === 'contents_only' ? '#1976d2' : 'divider',
                  bgcolor:
                    restoreLayout === 'contents_only'
                      ? (theme) => alpha('#1976d2', theme.palette.mode === 'dark' ? 0.12 : 0.06)
                      : 'background.paper',
                  cursor: 'pointer',
                  transition: 'border-color 0.2s, background-color 0.2s',
                  '&:hover': { borderColor: '#1976d2' },
                }}
                onClick={() => onChange({ restoreLayout: 'contents_only' })}
              >
                <FormControlLabel
                  value="contents_only"
                  control={<Radio size="small" />}
                  label={
                    <Box>
                      <Typography variant="body2" fontWeight={600}>
                        {t('wizard.restoreDestination.restoreContentsHere')}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {t('wizard.restoreDestination.restoreContentsHereDesc')}
                      </Typography>
                    </Box>
                  }
                  sx={{ m: 0, width: '100%' }}
                />
              </Paper>
            </RadioGroup>
          </FormControl>

          {data.customPath && previewItems.length > 0 && (
            <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'background.default' }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                {t('wizard.restoreDestination.restorePathPreview')}
              </Typography>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
                {previewItems.map((item) => (
                  <Box
                    key={item.path}
                    sx={{
                      display: 'grid',
                      gridTemplateColumns: { xs: '1fr', sm: '88px 1fr' },
                      columnGap: 1,
                      rowGap: 0.25,
                    }}
                  >
                    <Typography variant="caption" color="text.secondary">
                      {t('wizard.restoreDestination.archivePath')}
                    </Typography>
                    <Typography
                      variant="caption"
                      sx={{ fontFamily: 'monospace', overflowWrap: 'anywhere' }}
                    >
                      {item.path}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {t('wizard.restoreDestination.restorePath')}
                    </Typography>
                    <Typography
                      variant="caption"
                      sx={{
                        fontFamily: 'monospace',
                        fontWeight: 600,
                        color: '#1976d2',
                        overflowWrap: 'anywhere',
                      }}
                    >
                      {getPreviewDestination(item)}
                      {isContentsOnlyDirectoryPreview(item) && (
                        <Box component="span" sx={{ color: 'text.secondary', ml: 0.5 }}>
                          {t('wizard.restoreDestination.contentsOnlyMarker')}
                        </Box>
                      )}
                    </Typography>
                  </Box>
                ))}
                {hiddenPreviewCount > 0 && (
                  <Typography variant="caption" color="text.secondary">
                    {t('wizard.restoreDestination.andMoreItems', { count: hiddenPreviewCount })}
                  </Typography>
                )}
              </Box>
            </Paper>
          )}

          {data.customPath && data.destinationType === 'ssh' && selectedSshConnection && (
            <Alert severity="info" icon={<Cloud size={18} />} sx={{ mt: -1, py: 0.5 }}>
              <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                {getSshUrlPreview()}
              </Typography>
            </Alert>
          )}
        </>
      )}
    </Box>
  )
}

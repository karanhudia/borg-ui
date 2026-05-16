import {
  Alert,
  Box,
  Button,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material'
import { HardDrive, Laptop, Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { SourceLocationState } from '../utils/backupPlanPayload'
import SourceDirectoriesInput from './SourceDirectoriesInput'

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

interface SourceLocationsInputProps {
  sourceLocations: SourceLocationState[]
  sshConnections: SSHConnection[]
  onChange: (sourceLocations: SourceLocationState[]) => void
  onBrowse: (index: number) => void
  repositoryLocation?: 'local' | 'ssh'
  repoSshConnectionId?: number | ''
  required?: boolean
}

export default function SourceLocationsInput({
  sourceLocations,
  sshConnections,
  onChange,
  onBrowse,
  repositoryLocation = 'local',
  repoSshConnectionId = '',
  required = true,
}: SourceLocationsInputProps) {
  const { t } = useTranslation()
  const locations = sourceLocations.length > 0 ? sourceLocations : []
  const remoteDisabled = repositoryLocation === 'ssh'
  const availableConnections = sshConnections.filter((connection) => {
    if (repositoryLocation === 'ssh' && repoSshConnectionId) {
      return connection.id === repoSshConnectionId
    }
    return true
  })

  const updateLocation = (index: number, updates: Partial<SourceLocationState>) => {
    onChange(locations.map((location, i) => (i === index ? { ...location, ...updates } : location)))
  }

  const removeLocation = (index: number) => {
    onChange(locations.filter((_, i) => i !== index))
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Stack spacing={1}>
        <Typography variant="subtitle2">{t('sourceLocations.title')}</Typography>
        <Typography variant="caption" color="text.secondary">
          {t('sourceLocations.subtitle')}
        </Typography>
      </Stack>

      {locations.map((location, index) => {
        const isRemote = location.sourceType === 'remote'
        return (
          <Box
            key={location.id}
            sx={{
              border: 1,
              borderColor: 'divider',
              borderRadius: 1,
              p: 2,
              display: 'flex',
              flexDirection: 'column',
              gap: 2,
              bgcolor: 'background.paper',
            }}
          >
            <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
              <Stack direction="row" alignItems="center" spacing={1} sx={{ minWidth: 0 }}>
                {isRemote ? <Laptop size={16} /> : <HardDrive size={16} />}
                <Typography variant="subtitle2" noWrap>
                  {t('sourceLocations.sourceLabel', { count: index + 1 })}
                </Typography>
              </Stack>
              {locations.length > 1 && (
                <Tooltip title={t('sourceLocations.remove')} arrow>
                  <IconButton
                    size="small"
                    onClick={() => removeLocation(index)}
                    aria-label={t('sourceLocations.remove')}
                  >
                    <Trash2 size={16} />
                  </IconButton>
                </Tooltip>
              )}
            </Stack>

            <ToggleButtonGroup
              size="small"
              exclusive
              value={location.sourceType}
              onChange={(_, value: 'local' | 'remote' | null) => {
                if (!value || (value === 'remote' && remoteDisabled)) return
                updateLocation(index, {
                  sourceType: value,
                  sourceSshConnectionId: value === 'remote' ? location.sourceSshConnectionId : '',
                  sourceDirectories: [],
                })
              }}
              aria-label={t('sourceLocations.type')}
            >
              <ToggleButton value="local">
                <HardDrive size={14} />
                <Box component="span" sx={{ ml: 0.75 }}>
                  {t('sourceLocations.local')}
                </Box>
              </ToggleButton>
              <ToggleButton value="remote" disabled={remoteDisabled}>
                <Laptop size={14} />
                <Box component="span" sx={{ ml: 0.75 }}>
                  {t('sourceLocations.remote')}
                </Box>
              </ToggleButton>
            </ToggleButtonGroup>

            {remoteDisabled && (
              <Alert severity="info">{t('wizard.dataSource.remoteToRemoteBody')}</Alert>
            )}

            {isRemote && !remoteDisabled && (
              <>
                {!Array.isArray(sshConnections) || sshConnections.length === 0 ? (
                  <Alert severity="warning">{t('wizard.noSshConnections')}</Alert>
                ) : (
                  <FormControl fullWidth>
                    <InputLabel>{t('wizard.dataSource.selectRemoteClient')}</InputLabel>
                    <Select
                      value={
                        location.sourceSshConnectionId === ''
                          ? ''
                          : String(location.sourceSshConnectionId)
                      }
                      label={t('wizard.dataSource.selectRemoteClient')}
                      onChange={(event) => {
                        updateLocation(index, {
                          sourceSshConnectionId: Number(event.target.value),
                          sourceDirectories: [],
                        })
                      }}
                    >
                      {availableConnections.map((connection) => (
                        <MenuItem key={connection.id} value={String(connection.id)}>
                          <Stack direction="row" spacing={1} alignItems="center">
                            <Laptop size={16} />
                            <Box>
                              <Typography variant="body2">
                                {connection.username}@{connection.host}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                Port {connection.port}
                              </Typography>
                            </Box>
                          </Stack>
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                )}
              </>
            )}

            {(!isRemote || location.sourceSshConnectionId) && (
              <SourceDirectoriesInput
                directories={location.sourceDirectories}
                onChange={(sourceDirectories) => updateLocation(index, { sourceDirectories })}
                onBrowseClick={() => onBrowse(index)}
                required={required}
              />
            )}
          </Box>
        )
      })}

      <Button
        variant="outlined"
        startIcon={<Plus size={16} />}
        onClick={() =>
          onChange([
            ...locations,
            {
              id:
                globalThis.crypto?.randomUUID?.() ||
                `source-${Date.now()}-${Math.random().toString(36).slice(2)}`,
              sourceType: 'local',
              sourceSshConnectionId: '',
              sourceDirectories: [],
            },
          ])
        }
        sx={{ alignSelf: 'flex-start' }}
      >
        {t('sourceLocations.add')}
      </Button>
    </Box>
  )
}

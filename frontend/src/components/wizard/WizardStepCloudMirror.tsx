import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  FormControl,
  FormControlLabel,
  IconButton,
  InputAdornment,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Typography,
} from '@mui/material'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'
import { Cloud, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export interface CloudMirrorStepData {
  cloudMirrorEnabled: boolean
  rcloneRemoteId: number | ''
  rcloneRemotePath: string
  rcloneRemotePathVerified: boolean
  rcloneSyncPolicy: 'after_success' | 'manual' | 'scheduled'
  rcloneExtraFlags: string
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

interface WizardStepCloudMirrorProps {
  data: CloudMirrorStepData
  rcloneRemotes?: RcloneRemote[]
  rcloneStatus?: RcloneStatus | null
  eligible: boolean
  onChange: (data: Partial<CloudMirrorStepData>) => void
  onAddRcloneRemote?: () => void
  onBrowseRemotePath?: () => void
}

export default function WizardStepCloudMirror({
  data,
  rcloneRemotes = [],
  rcloneStatus = null,
  eligible,
  onChange,
  onAddRcloneRemote,
  onBrowseRemotePath,
}: WizardStepCloudMirrorProps) {
  const { t } = useTranslation()
  const isRcloneAvailable = rcloneStatus?.available === true
  const controlsDisabled = !eligible || !isRcloneAvailable

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.25 }}>
      <FormControlLabel
        control={
          <Checkbox
            checked={data.cloudMirrorEnabled}
            disabled={!eligible}
            onChange={(event) => {
              onChange({
                cloudMirrorEnabled: event.target.checked,
                rcloneRemotePathVerified: false,
              })
            }}
          />
        }
        label={
          <Box>
            <Typography variant="body2" fontWeight={600}>
              {t('wizard.cloudMirror.enableLabel')}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t('wizard.cloudMirror.enableHelper')}
            </Typography>
          </Box>
        }
      />

      {!eligible && <Alert severity="info">{t('wizard.cloudMirror.localOnly')}</Alert>}

      {data.cloudMirrorEnabled && (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {rcloneStatus && !isRcloneAvailable && (
            <Alert severity="warning">
              {rcloneStatus.error || t('wizard.location.rcloneUnavailable')}
            </Alert>
          )}

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', sm: 'minmax(0, 1fr) auto' },
              gap: 1,
              alignItems: 'start',
            }}
          >
            <FormControl fullWidth disabled={controlsDisabled}>
              <InputLabel id="cloud-mirror-rclone-remote-label">
                {t('wizard.location.rcloneRemoteLabel')}
              </InputLabel>
              <Select
                labelId="cloud-mirror-rclone-remote-label"
                id="cloud-mirror-rclone-remote"
                value={
                  data.rcloneRemoteId === '' || data.rcloneRemoteId == null
                    ? ''
                    : String(data.rcloneRemoteId)
                }
                label={t('wizard.location.rcloneRemoteLabel')}
                onChange={(event) => {
                  const value = event.target.value
                  onChange({
                    rcloneRemoteId: value ? Number(value) : '',
                    rcloneRemotePathVerified: false,
                  })
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
            {onAddRcloneRemote && (
              <Button
                variant="outlined"
                startIcon={<Plus size={16} />}
                onClick={onAddRcloneRemote}
                disabled={controlsDisabled}
                sx={{ height: 56, minHeight: 56, whiteSpace: 'nowrap' }}
              >
                {t('wizard.location.rcloneAddRemote')}
              </Button>
            )}
          </Box>

          {rcloneRemotes.length === 0 && (
            <Alert severity="info">{t('wizard.location.rcloneNoRemotes')}</Alert>
          )}

          <TextField
            label={t('wizard.location.rcloneRemotePathLabel')}
            value={data.rcloneRemotePath || ''}
            onChange={(event) => {
              onChange({
                rcloneRemotePath: event.target.value,
                rcloneRemotePathVerified: false,
              })
            }}
            placeholder="borg-ui/repositories/app"
            required
            fullWidth
            disabled={controlsDisabled}
            helperText={
              data.rcloneRemotePathVerified
                ? t('wizard.cloudMirror.remotePathVerified')
                : t('wizard.location.rcloneRemotePathHelper')
            }
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    onClick={onBrowseRemotePath}
                    edge="end"
                    size="small"
                    title={t('wizard.cloudMirror.browseRemote')}
                    aria-label={t('wizard.cloudMirror.browseRemote')}
                    disabled={controlsDisabled || !data.rcloneRemoteId}
                  >
                    <FolderOpenIcon fontSize="small" />
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />

          <FormControl fullWidth disabled={controlsDisabled}>
            <InputLabel id="cloud-mirror-sync-policy-label">
              {t('wizard.location.rcloneSyncPolicyLabel')}
            </InputLabel>
            <Select
              labelId="cloud-mirror-sync-policy-label"
              id="cloud-mirror-sync-policy"
              value={data.rcloneSyncPolicy || 'after_success'}
              label={t('wizard.location.rcloneSyncPolicyLabel')}
              onChange={(event) =>
                onChange({
                  rcloneSyncPolicy: event.target.value as 'after_success' | 'manual' | 'scheduled',
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
            onChange={(event) => onChange({ rcloneExtraFlags: event.target.value })}
            placeholder="--fast-list"
            fullWidth
            disabled={controlsDisabled}
            helperText={t('wizard.location.rcloneExtraFlagsHelper')}
          />

          <Alert severity="info" icon={<Cloud size={18} />}>
            {t('wizard.cloudMirror.routePreview')}
          </Alert>
        </Box>
      )}
    </Box>
  )
}

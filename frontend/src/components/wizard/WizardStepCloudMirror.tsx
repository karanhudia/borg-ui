import {
  Alert,
  Box,
  Button,
  Checkbox,
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
import SchedulePicker from '../shared/SchedulePicker'
import RcloneRemoteSelect from '../shared/RcloneRemoteSelect'

export interface CloudMirrorStepData {
  cloudMirrorEnabled: boolean
  rcloneRemoteId: number | ''
  rcloneRemotePath: string
  rcloneRemotePathVerified: boolean
  rcloneSyncPolicy: 'after_success' | 'manual' | 'scheduled'
  rcloneSyncCronExpression: string
  rcloneSyncTimezone: string
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
  primaryLocation?: 'local' | 'ssh' | 'agent'
  storageMode?: 'mirror' | 'cachedRepository'
  onChange: (data: Partial<CloudMirrorStepData>) => void
  onAddRcloneRemote?: () => void
  onBrowseRemotePath?: () => void
}

export default function WizardStepCloudMirror({
  data,
  rcloneRemotes = [],
  rcloneStatus = null,
  eligible,
  primaryLocation = 'local',
  storageMode = 'mirror',
  onChange,
  onAddRcloneRemote,
  onBrowseRemotePath,
}: WizardStepCloudMirrorProps) {
  const { t } = useTranslation()
  const isRcloneAvailable = rcloneStatus?.available === true
  const isCachedRepositoryMode = storageMode === 'cachedRepository'
  const controlsDisabled = !eligible || !isRcloneAvailable
  const ineligibleMessage = t('wizard.cloudMirror.unsupportedPrimary')
  const routePreview = isCachedRepositoryMode
    ? t('wizard.cloudMirror.cachedRepositoryRoutePreview')
    : primaryLocation === 'agent'
      ? t('wizard.cloudMirror.agentRoutePreview')
      : primaryLocation === 'ssh'
        ? t('wizard.cloudMirror.sshRoutePreview')
        : t('wizard.cloudMirror.routePreview')
  const enableLabel = isCachedRepositoryMode
    ? t('wizard.cloudMirror.cachedRepositoryLabel')
    : t('wizard.cloudMirror.enableLabel')
  const enableHelper = isCachedRepositoryMode
    ? t('wizard.cloudMirror.cachedRepositoryHelper')
    : t('wizard.cloudMirror.enableHelper')

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.25 }}>
      <FormControlLabel
        control={
          <Checkbox
            checked={data.cloudMirrorEnabled}
            disabled={!eligible || isCachedRepositoryMode}
            onChange={(event) => {
              if (isCachedRepositoryMode) return
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
              {enableLabel}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {enableHelper}
            </Typography>
          </Box>
        }
      />

      {!eligible && <Alert severity="info">{ineligibleMessage}</Alert>}

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
            <RcloneRemoteSelect
              value={
                data.rcloneRemoteId === '' || data.rcloneRemoteId == null ? '' : data.rcloneRemoteId
              }
              onChange={(id) =>
                onChange({
                  rcloneRemoteId: id,
                  rcloneRemotePathVerified: false,
                })
              }
              remotes={rcloneRemotes}
              label={t('wizard.location.rcloneRemoteLabel')}
              emptyMessage={t('wizard.location.rcloneNoRemotes')}
              labelId="cloud-mirror-rclone-remote-label"
              selectId="cloud-mirror-rclone-remote"
              disabled={controlsDisabled}
            />
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
              onChange={(event) => {
                const policy = event.target.value as 'after_success' | 'manual' | 'scheduled'
                onChange({
                  rcloneSyncPolicy: policy,
                  ...(policy === 'scheduled' && !data.rcloneSyncCronExpression
                    ? { rcloneSyncCronExpression: '0 */6 * * *' }
                    : {}),
                  ...(policy === 'scheduled' && !data.rcloneSyncTimezone
                    ? { rcloneSyncTimezone: 'UTC' }
                    : {}),
                })
              }}
            >
              <MenuItem value="after_success">
                {t('wizard.location.rcloneSyncAfterSuccess')}
              </MenuItem>
              <MenuItem value="manual">{t('wizard.location.rcloneSyncManual')}</MenuItem>
              <MenuItem value="scheduled">{t('wizard.location.rcloneSyncScheduled')}</MenuItem>
            </Select>
          </FormControl>

          {data.rcloneSyncPolicy === 'scheduled' && (
            <SchedulePicker
              cronExpression={data.rcloneSyncCronExpression || ''}
              timezone={data.rcloneSyncTimezone || 'UTC'}
              onChange={(updates) =>
                onChange({
                  ...(updates.cronExpression !== undefined
                    ? { rcloneSyncCronExpression: updates.cronExpression }
                    : {}),
                  ...(updates.timezone !== undefined
                    ? { rcloneSyncTimezone: updates.timezone }
                    : {}),
                })
              }
              required
              disabled={controlsDisabled}
              cronLabel={t('wizard.location.rcloneSyncCronLabel')}
              cronHelperText={t('wizard.location.rcloneSyncCronHelper')}
              timezoneLabel={t('wizard.location.rcloneSyncTimezoneLabel')}
            />
          )}

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
            {routePreview}
          </Alert>
        </Box>
      )}
    </Box>
  )
}

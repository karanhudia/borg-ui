import {
  Alert,
  Box,
  Button,
  Checkbox,
  IconButton,
  Tooltip,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Typography,
} from '@mui/material'
import { Cloud, KeyRound, Lock, Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import PathSelectorField from '../shared/PathSelectorField'
import SchedulePicker from '../shared/SchedulePicker'
import RcloneRemoteSelect from '../shared/RcloneRemoteSelect'
import RichSelect from '../shared/RichSelect'

export interface CloudMirrorStepData {
  cloudMirrorEnabled: boolean
  rcloneRemoteId: number | ''
  rcloneRemotePath: string
  rcloneRemotePathVerified: boolean
  rcloneSyncPolicy: 'after_success' | 'manual' | 'scheduled'
  rcloneSyncCronExpression: string
  rcloneSyncTimezone: string
  rcloneExtraFlags: string
  rcloneSftpSshKeyId?: number | ''
}

export interface SftpSshKeyOption {
  id: number
  name: string
  key_type: string
  fingerprint?: string | null
  sftp_repository_count?: number
}

const SAME_KEY_VALUE = 'connection-key'

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
  sftpSshKeys?: SftpSshKeyOption[]
  rcloneStatus?: RcloneStatus | null
  eligible: boolean
  primaryLocation?: 'local' | 'ssh' | 'agent'
  storageMode?: 'mirror' | 'cachedRepository'
  canUseRclone?: boolean
  onChange: (data: Partial<CloudMirrorStepData>) => void
  onAddRcloneRemote?: () => void
  onBrowseRemotePath?: () => void
  onAddSshKey?: () => void
  onDeleteSshKey?: (key: SftpSshKeyOption) => void
}

export default function WizardStepCloudMirror({
  data,
  rcloneRemotes = [],
  sftpSshKeys = [],
  rcloneStatus = null,
  eligible,
  primaryLocation = 'local',
  storageMode = 'mirror',
  canUseRclone = true,
  onChange,
  onAddRcloneRemote,
  onBrowseRemotePath,
  onAddSshKey,
  onDeleteSshKey,
}: WizardStepCloudMirrorProps) {
  const { t } = useTranslation()
  const isRcloneAvailable = rcloneStatus?.available === true
  const isCachedRepositoryMode = storageMode === 'cachedRepository'
  const controlsDisabled = !eligible || !isRcloneAvailable || !canUseRclone
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
  const selectedSftpKey = sftpSshKeys.find((key) => key.id === data.rcloneSftpSshKeyId)
  const enableHelper = isCachedRepositoryMode
    ? t('wizard.cloudMirror.cachedRepositoryHelper')
    : t('wizard.cloudMirror.enableHelper')

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.25 }}>
      <FormControlLabel
        control={
          <Checkbox
            checked={data.cloudMirrorEnabled}
            disabled={!eligible || isCachedRepositoryMode || !canUseRclone}
            onChange={(event) => {
              if (isCachedRepositoryMode) return
              if (event.target.checked && !canUseRclone) return
              onChange({
                cloudMirrorEnabled: event.target.checked,
                rcloneRemotePathVerified: false,
              })
            }}
          />
        }
        label={
          <Box>
            <Typography
              variant="body2"
              sx={{
                fontWeight: 600,
              }}
            >
              {enableLabel}
            </Typography>
            <Typography
              variant="caption"
              sx={{
                color: 'text.secondary',
              }}
            >
              {enableHelper}
            </Typography>
          </Box>
        }
      />

      {!eligible && <Alert severity="info">{ineligibleMessage}</Alert>}
      {!canUseRclone && (
        <Alert severity="info" icon={<Lock size={18} />}>
          {t('wizard.cloudMirror.requiresPro')}
        </Alert>
      )}

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

          <PathSelectorField
            label={t('wizard.location.rcloneRemotePathLabel')}
            value={data.rcloneRemotePath || ''}
            onChange={(value) => {
              onChange({
                rcloneRemotePath: value,
                rcloneRemotePathVerified: false,
              })
            }}
            placeholder="borg-ui/repositories/app"
            required
            disabled={controlsDisabled}
            helperText={
              data.rcloneRemotePathVerified
                ? t('wizard.cloudMirror.remotePathVerified')
                : t('wizard.location.rcloneRemotePathHelper')
            }
            onBrowse={onBrowseRemotePath}
            browseButtonLabel={t('wizard.cloudMirror.browseRemote')}
            browseButtonDisabled={controlsDisabled || !data.rcloneRemoteId || !onBrowseRemotePath}
          />

          {primaryLocation === 'ssh' && !isCachedRepositoryMode && (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr', sm: 'minmax(0, 1fr) auto auto' },
                  gap: 1,
                  alignItems: 'start',
                }}
              >
                <RichSelect
                  value={data.rcloneSftpSshKeyId ? String(data.rcloneSftpSshKeyId) : SAME_KEY_VALUE}
                  onChange={(next) =>
                    onChange({ rcloneSftpSshKeyId: next === SAME_KEY_VALUE ? '' : Number(next) })
                  }
                  options={[
                    {
                      value: SAME_KEY_VALUE,
                      icon: <KeyRound size={16} />,
                      primary: t('wizard.cloudMirror.sftpKeyDefault'),
                    },
                    ...sftpSshKeys.map((key) => ({
                      value: String(key.id),
                      icon: <KeyRound size={16} />,
                      primary: key.name,
                      secondary: key.fingerprint || key.key_type,
                    })),
                  ]}
                  label={t('wizard.cloudMirror.sftpKeyLabel')}
                  labelId="cloud-mirror-sftp-key-label"
                  disabled={controlsDisabled}
                />
                {onAddSshKey && (
                  <Button
                    variant="outlined"
                    startIcon={<Plus size={16} />}
                    onClick={onAddSshKey}
                    disabled={controlsDisabled}
                    sx={{ height: 56, minHeight: 56, whiteSpace: 'nowrap' }}
                  >
                    {t('wizard.cloudMirror.sftpKeyAdd')}
                  </Button>
                )}
                {onDeleteSshKey && (
                  <Tooltip title={t('wizard.cloudMirror.sftpKeyDelete')}>
                    <span>
                      <IconButton
                        aria-label={t('wizard.cloudMirror.sftpKeyDelete')}
                        onClick={() => selectedSftpKey && onDeleteSshKey(selectedSftpKey)}
                        disabled={controlsDisabled || !selectedSftpKey}
                        sx={{
                          width: 56,
                          height: 56,
                          border: 1,
                          borderColor: 'divider',
                          borderRadius: 1,
                        }}
                      >
                        <Trash2 size={18} />
                      </IconButton>
                    </span>
                  </Tooltip>
                )}
              </Box>
              <Typography variant="caption" sx={{ color: 'text.secondary', px: 1.75 }}>
                {t('wizard.cloudMirror.sftpKeyHelper')}
              </Typography>
            </Box>
          )}

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

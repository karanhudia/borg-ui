import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  Divider,
  FormControlLabel,
  IconButton,
  MenuItem,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { SystemSettings } from '../../services/api'
import type {
  AuthEventFilter,
  AuthEventFormatter,
  AuthEventRefetch,
  AuthEventStats,
  AuthEvents,
} from './types'

interface OidcSectionProps {
  systemSettings?: SystemSettings
  oidcEnabled: boolean
  oidcDisableLocalAuth: boolean
  oidcProviderName: string
  oidcTokenAuthMethod: string
  oidcDiscoveryUrl: string
  oidcClientId: string
  oidcClientSecret: string
  clearOidcClientSecret: boolean
  oidcScopes: string
  oidcRedirectUriOverride: string
  oidcEndSessionEndpointOverride: string
  oidcClaimUsername: string
  oidcClaimEmail: string
  oidcClaimFullName: string
  oidcGroupClaim: string
  oidcRoleClaim: string
  oidcAdminGroups: string
  oidcAllRepositoriesRoleClaim: string
  oidcNewUserMode: string
  oidcTemplateUsername: string
  oidcDefaultRole: string
  oidcDefaultAllRepositoriesRole: string
  hasOidcActiveAdminSignal: boolean
  hasActiveOidcAdmin: boolean
  authEventsLoading: boolean
  authEventsData: AuthEvents
  authEventStats: AuthEventStats
  filteredAuthEvents: AuthEvents
  authEventFilter: AuthEventFilter
  formatAuthEventType: AuthEventFormatter
  formatAuthSource: AuthEventFormatter
  refetchAuthEvents: AuthEventRefetch
  setOidcEnabled: (value: boolean) => void
  setOidcDisableLocalAuth: (value: boolean) => void
  setOidcProviderName: (value: string) => void
  setOidcTokenAuthMethod: (value: string) => void
  setOidcDiscoveryUrl: (value: string) => void
  setOidcClientId: (value: string) => void
  setOidcClientSecret: (value: string) => void
  setClearOidcClientSecret: (value: boolean) => void
  setOidcScopes: (value: string) => void
  setOidcRedirectUriOverride: (value: string) => void
  setOidcEndSessionEndpointOverride: (value: string) => void
  setOidcClaimUsername: (value: string) => void
  setOidcClaimEmail: (value: string) => void
  setOidcClaimFullName: (value: string) => void
  setOidcGroupClaim: (value: string) => void
  setOidcRoleClaim: (value: string) => void
  setOidcAdminGroups: (value: string) => void
  setOidcAllRepositoriesRoleClaim: (value: string) => void
  setOidcNewUserMode: (value: string) => void
  setOidcTemplateUsername: (value: string) => void
  setOidcDefaultRole: (value: string) => void
  setOidcDefaultAllRepositoriesRole: (value: string) => void
  setAuthEventFilter: (value: AuthEventFilter) => void
}

const OidcSection: React.FC<OidcSectionProps> = ({
  systemSettings,
  oidcEnabled,
  oidcDisableLocalAuth,
  oidcProviderName,
  oidcTokenAuthMethod,
  oidcDiscoveryUrl,
  oidcClientId,
  oidcClientSecret,
  clearOidcClientSecret,
  oidcScopes,
  oidcRedirectUriOverride,
  oidcEndSessionEndpointOverride,
  oidcClaimUsername,
  oidcClaimEmail,
  oidcClaimFullName,
  oidcGroupClaim,
  oidcRoleClaim,
  oidcAdminGroups,
  oidcAllRepositoriesRoleClaim,
  oidcNewUserMode,
  oidcTemplateUsername,
  oidcDefaultRole,
  oidcDefaultAllRepositoriesRole,
  hasOidcActiveAdminSignal,
  hasActiveOidcAdmin,
  authEventsLoading,
  authEventsData,
  authEventStats,
  filteredAuthEvents,
  authEventFilter,
  formatAuthEventType,
  formatAuthSource,
  refetchAuthEvents,
  setOidcEnabled,
  setOidcDisableLocalAuth,
  setOidcProviderName,
  setOidcTokenAuthMethod,
  setOidcDiscoveryUrl,
  setOidcClientId,
  setOidcClientSecret,
  setClearOidcClientSecret,
  setOidcScopes,
  setOidcRedirectUriOverride,
  setOidcEndSessionEndpointOverride,
  setOidcClaimUsername,
  setOidcClaimEmail,
  setOidcClaimFullName,
  setOidcGroupClaim,
  setOidcRoleClaim,
  setOidcAdminGroups,
  setOidcAllRepositoriesRoleClaim,
  setOidcNewUserMode,
  setOidcTemplateUsername,
  setOidcDefaultRole,
  setOidcDefaultAllRepositoriesRole,
  setAuthEventFilter,
}) => {
  const { t } = useTranslation()

  return (
    <Stack spacing={2.5}>
      <FormControlLabel
        control={
          <Switch checked={oidcEnabled} onChange={(e) => setOidcEnabled(e.target.checked)} />
        }
        label={t('systemSettings.oidcEnabledLabel')}
      />

      <FormControlLabel
        control={
          <Switch
            checked={oidcDisableLocalAuth}
            disabled={!oidcEnabled}
            onChange={(e) => setOidcDisableLocalAuth(e.target.checked)}
          />
        }
        label={t('systemSettings.oidcDisableLocalAuthLabel')}
      />

      {oidcEnabled && oidcDisableLocalAuth && (
        <Alert severity={hasOidcActiveAdminSignal && !hasActiveOidcAdmin ? 'error' : 'warning'}>
          <Typography variant="body2">
            {hasOidcActiveAdminSignal && !hasActiveOidcAdmin
              ? t('systemSettings.oidcActiveAdminRequired')
              : t('systemSettings.oidcDisableLocalAuthWarning')}
          </Typography>
        </Alert>
      )}

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' },
          gap: 2,
        }}
      >
        <TextField
          label={t('systemSettings.oidcProviderNameLabel')}
          value={oidcProviderName}
          onChange={(e) => setOidcProviderName(e.target.value)}
          helperText={t('systemSettings.oidcProviderNameHelper')}
        />
        <TextField
          select
          label={t('systemSettings.oidcTokenAuthMethodLabel')}
          value={oidcTokenAuthMethod}
          onChange={(e) => setOidcTokenAuthMethod(e.target.value)}
          helperText={t('systemSettings.oidcTokenAuthMethodHelper')}
        >
          <MenuItem value="client_secret_post">
            {t('systemSettings.oidcTokenAuthMethodPost')}
          </MenuItem>
          <MenuItem value="client_secret_basic">
            {t('systemSettings.oidcTokenAuthMethodBasic')}
          </MenuItem>
        </TextField>
        <TextField
          label={t('systemSettings.oidcDiscoveryUrlLabel')}
          value={oidcDiscoveryUrl}
          onChange={(e) => setOidcDiscoveryUrl(e.target.value)}
          helperText={t('systemSettings.oidcDiscoveryUrlHelper')}
        />
        <TextField
          label={t('systemSettings.oidcClientIdLabel')}
          value={oidcClientId}
          onChange={(e) => setOidcClientId(e.target.value)}
        />
        <TextField
          label={t('systemSettings.oidcClientSecretLabel')}
          type="password"
          value={oidcClientSecret}
          onChange={(e) => setOidcClientSecret(e.target.value)}
          helperText={
            systemSettings?.oidc_client_secret_set
              ? t('systemSettings.oidcClientSecretConfigured')
              : t('systemSettings.oidcClientSecretRequiredHelper')
          }
        />
        <TextField
          label={t('systemSettings.oidcScopesLabel')}
          value={oidcScopes}
          onChange={(e) => setOidcScopes(e.target.value)}
        />
        <TextField
          label={t('systemSettings.oidcRedirectUriOverrideLabel')}
          value={oidcRedirectUriOverride}
          onChange={(e) => setOidcRedirectUriOverride(e.target.value)}
          helperText={t('systemSettings.oidcRedirectUriOverrideHelper')}
        />
        <TextField
          label={t('systemSettings.oidcEndSessionEndpointOverrideLabel')}
          value={oidcEndSessionEndpointOverride}
          onChange={(e) => setOidcEndSessionEndpointOverride(e.target.value)}
          helperText={t('systemSettings.oidcEndSessionEndpointOverrideHelper')}
        />
        <TextField
          label={t('systemSettings.oidcClaimUsernameLabel')}
          value={oidcClaimUsername}
          onChange={(e) => setOidcClaimUsername(e.target.value)}
        />
        <TextField
          label={t('systemSettings.oidcClaimEmailLabel')}
          value={oidcClaimEmail}
          onChange={(e) => setOidcClaimEmail(e.target.value)}
        />
        <TextField
          label={t('systemSettings.oidcClaimFullNameLabel')}
          value={oidcClaimFullName}
          onChange={(e) => setOidcClaimFullName(e.target.value)}
        />
        <TextField
          label={t('systemSettings.oidcGroupClaimLabel')}
          value={oidcGroupClaim}
          onChange={(e) => setOidcGroupClaim(e.target.value)}
          helperText={t('systemSettings.oidcGroupClaimHelper')}
        />
        <TextField
          label={t('systemSettings.oidcRoleClaimLabel')}
          value={oidcRoleClaim}
          onChange={(e) => setOidcRoleClaim(e.target.value)}
        />
        <TextField
          label={t('systemSettings.oidcAdminGroupsLabel')}
          value={oidcAdminGroups}
          onChange={(e) => setOidcAdminGroups(e.target.value)}
          helperText={t('systemSettings.oidcAdminGroupsHelper')}
        />
        <TextField
          label={t('systemSettings.oidcAllRepositoriesRoleClaimLabel')}
          value={oidcAllRepositoriesRoleClaim}
          onChange={(e) => setOidcAllRepositoriesRoleClaim(e.target.value)}
        />
        <TextField
          select
          label={t('systemSettings.oidcNewUserModeLabel')}
          value={oidcNewUserMode}
          onChange={(e) => setOidcNewUserMode(e.target.value)}
        >
          <MenuItem value="deny">{t('systemSettings.oidcModeDeny')}</MenuItem>
          <MenuItem value="viewer">{t('systemSettings.oidcModeViewer')}</MenuItem>
          <MenuItem value="pending">{t('systemSettings.oidcModePending')}</MenuItem>
          <MenuItem value="template">{t('systemSettings.oidcModeTemplate')}</MenuItem>
        </TextField>
        <TextField
          label={t('systemSettings.oidcTemplateUsernameLabel')}
          value={oidcTemplateUsername}
          disabled={oidcNewUserMode !== 'template'}
          onChange={(e) => setOidcTemplateUsername(e.target.value)}
        />
        <TextField
          select
          label={t('systemSettings.oidcDefaultRoleLabel')}
          value={oidcDefaultRole}
          onChange={(e) => setOidcDefaultRole(e.target.value)}
        >
          <MenuItem value="viewer">{t('systemSettings.roleViewer')}</MenuItem>
          <MenuItem value="operator">{t('systemSettings.roleOperator')}</MenuItem>
          <MenuItem value="admin">{t('systemSettings.roleAdmin')}</MenuItem>
        </TextField>
        <TextField
          select
          label={t('systemSettings.oidcDefaultAllRepositoriesRoleLabel')}
          value={oidcDefaultAllRepositoriesRole}
          onChange={(e) => setOidcDefaultAllRepositoriesRole(e.target.value)}
        >
          <MenuItem value="viewer">{t('systemSettings.roleViewer')}</MenuItem>
          <MenuItem value="operator">{t('systemSettings.roleOperator')}</MenuItem>
        </TextField>
      </Box>

      <FormControlLabel
        control={
          <Switch
            checked={clearOidcClientSecret}
            disabled={!systemSettings?.oidc_client_secret_set}
            onChange={(e) => setClearOidcClientSecret(e.target.checked)}
          />
        }
        label={t('systemSettings.oidcClearClientSecretLabel')}
      />

      <Divider />

      <Stack spacing={1.25}>
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={1.5}
          justifyContent="space-between"
          alignItems={{ xs: 'stretch', md: 'flex-start' }}
        >
          <Box>
            <Typography variant="subtitle1" fontWeight={600}>
              {t('systemSettings.oidcEventsTitle')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('systemSettings.oidcEventsDescription')}
            </Typography>
          </Box>
          <Tooltip title={t('systemSettings.oidcEventsRefresh')}>
            <span>
              <IconButton
                size="small"
                onClick={() => refetchAuthEvents()}
                disabled={authEventsLoading}
              >
                <RefreshCw size={16} />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>

        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Chip
            size="small"
            variant="outlined"
            label={t('systemSettings.authEventSummary.total', { count: authEventStats.total })}
          />
          <Chip
            size="small"
            color="success"
            variant="outlined"
            label={t('systemSettings.authEventSummary.success', { count: authEventStats.success })}
          />
          <Chip
            size="small"
            color="error"
            variant="outlined"
            label={t('systemSettings.authEventSummary.failed', { count: authEventStats.failed })}
          />
          <Chip
            size="small"
            color="warning"
            variant="outlined"
            label={t('systemSettings.authEventSummary.pending', { count: authEventStats.pending })}
          />
        </Stack>

        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {(
            [
              ['all', 'systemSettings.authEventFilters.all'],
              ['failed', 'systemSettings.authEventFilters.failed'],
              ['oidc', 'systemSettings.authEventFilters.oidc'],
              ['pending', 'systemSettings.authEventFilters.pending'],
            ] as const
          ).map(([value, labelKey]) => (
            <Chip
              key={value}
              size="small"
              label={t(labelKey)}
              clickable
              color={authEventFilter === value ? 'primary' : 'default'}
              variant={authEventFilter === value ? 'filled' : 'outlined'}
              onClick={() => setAuthEventFilter(value)}
            />
          ))}
        </Stack>

        {authEventsLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
            <CircularProgress size={20} />
          </Box>
        ) : (authEventsData?.length ?? 0) === 0 ? (
          <Alert severity="info">{t('systemSettings.oidcEventsEmpty')}</Alert>
        ) : (filteredAuthEvents?.length ?? 0) === 0 ? (
          <Alert severity="info">{t('systemSettings.oidcEventsFilteredEmpty')}</Alert>
        ) : (
          <Stack spacing={1}>
            {filteredAuthEvents?.map((event) => {
              const isPendingEvent = event.event_type === 'oidc_user_pending'
              return (
                <Box
                  key={event.id}
                  sx={{
                    border: '1px solid',
                    borderColor: isPendingEvent ? 'warning.light' : 'divider',
                    borderRadius: 2,
                    px: 1.5,
                    py: 1.25,
                    bgcolor: isPendingEvent ? 'rgba(245, 158, 11, 0.06)' : 'transparent',
                  }}
                >
                  <Stack
                    direction={{ xs: 'column', md: 'row' }}
                    spacing={1.5}
                    justifyContent="space-between"
                  >
                    <Stack spacing={0.4}>
                      <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                        <Chip
                          size="small"
                          label={formatAuthEventType(event.event_type)}
                          color={isPendingEvent ? 'warning' : 'default'}
                          variant={isPendingEvent ? 'filled' : 'outlined'}
                        />
                        <Chip
                          size="small"
                          label={formatAuthSource(event.auth_source)}
                          variant="outlined"
                          color={event.auth_source === 'oidc' ? 'info' : 'default'}
                        />
                      </Stack>
                      <Typography variant="body2" fontWeight={600}>
                        {event.username || event.email || t('systemSettings.authEventAnonymous')}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {[
                          event.email,
                          event.actor_user_id
                            ? t('systemSettings.authEventActor', { id: event.actor_user_id })
                            : null,
                        ]
                          .filter(Boolean)
                          .join(' • ')}
                      </Typography>
                      {event.detail && (
                        <Typography variant="caption" color="text.secondary">
                          {event.detail}
                        </Typography>
                      )}
                    </Stack>
                    <Stack spacing={0.4} alignItems={{ xs: 'flex-start', md: 'flex-end' }}>
                      <Typography
                        variant="caption"
                        sx={{
                          color: isPendingEvent
                            ? 'warning.main'
                            : event.success
                              ? 'success.main'
                              : 'error.main',
                          fontWeight: 600,
                        }}
                      >
                        {isPendingEvent
                          ? t('systemSettings.authEventPending')
                          : event.success
                            ? t('systemSettings.authEventSuccess')
                            : t('systemSettings.authEventFailed')}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {new Date(event.created_at).toLocaleString()}
                      </Typography>
                    </Stack>
                  </Stack>
                </Box>
              )
            })}
          </Stack>
        )}
      </Stack>
    </Stack>
  )
}

export default OidcSection

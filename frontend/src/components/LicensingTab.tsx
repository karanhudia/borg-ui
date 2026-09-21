import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Divider,
  Link,
  Stack,
  TextField,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import { KeyRound, RefreshCw, ShieldCheck, ShieldOff } from 'lucide-react'
import SettingsCard from './SettingsCard'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { licensingAPI } from '../services/api'
import { usePlan } from '../hooks/usePlan'
import { translateBackendKey } from '../utils/translateBackendKey'
import { useAnalytics } from '../hooks/useAnalytics'
import { buildBuyUrl } from '../utils/externalLinks'
import { PLAN_LABEL, nextPlanAbove } from '../core/features'
import PlanInfoDrawer from './PlanInfoDrawer'
import LicenseSeatsCard from './LicenseSeatsCard'
import LicenseIdentifierRow from './LicenseIdentifierRow'
import { tintChipSx, type Tone } from './shared/tones'

export default function LicensingTab() {
  const { t, i18n } = useTranslation()
  const theme = useTheme()
  const queryClient = useQueryClient()
  const { plan, features, entitlement } = usePlan()
  const { trackPlan, EventAction } = useAnalytics()
  const [licenseKey, setLicenseKey] = useState('')
  // A live paid licence hides the key field behind "Replace licence", so the
  // state actions next to it cannot read as if they needed a key typed in.
  const [replacingLicense, setReplacingLicense] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)

  const analyticsContext = useMemo(
    () => ({
      surface: 'licensing_tab',
      current_plan: plan,
      access_level: entitlement?.access_level ?? 'community',
      ui_state: entitlement?.ui_state ?? 'community',
      status: entitlement?.status ?? 'none',
      is_full_access: !!(entitlement?.is_full_access && entitlement.status === 'active'),
      has_license_id: !!entitlement?.license_id,
    }),
    [entitlement, plan]
  )

  const refreshSystemInfo = async () => {
    await queryClient.invalidateQueries({ queryKey: ['system-info'] })
  }

  useEffect(() => {
    trackPlan(EventAction.VIEW, analyticsContext)
  }, [analyticsContext, trackPlan, EventAction])

  const refreshMutation = useMutation({
    mutationFn: async () => licensingAPI.refresh(),
    onSuccess: async () => {
      await refreshSystemInfo()
      trackPlan(EventAction.COMPLETE, {
        ...analyticsContext,
        operation: 'refresh_license',
      })
      toast.success(t('plan.licenseRefreshSuccess'))
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      trackPlan(EventAction.FAIL, {
        ...analyticsContext,
        operation: 'refresh_license',
      })
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('plan.licenseRefreshFailed')
      )
    },
  })

  const activateMutation = useMutation({
    mutationFn: async (nextLicenseKey: string) => licensingAPI.activate(nextLicenseKey),
    onSuccess: async (_response, nextLicenseKey) => {
      await refreshSystemInfo()
      // The seats belong to the licence, not the instance: a replacement
      // makes the cached list the previous licence's.
      await queryClient.invalidateQueries({ queryKey: ['license-seats'] })
      trackPlan(EventAction.COMPLETE, {
        ...analyticsContext,
        operation: activePaidLicense ? 'replace_license' : 'activate_license',
        license_key_length: nextLicenseKey.length,
      })
      setLicenseKey('')
      setReplacingLicense(false)
      toast.success(t('plan.licenseActivationSuccess'))
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      trackPlan(EventAction.FAIL, {
        ...analyticsContext,
        operation: activePaidLicense ? 'replace_license' : 'activate_license',
      })
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('plan.licenseActivationFailed')
      )
    },
  })

  const deactivateMutation = useMutation({
    mutationFn: async () => licensingAPI.deactivate(),
    onSuccess: async () => {
      await refreshSystemInfo()
      trackPlan(EventAction.COMPLETE, {
        ...analyticsContext,
        operation: 'deactivate_license',
      })
      setLicenseKey('')
      setReplacingLicense(false)
      toast.success(t('plan.licenseDeactivationSuccess'))
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      trackPlan(EventAction.FAIL, {
        ...analyticsContext,
        operation: 'deactivate_license',
      })
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('plan.licenseDeactivationFailed')
      )
    },
  })

  const isMutating =
    refreshMutation.isPending || activateMutation.isPending || deactivateMutation.isPending
  const isFullAccess = entitlement?.is_full_access && entitlement.status === 'active'
  const activePaidLicense = entitlement?.ui_state === 'paid_active'
  const keyEntryOpen = !activePaidLicense || replacingLicense
  // The buy link sells the tier above the current plan; Enterprise has none.
  const upgradePlan = nextPlanAbove(plan)
  const statusLabel = isFullAccess
    ? t('plan.fullAccessLabel')
    : plan === 'community'
      ? 'Community'
      : plan === 'pro'
        ? 'Pro'
        : 'Enterprise'

  // The header carries state as a chip, so the page needs no green banner.
  const statusNeutral =
    !activePaidLicense && !isFullAccess && entitlement?.ui_state !== 'full_access_expired'
  const statusTone: Tone = activePaidLicense
    ? 'success'
    : isFullAccess
      ? 'info'
      : entitlement?.ui_state === 'full_access_expired'
        ? 'warning'
        : 'primary'
  const statusChipLabel = activePaidLicense
    ? t('licensing.statusActive')
    : isFullAccess
      ? t('licensing.statusFullAccess')
      : entitlement?.ui_state === 'full_access_expired'
        ? t('licensing.statusExpired')
        : t('licensing.statusCommunity')
  const expiresOn = entitlement?.expires_at
    ? new Date(entitlement.expires_at).toLocaleDateString(i18n.resolvedLanguage)
    : null
  const headerSubline = activePaidLicense
    ? expiresOn
      ? t('licensing.validUntil', { date: expiresOn })
      : t('licensing.validIndefinitely')
    : isFullAccess
      ? t('plan.fullAccessActiveNotice', { date: expiresOn ?? t('navigation.loading') })
      : t('licensing.noPaidLicence')

  const handleActivate = () => {
    const trimmedKey = licenseKey.trim()
    if (!trimmedKey) {
      trackPlan(EventAction.FAIL, {
        ...analyticsContext,
        operation: activePaidLicense ? 'replace_license' : 'activate_license',
        failure_reason: 'missing_license_key',
        stage: 'validation',
      })
      toast.error(t('plan.licenseKeyRequired'))
      return
    }
    trackPlan(EventAction.START, {
      ...analyticsContext,
      operation: activePaidLicense ? 'replace_license' : 'activate_license',
      license_key_length: trimmedKey.length,
    })
    activateMutation.mutate(trimmedKey)
  }

  const handleDeactivate = () => {
    trackPlan(EventAction.START, {
      ...analyticsContext,
      operation: 'deactivate_license',
    })
    deactivateMutation.mutate()
  }

  const handleBuyClick = () => {
    trackPlan(EventAction.VIEW, {
      ...analyticsContext,
      operation: 'open_buy_link',
      selected_plan: upgradePlan,
    })
  }

  return (
    <Stack spacing={3}>
      <Box>
        <Typography
          variant="h6"
          sx={{
            fontWeight: 700,
          }}
        >
          {t('licensing.title')}
        </Typography>
        <Typography
          variant="body2"
          sx={{
            color: 'text.secondary',
          }}
        >
          {t('licensing.subtitle')}
        </Typography>
      </Box>
      <SettingsCard contentSx={{ p: 0, '&:last-child': { pb: 0 } }}>
        {/* Who this instance is, and on what. */}
        <Stack direction="row" spacing={2} sx={{ p: { xs: 2, md: 3 }, alignItems: 'center' }}>
          <Box
            sx={{
              width: 44,
              height: 44,
              borderRadius: 2,
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: statusNeutral ? 'text.secondary' : theme.palette[statusTone].main,
              bgcolor: alpha(
                statusNeutral ? theme.palette.text.primary : theme.palette[statusTone].main,
                theme.palette.mode === 'dark' ? 0.12 : 0.07
              ),
            }}
          >
            {activePaidLicense || isFullAccess ? (
              <ShieldCheck size={22} />
            ) : (
              <ShieldOff size={22} />
            )}
          </Box>
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Stack
              direction="row"
              spacing={1}
              sx={{ alignItems: 'center', flexWrap: 'wrap', rowGap: 0.5 }}
            >
              <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
                {statusLabel}
              </Typography>
              {statusNeutral ? (
                <Chip size="small" variant="outlined" label={statusChipLabel} />
              ) : (
                <Chip size="small" label={statusChipLabel} sx={tintChipSx(theme, statusTone)} />
              )}
            </Stack>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              {headerSubline}
            </Typography>
          </Box>
        </Stack>

        <Divider />

        {/* The identifiers support asks for, in mono and one click to copy. */}
        <Stack spacing={1} sx={{ px: { xs: 2, md: 3 }, py: 2 }}>
          <LicenseIdentifierRow
            label={t('licensing.instanceIdLabel')}
            value={entitlement?.instance_id ?? t('navigation.loading')}
            copyable={!!entitlement?.instance_id}
          />
          {entitlement?.license_id && (
            <LicenseIdentifierRow
              label={t('licensing.licenseIdLabel')}
              value={entitlement.license_id}
              copyable
            />
          )}
        </Stack>

        <Divider />

        {/* Everything that changes the licence lives below the line. */}
        <Stack spacing={2} sx={{ px: { xs: 2, md: 3 }, py: { xs: 2, md: 2.5 } }}>
          {entitlement?.ui_state === 'full_access_expired' && (
            <Alert severity="warning">{t('plan.fullAccessExpiredNotice')}</Alert>
          )}
          {entitlement?.last_refresh_error && (
            <Alert severity="warning">
              {t('plan.lastRefreshError', { error: entitlement.last_refresh_error })}
            </Alert>
          )}

          <Collapse in={keyEntryOpen} unmountOnExit>
            <Stack
              spacing={1.5}
              sx={{
                p: 2,
                borderRadius: 2,
                bgcolor: alpha(
                  theme.palette.text.primary,
                  theme.palette.mode === 'dark' ? 0.05 : 0.03
                ),
              }}
            >
              <TextField
                size="small"
                label={t('plan.licenseKeyLabel')}
                placeholder={t('plan.licenseKeyPlaceholder')}
                value={licenseKey}
                onChange={(event) => setLicenseKey(event.target.value)}
                disabled={isMutating}
                fullWidth
                autoFocus={replacingLicense}
              />
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={1}
                sx={{ alignItems: { xs: 'stretch', sm: 'center' } }}
              >
                <Button
                  variant="contained"
                  onClick={handleActivate}
                  disabled={isMutating}
                  sx={{ width: { xs: '100%', sm: 'auto' } }}
                  startIcon={
                    activateMutation.isPending ? (
                      <CircularProgress size={14} color="inherit" />
                    ) : (
                      <KeyRound size={16} />
                    )
                  }
                >
                  {t(
                    activePaidLicense ? 'plan.replaceLicenseButton' : 'plan.activateLicenseButton'
                  )}
                </Button>
                {activePaidLicense && (
                  <Button
                    variant="text"
                    onClick={() => {
                      setReplacingLicense(false)
                      setLicenseKey('')
                    }}
                    disabled={isMutating}
                    sx={{ width: { xs: '100%', sm: 'auto' } }}
                  >
                    {t('common.buttons.cancel')}
                  </Button>
                )}
              </Stack>
            </Stack>
          </Collapse>

          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={1}
            sx={{ alignItems: { xs: 'stretch', sm: 'center' }, flexWrap: 'wrap', rowGap: 1 }}
          >
            {!keyEntryOpen && (
              <Button
                variant="outlined"
                onClick={() => setReplacingLicense(true)}
                disabled={isMutating}
                startIcon={<KeyRound size={16} />}
                sx={{ width: { xs: '100%', sm: 'auto' } }}
              >
                {t('plan.replaceLicenseButton')}
              </Button>
            )}
            <Button
              variant="outlined"
              onClick={() => {
                trackPlan(EventAction.START, {
                  ...analyticsContext,
                  operation: 'refresh_license',
                })
                refreshMutation.mutate()
              }}
              disabled={isMutating}
              sx={{ width: { xs: '100%', sm: 'auto' } }}
              startIcon={
                refreshMutation.isPending ? (
                  <CircularProgress size={14} color="inherit" />
                ) : (
                  <RefreshCw size={16} />
                )
              }
            >
              {t('plan.refreshLicenseButton')}
            </Button>
            {activePaidLicense && (
              <Button
                variant="outlined"
                color="warning"
                onClick={handleDeactivate}
                disabled={isMutating}
                sx={{ width: { xs: '100%', sm: 'auto' } }}
                startIcon={
                  deactivateMutation.isPending ? (
                    <CircularProgress size={14} color="inherit" />
                  ) : (
                    <ShieldOff size={16} />
                  )
                }
              >
                {t('plan.deactivateLicenseButton')}
              </Button>
            )}
          </Stack>

          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            {t('plan.licenseManagementHelp')}
          </Typography>

          <Stack
            direction="row"
            spacing={2}
            sx={{ alignItems: 'center', flexWrap: 'wrap', rowGap: 1 }}
          >
            {upgradePlan && (
              <Link
                href={buildBuyUrl({ plan: upgradePlan, src: 'app-licensing' })}
                target="_blank"
                rel="noreferrer"
                underline="hover"
                sx={{ fontSize: '0.875rem', fontWeight: 600 }}
                onClick={handleBuyClick}
              >
                {t('plan.buyLink', { plan: PLAN_LABEL[upgradePlan] })}
              </Link>
            )}
            <Link
              component="button"
              underline="hover"
              onClick={() => setDrawerOpen(true)}
              sx={{ fontSize: '0.8125rem', color: 'text.secondary' }}
            >
              {t('licensing.viewPlanDetails')}
            </Link>
          </Stack>
        </Stack>
      </SettingsCard>
      {activePaidLicense && <LicenseSeatsCard />}
      <PlanInfoDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        plan={plan}
        features={features}
        entitlement={entitlement}
      />
    </Stack>
  )
}

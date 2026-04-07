import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Alert, Box, Button, CircularProgress, Stack, TextField, Typography } from '@mui/material'
import SettingsCard from './SettingsCard'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { licensingAPI } from '../services/api'
import { usePlan } from '../hooks/usePlan'
import { translateBackendKey } from '../utils/translateBackendKey'
import { useAnalytics } from '../hooks/useAnalytics'

export default function LicensingTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { plan, entitlement } = usePlan()
  const { trackPlan, EventAction } = useAnalytics()
  const [licenseKey, setLicenseKey] = useState('')

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
      trackPlan(EventAction.COMPLETE, {
        ...analyticsContext,
        operation: activePaidLicense ? 'replace_license' : 'activate_license',
        license_key_length: nextLicenseKey.length,
      })
      setLicenseKey('')
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
  const statusLabel = isFullAccess
    ? t('plan.fullAccessLabel')
    : plan === 'community'
      ? 'Community'
      : plan === 'pro'
        ? 'Pro'
        : 'Enterprise'

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

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h6" fontWeight={700}>
          {t('licensing.title')}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t('licensing.subtitle')}
        </Typography>
      </Box>
      <SettingsCard>
        <Stack spacing={2}>
          <Box>
            <Typography variant="subtitle2" fontWeight={700} gutterBottom>
              {t('licensing.currentState')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('licensing.currentPlanValue', { plan: statusLabel })}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('licensing.instanceIdValue', {
                instanceId: entitlement?.instance_id ?? t('navigation.loading'),
              })}
            </Typography>
            {entitlement?.license_id && (
              <Typography variant="body2" color="text.secondary">
                {t('licensing.licenseIdValue', { licenseId: entitlement.license_id })}
              </Typography>
            )}
            {entitlement?.expires_at && (
              <Typography variant="body2" color="text.secondary">
                {t('licensing.expiresAtValue', {
                  date: new Date(entitlement.expires_at).toLocaleDateString(),
                })}
              </Typography>
            )}
          </Box>

          {isFullAccess && (
            <Alert severity="info">
              {t('plan.fullAccessActiveNotice', {
                date: entitlement?.expires_at
                  ? new Date(entitlement.expires_at).toLocaleDateString()
                  : t('navigation.loading'),
              })}
            </Alert>
          )}
          {entitlement?.ui_state === 'full_access_expired' && (
            <Alert severity="warning">{t('plan.fullAccessExpiredNotice')}</Alert>
          )}
          {entitlement?.ui_state === 'paid_active' && (
            <Alert severity="success">{t('plan.paidActiveNotice')}</Alert>
          )}
          {entitlement?.last_refresh_error && (
            <Alert severity="warning">
              {t('plan.lastRefreshError', { error: entitlement.last_refresh_error })}
            </Alert>
          )}

          <TextField
            size="small"
            label={t('plan.licenseKeyLabel')}
            placeholder={t('plan.licenseKeyPlaceholder')}
            value={licenseKey}
            onChange={(event) => setLicenseKey(event.target.value)}
            disabled={isMutating}
            fullWidth
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
              fullWidth
              sx={{ width: { xs: '100%', sm: 'auto' } }}
              startIcon={
                activateMutation.isPending ? <CircularProgress size={14} color="inherit" /> : null
              }
            >
              {t(activePaidLicense ? 'plan.replaceLicenseButton' : 'plan.activateLicenseButton')}
            </Button>
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
              fullWidth
              sx={{ width: { xs: '100%', sm: 'auto' } }}
              startIcon={
                refreshMutation.isPending ? <CircularProgress size={14} color="inherit" /> : null
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
                fullWidth
                sx={{ width: { xs: '100%', sm: 'auto' } }}
                startIcon={
                  deactivateMutation.isPending ? (
                    <CircularProgress size={14} color="inherit" />
                  ) : null
                }
              >
                {t('plan.deactivateLicenseButton')}
              </Button>
            )}
          </Stack>

          <Typography variant="body2" color="text.secondary">
            {t('plan.licenseManagementHelp')}
          </Typography>
        </Stack>
      </SettingsCard>
    </Stack>
  )
}

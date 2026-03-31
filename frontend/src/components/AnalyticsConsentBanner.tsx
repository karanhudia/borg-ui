import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Paper, Typography, Switch, Button, FormControlLabel, Link, Stack } from '@mui/material'
import { BarChart3 } from 'lucide-react'
import { settingsAPI } from '../services/api'
import {
  PUBLIC_ANALYTICS_DASHBOARD_URL,
  resetOptOutCache,
  trackConsentResponse,
} from '../utils/analytics'

interface AnalyticsConsentBannerProps {
  onConsentGiven: () => void
}

export default function AnalyticsConsentBanner({ onConsentGiven }: AnalyticsConsentBannerProps) {
  const { t } = useTranslation()
  const [analyticsEnabled, setAnalyticsEnabled] = useState(true)
  const [saving, setSaving] = useState(false)

  const handleContinue = async () => {
    setSaving(true)
    try {
      // Track consent response BEFORE saving (so we capture the event)
      trackConsentResponse(analyticsEnabled)

      await settingsAPI.updatePreferences({
        analytics_enabled: analyticsEnabled,
        analytics_consent_given: true,
      })

      // Reset cache so tracking respects new preference
      await resetOptOutCache()

      onConsentGiven()
    } catch (error) {
      console.error('Failed to save analytics preference:', error)
      // Still close banner even if save fails
      onConsentGiven()
    }
    setSaving(false)
  }

  return (
    <Paper
      elevation={8}
      sx={{
        position: 'fixed',
        bottom: 24,
        left: '50%',
        transform: 'translateX(-50%)',
        maxWidth: 600,
        width: 'calc(100% - 48px)',
        p: 3,
        zIndex: 1300,
        borderRadius: 2,
      }}
    >
      <Stack spacing={2}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <BarChart3 size={24} />
          <Typography variant="h6" fontWeight={600}>
            {t('analyticsConsent.title')}
          </Typography>
        </Stack>

        <Typography variant="body2" color="text.secondary">
          {t('analyticsConsent.message')}
        </Typography>

        <Typography variant="body2" color="text.secondary">
          <Link
            href={PUBLIC_ANALYTICS_DASHBOARD_URL}
            target="_blank"
            rel="noopener noreferrer"
            sx={{ fontWeight: 500 }}
          >
            {t('analyticsBanner.viewDashboardLink')}
          </Link>{' '}
          {t('analyticsBanner.viewDashboardSuffix')}
        </Typography>

        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={2}
          alignItems={{ xs: 'stretch', sm: 'center' }}
          justifyContent="space-between"
        >
          <FormControlLabel
            control={
              <Switch
                checked={analyticsEnabled}
                onChange={(e) => setAnalyticsEnabled(e.target.checked)}
                disabled={saving}
              />
            }
            label={
              <Typography variant="body2" fontWeight={500}>
                {t('analyticsConsent.enableToggle')}
              </Typography>
            }
          />

          <Button
            variant="contained"
            onClick={handleContinue}
            disabled={saving}
            sx={{ minWidth: 120 }}
          >
            {saving ? t('analyticsConsent.saving') : t('analyticsConsent.continue')}
          </Button>
        </Stack>

        <Typography variant="caption" color="text.secondary">
          {t('analyticsBanner.changeAnytimeNote')}
        </Typography>
      </Stack>
    </Paper>
  )
}

import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Typography,
  Switch,
  FormControlLabel,
  Stack,
  Alert,
  CircularProgress,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
} from '@mui/material'
import { BarChart3, Info, Globe } from 'lucide-react'
import SettingsCard from './SettingsCard'
import { settingsAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { translateBackendKey } from '../utils/translateBackendKey'
import {
  PUBLIC_ANALYTICS_DASHBOARD_URL,
  resetOptOutCache,
  trackOptOut,
  trackLanguageChange,
} from '../utils/analytics'
import i18n from '../i18n'

const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'es', label: 'Español' },
  { code: 'de', label: 'Deutsch' },
  { code: 'it', label: 'Italiano' },
]

interface Preferences {
  analytics_enabled: boolean
  [key: string]: unknown
}

export default function PreferencesTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [analyticsEnabled, setAnalyticsEnabled] = useState(true)
  const [currentLanguage, setCurrentLanguage] = useState(
    localStorage.getItem('i18nextLng')?.split('-')[0] || i18n.language?.split('-')[0] || 'en'
  )

  // Fetch user preferences
  const { data: preferencesData, isLoading } = useQuery({
    queryKey: ['preferences'],
    queryFn: async () => {
      const response = await settingsAPI.getPreferences()
      return response.data
    },
  })

  // Update local state when data loads
  useEffect(() => {
    if (preferencesData?.preferences) {
      setAnalyticsEnabled(preferencesData.preferences.analytics_enabled)
    }
  }, [preferencesData])

  // Update preferences mutation
  const updatePreferencesMutation = useMutation({
    mutationFn: (preferences: Preferences) => settingsAPI.updatePreferences(preferences),
    onSuccess: async () => {
      toast.success(t('preferences.updatedSuccessfully'))
      queryClient.invalidateQueries({ queryKey: ['preferences'] })

      // Reset analytics cache so the new preference takes effect immediately
      await resetOptOutCache()

      // Reload the page to reinitialize Umami with the new preferences
      setTimeout(() => {
        window.location.reload()
      }, 500)
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('preferences.updateFailed')
      )
    },
  })

  const handleAnalyticsToggle = (checked: boolean) => {
    // Track opt-out event BEFORE saving (so we know how many users opt out)
    if (!checked) {
      trackOptOut()
    }
    setAnalyticsEnabled(checked)
    updatePreferencesMutation.mutate({ analytics_enabled: checked })
  }

  const handleLanguageChange = (langCode: string) => {
    trackLanguageChange(langCode)
    setCurrentLanguage(langCode)
    i18n.changeLanguage(langCode)
    localStorage.setItem('i18nextLng', langCode)
    toast.success(t('preferences.languageSaved'))
  }

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
        <CircularProgress />
      </Box>
    )
  }

  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h5" fontWeight={700} gutterBottom>
          {t('preferences.title')}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t('preferences.subtitle')}
        </Typography>
      </Box>

      {/* Language Section */}
      <SettingsCard sx={{ mb: 3 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="flex-start">
          <Globe size={24} />
          <Box sx={{ flex: 1 }}>
            <Typography variant="h6" fontWeight={600} gutterBottom>
              {t('preferences.languageTitle')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {t('preferences.languageDescription')}
            </Typography>
            <FormControl size="small" sx={{ width: { xs: '100%', sm: 200 } }}>
              <InputLabel>{t('preferences.languageLabel')}</InputLabel>
              <Select
                value={currentLanguage}
                label={t('preferences.languageLabel')}
                onChange={(e) => handleLanguageChange(e.target.value)}
              >
                {LANGUAGES.map((lang) => (
                  <MenuItem key={lang.code} value={lang.code}>
                    {lang.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Box>
        </Stack>
      </SettingsCard>

      {/* Analytics Section */}
      <SettingsCard sx={{ mb: 3 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="flex-start">
          <BarChart3 size={24} />
          <Box sx={{ flex: 1 }}>
            <Typography variant="h6" fontWeight={600} gutterBottom>
              {t('preferences.analyticsTitle')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {t('preferences.analyticsDescription')}
            </Typography>

            <>
              <FormControlLabel
                control={
                  <Switch
                    checked={analyticsEnabled}
                    onChange={(e) => handleAnalyticsToggle(e.target.checked)}
                    disabled={updatePreferencesMutation.isPending}
                  />
                }
                label={t('preferences.enableAnalytics')}
              />

              <Alert severity="info" icon={<Info size={20} />} sx={{ mt: 2 }}>
                <Typography variant="body2">
                  <strong>{t('preferences.analyticsTransparencyBold')}</strong>{' '}
                  <a
                    href={PUBLIC_ANALYTICS_DASHBOARD_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: 'inherit', textDecoration: 'underline' }}
                  >
                    {t('preferences.analyticsTransparencyLink')}
                  </a>{' '}
                  {t('preferences.analyticsTransparencyAfterLink')}
                </Typography>
              </Alert>
            </>
          </Box>
        </Stack>
      </SettingsCard>

      {/* Future preferences sections can be added here */}
      {/* Example:
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" spacing={2} alignItems="flex-start">
            <Bell size={24} />
            <Box sx={{ flex: 1 }}>
              <Typography variant="h6" fontWeight={600} gutterBottom>
                Notification Preferences
              </Typography>
              ...
            </Box>
          </Stack>
        </CardContent>
      </Card>
      */}
    </Box>
  )
}

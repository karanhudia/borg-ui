import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Switch,
  FormControlLabel,
  Stack,
  Alert,
  CircularProgress,
} from '@mui/material'
import { BarChart3, Info } from 'lucide-react'
import { settingsAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { resetOptOutCache } from '../utils/matomo'

interface Preferences {
  analytics_enabled: boolean
}

export default function PreferencesTab() {
  const queryClient = useQueryClient()
  const [analyticsEnabled, setAnalyticsEnabled] = useState(true)

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
      toast.success('Preferences updated successfully')
      queryClient.invalidateQueries({ queryKey: ['preferences'] })

      // Reset Matomo opt-out cache so new preference takes effect immediately
      await resetOptOutCache()

      // Reload the page to reinitialize Matomo with new preferences
      setTimeout(() => {
        window.location.reload()
      }, 500)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update preferences')
    },
  })

  const handleAnalyticsToggle = (checked: boolean) => {
    setAnalyticsEnabled(checked)
    updatePreferencesMutation.mutate({ analytics_enabled: checked })
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
          Preferences
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Customize your experience and manage your privacy settings
        </Typography>
      </Box>

      {/* Analytics Section */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" spacing={2} alignItems="flex-start">
            <BarChart3 size={24} />
            <Box sx={{ flex: 1 }}>
              <Typography variant="h6" fontWeight={600} gutterBottom>
                Anonymous Usage Analytics
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Help us improve Borg UI by sharing anonymous usage data. We collect page views,
                feature clicks, and browser type—without tracking IP addresses, hostnames, cookies,
                or any personally identifiable information.
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
                  label="Enable analytics"
                />

                <Alert severity="info" icon={<Info size={20} />} sx={{ mt: 2 }}>
                  <Typography variant="body2">
                    <strong>Full Transparency:</strong>{' '}
                    <a
                      href="https://analytics.nullcodeai.dev/"
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: 'inherit', textDecoration: 'underline' }}
                    >
                      View our analytics dashboard publicly
                    </a>{' '}
                    to see exactly what we collect. Self-hosted, no third parties.
                  </Typography>
                </Alert>
              </>
            </Box>
          </Stack>
        </CardContent>
      </Card>

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

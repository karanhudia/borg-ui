import { useTranslation } from 'react-i18next'
import { Box, Typography, Stack, Chip } from '@mui/material'
import SettingsCard from './SettingsCard'
import { alpha } from '@mui/material/styles'
import { Moon, Sun, Monitor } from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'
import { useTheme } from '../context/ThemeContext'
import { availableThemes } from '../theme'

export default function AppearanceTab() {
  const { t } = useTranslation()
  const { trackSettings, EventAction } = useAnalytics()
  const { mode, effectiveMode, setTheme } = useTheme()

  const appearanceAccent =
    effectiveMode === 'dark' ? '#60a5fa' : mode === 'auto' ? '#0891b2' : '#2563eb'

  return (
    <Box>
      <Box>
        <Typography variant="h6" fontWeight={600} gutterBottom>
          {t('settings.appearance.title')}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          {t('settings.appearance.subtitle')}
        </Typography>
      </Box>
      <SettingsCard sx={{ maxWidth: 600 }}>
        <Stack spacing={2.5}>
          <Stack direction="row" spacing={2} alignItems="center">
            <Box
              sx={{
                width: 42,
                height: 42,
                borderRadius: 2,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                bgcolor: alpha(appearanceAccent, 0.14),
                color: appearanceAccent,
                flexShrink: 0,
              }}
            >
              {mode === 'auto' ? (
                <Monitor size={22} />
              ) : effectiveMode === 'dark' ? (
                <Moon size={22} />
              ) : (
                <Sun size={22} />
              )}
            </Box>
            <Box>
              <Typography variant="subtitle1" fontWeight={700}>
                {t('settings.appearance.theme')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t('settings.appearance.chooseTheme')}
              </Typography>
            </Box>
          </Stack>

          <Chip
            size="small"
            label={
              mode === 'auto'
                ? t('settings.appearance.autoStatus', {
                    theme: t(`settings.appearance.themeOptions.${effectiveMode}`),
                  })
                : t('settings.appearance.activeTheme', {
                    theme: t(`settings.appearance.themeOptions.${mode}`),
                  })
            }
            sx={{
              alignSelf: 'flex-start',
              bgcolor: alpha(appearanceAccent, 0.12),
              color: appearanceAccent,
              border: `1px solid ${alpha(appearanceAccent, 0.24)}`,
              fontWeight: 600,
            }}
          />

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' },
              gap: 1.5,
            }}
          >
            {availableThemes.map((themeOption) => {
              const isSelected = mode === themeOption.id
              const Icon =
                themeOption.icon === 'Sun' ? Sun : themeOption.icon === 'Moon' ? Moon : Monitor
              const previewIsDark =
                themeOption.id === 'dark' || (themeOption.id === 'auto' && effectiveMode === 'dark')

              return (
                <Box
                  key={themeOption.id}
                  role="button"
                  tabIndex={0}
                  aria-label={`${t('settings.appearance.themeAriaLabel')}: ${t(themeOption.labelKey)}`}
                  onClick={() => {
                    const theme = themeOption.id as typeof mode
                    setTheme(theme)
                    trackSettings(EventAction.EDIT, {
                      section: 'appearance',
                      setting: 'theme',
                      theme,
                    })
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      const theme = themeOption.id as typeof mode
                      setTheme(theme)
                      trackSettings(EventAction.EDIT, {
                        section: 'appearance',
                        setting: 'theme',
                        theme,
                      })
                    }
                  }}
                  sx={{
                    p: 1.5,
                    borderRadius: 3,
                    border: '1px solid',
                    borderColor: isSelected ? appearanceAccent : 'divider',
                    bgcolor: isSelected ? alpha(appearanceAccent, 0.08) : 'background.paper',
                    cursor: 'pointer',
                    transition: 'all 0.18s ease',
                    boxShadow: isSelected ? `0 10px 24px ${alpha(appearanceAccent, 0.16)}` : 'none',
                    '&:hover': {
                      borderColor: isSelected ? appearanceAccent : 'text.primary',
                      transform: 'translateY(-1px)',
                    },
                    '&:focus-visible': {
                      outline: `2px solid ${appearanceAccent}`,
                      outlineOffset: 2,
                    },
                  }}
                >
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.25 }}>
                    <Box
                      sx={{
                        width: 32,
                        height: 32,
                        borderRadius: 1.5,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        bgcolor: previewIsDark ? '#0f172a' : alpha(appearanceAccent, 0.12),
                        color: previewIsDark ? '#cbd5e1' : appearanceAccent,
                        border: `1px solid ${previewIsDark ? '#334155' : alpha(appearanceAccent, 0.18)}`,
                      }}
                    >
                      <Icon size={16} />
                    </Box>
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="subtitle2" fontWeight={700}>
                        {t(themeOption.labelKey)}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {t(`settings.appearance.themeDescriptions.${themeOption.id}`)}
                      </Typography>
                    </Box>
                  </Stack>

                  <Box
                    sx={{
                      p: 1,
                      borderRadius: 2,
                      bgcolor: previewIsDark ? '#0f172a' : '#f8fafc',
                      border: `1px solid ${previewIsDark ? '#1e293b' : '#e2e8f0'}`,
                    }}
                  >
                    <Stack direction="row" spacing={0.75} sx={{ mb: 0.9 }}>
                      <Box
                        sx={{
                          width: 24,
                          height: 54,
                          borderRadius: 1.5,
                          bgcolor: previewIsDark ? '#111827' : '#ffffff',
                          border: `1px solid ${previewIsDark ? '#1f2937' : '#e2e8f0'}`,
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          gap: 0.4,
                          py: 0.75,
                        }}
                      >
                        <Box
                          sx={{
                            width: 10,
                            height: 10,
                            borderRadius: '50%',
                            bgcolor: previewIsDark
                              ? alpha('#60a5fa', 0.75)
                              : alpha(appearanceAccent, 0.75),
                          }}
                        />
                        <Box
                          sx={{
                            width: 8,
                            height: 8,
                            borderRadius: 1,
                            bgcolor: previewIsDark ? '#334155' : '#dbe4ee',
                          }}
                        />
                        <Box
                          sx={{
                            width: 8,
                            height: 8,
                            borderRadius: 1,
                            bgcolor: previewIsDark ? '#334155' : '#dbe4ee',
                          }}
                        />
                      </Box>

                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Box
                          sx={{
                            height: 12,
                            borderRadius: 999,
                            mb: 0.8,
                            width: '46%',
                            bgcolor: previewIsDark ? '#334155' : '#cbd5e1',
                          }}
                        />

                        <Stack direction="row" spacing={0.75} sx={{ mb: 0.75 }}>
                          <Box
                            sx={{
                              flex: 1.1,
                              height: 24,
                              borderRadius: 1.5,
                              bgcolor: previewIsDark ? '#111827' : '#ffffff',
                              border: `1px solid ${previewIsDark ? '#1f2937' : '#dbe4ee'}`,
                              boxShadow: previewIsDark
                                ? 'none'
                                : '0 1px 2px rgba(15, 23, 42, 0.06)',
                            }}
                          />
                          <Box
                            sx={{
                              width: 20,
                              height: 24,
                              borderRadius: 1.5,
                              bgcolor: previewIsDark
                                ? alpha('#60a5fa', 0.18)
                                : alpha(appearanceAccent, 0.14),
                              border: `1px solid ${
                                previewIsDark
                                  ? alpha('#60a5fa', 0.16)
                                  : alpha(appearanceAccent, 0.12)
                              }`,
                            }}
                          />
                        </Stack>

                        <Stack direction="row" spacing={0.6}>
                          {[0, 1, 2].map((index) => (
                            <Box
                              key={index}
                              sx={{
                                flex: 1,
                                height: index === 1 ? 16 : 14,
                                borderRadius: 1.25,
                                bgcolor: previewIsDark ? '#172033' : '#ffffff',
                                border: `1px solid ${previewIsDark ? '#1f2937' : '#dbe4ee'}`,
                              }}
                            />
                          ))}
                        </Stack>
                      </Box>
                    </Stack>

                    <Box
                      sx={{
                        height: 18,
                        borderRadius: 1.5,
                        bgcolor: previewIsDark ? '#111827' : '#ffffff',
                        border: `1px solid ${previewIsDark ? '#1f2937' : '#dbe4ee'}`,
                        display: 'flex',
                        alignItems: 'center',
                        px: 0.9,
                        gap: 0.5,
                      }}
                    >
                      <Box
                        sx={{
                          width: 16,
                          height: 16,
                          borderRadius: '50%',
                          bgcolor: previewIsDark
                            ? alpha('#60a5fa', 0.22)
                            : alpha(appearanceAccent, 0.18),
                        }}
                      />
                      <Box
                        sx={{
                          height: 6,
                          width: '42%',
                          borderRadius: 999,
                          bgcolor: previewIsDark ? '#334155' : '#cbd5e1',
                        }}
                      />
                    </Box>
                  </Box>
                </Box>
              )
            })}
          </Box>
        </Stack>
      </SettingsCard>
    </Box>
  )
}

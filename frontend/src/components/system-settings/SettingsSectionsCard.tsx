import type { ReactNode } from 'react'
import { Box, Divider, Stack, Tab, Tabs, Tooltip, Typography } from '@mui/material'
import { AlertTriangle, Clock, Info, Key, RefreshCw, Settings } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import SettingsCard from '../SettingsCard'
import type { SectionTabConfig } from './types'

interface SettingsSectionsCardProps {
  activeSection: number
  sectionTabs: SectionTabConfig[]
  onActiveSectionChange: (value: number) => void
  children: ReactNode
}

const tabIcons = [
  <Clock key="timeouts" size={15} />,
  <RefreshCw key="monitoring" size={15} />,
  <Key key="metrics" size={15} />,
  <AlertTriangle key="browsing" size={15} />,
  <Settings key="proxy" size={15} />,
  <Key key="oidc" size={15} />,
]

const headingIcons = [
  <Clock key="timeouts" size={22} />,
  <RefreshCw key="monitoring" size={22} />,
  <Settings key="metrics" size={22} />,
  <AlertTriangle key="browsing" size={22} />,
  <Settings key="proxy" size={22} />,
  <Key key="oidc" size={22} />,
]

const SettingsSectionsCard: React.FC<SettingsSectionsCardProps> = ({
  activeSection,
  sectionTabs,
  onActiveSectionChange,
  children,
}) => {
  const { t } = useTranslation()

  return (
    <SettingsCard sx={{ overflow: 'hidden' }} contentSx={{ p: 0 }}>
      <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Tabs
          value={activeSection}
          onChange={(_, value) => onActiveSectionChange(value)}
          variant="scrollable"
          scrollButtons="auto"
          allowScrollButtonsMobile
          sx={{ px: { xs: 1, md: 2 } }}
        >
          {sectionTabs.map((section, index) => (
            <Tab
              key={section.label}
              label={section.label}
              icon={tabIcons[index]}
              iconPosition="start"
              sx={{ minHeight: 48, gap: 0.5, textTransform: 'none', fontWeight: 600 }}
            />
          ))}
        </Tabs>
      </Box>

      <Box sx={{ p: { xs: 2, md: 2.5 } }}>
        <Stack spacing={3}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {headingIcons[activeSection]}
            <Typography variant="h6">{sectionTabs[activeSection].label}</Typography>
            {activeSection === 1 && (
              <Tooltip title={t('systemSettings.manualRefreshAlert')} placement="right">
                <Box
                  component="span"
                  sx={{ display: 'inline-flex', color: 'info.main', cursor: 'help', ml: 0.5 }}
                >
                  <Info size={16} />
                </Box>
              </Tooltip>
            )}
            {activeSection === 2 && (
              <Tooltip title={t('systemSettings.metricsHeaderHelp')} placement="right">
                <Box
                  component="span"
                  sx={{ display: 'inline-flex', color: 'info.main', cursor: 'help', ml: 0.5 }}
                >
                  <Info size={16} />
                </Box>
              </Tooltip>
            )}
            {activeSection === 3 && (
              <Tooltip
                title={
                  <>
                    <strong>{t('systemSettings.warningLabel')}</strong>{' '}
                    {t('systemSettings.largeLimitsWarning')}
                  </>
                }
                placement="right"
              >
                <Box
                  component="span"
                  sx={{ display: 'inline-flex', color: 'warning.main', cursor: 'help', ml: 0.5 }}
                >
                  <AlertTriangle size={16} />
                </Box>
              </Tooltip>
            )}
          </Box>

          <Typography variant="body2" color="text.secondary">
            {sectionTabs[activeSection].description}
          </Typography>

          <Divider />

          {children}
        </Stack>
      </Box>
    </SettingsCard>
  )
}

export default SettingsSectionsCard

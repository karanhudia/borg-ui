import { Box, Typography, Tooltip } from '@mui/material'
import { Info } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import VersionChip from './VersionChip'

interface SystemInfo {
  app_version: string
  borg_version: string | null
  borg2_version: string | null
}

interface SidebarVersionInfoProps {
  systemInfo: SystemInfo | null
}

export default function SidebarVersionInfo({ systemInfo }: SidebarVersionInfoProps) {
  const { t } = useTranslation()

  return (
    <Box sx={{ mt: 'auto', px: 2, py: 1.5, borderTop: 1, borderColor: 'divider' }}>
      <Tooltip title={t('layout.systemInformation')} arrow placement="right">
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 1 }}>
          <Info size={13} style={{ color: '#555', flexShrink: 0 }} />
          <Typography
            variant="caption"
            sx={{
              fontWeight: 600,
              fontSize: '0.65rem',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'text.disabled',
            }}
          >
            {t('navigation.versionInfo')}
          </Typography>
        </Box>
      </Tooltip>
      {systemInfo ? (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
          <VersionChip label="UI" version={systemInfo.app_version} />
          {systemInfo.borg_version && (
            <VersionChip
              label="B1"
              version={systemInfo.borg_version.replace(/^borg\s*/i, '')}
            />
          )}
          {systemInfo.borg2_version && (
            <VersionChip
              label="B2"
              version={systemInfo.borg2_version.replace(/^borg2\s*/i, '')}
              accent
            />
          )}
        </Box>
      ) : (
        <Typography variant="caption" display="block" color="text.secondary">
          {t('navigation.loading')}
        </Typography>
      )}
    </Box>
  )
}

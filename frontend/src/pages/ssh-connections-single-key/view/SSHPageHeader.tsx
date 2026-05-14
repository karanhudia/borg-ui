import type { TFunction } from 'i18next'
import { Box, Tooltip, Typography } from '@mui/material'
import { Info } from 'lucide-react'

interface SSHPageHeaderProps {
  t: TFunction
}

export function SSHPageHeader({ t }: SSHPageHeaderProps) {
  return (
    <Box sx={{ mb: 4 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
        <Typography variant="h4" fontWeight={600}>
          {t('sshConnections.title')}
        </Typography>
        <Tooltip
          title={
            <Box>
              <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
                {t('sshConnections.singleKeySystem.title')}
              </Typography>
              <Typography variant="body2">
                {t('sshConnections.singleKeySystem.description')}
              </Typography>
            </Box>
          }
          arrow
        >
          <Info
            size={16}
            style={{ color: 'inherit', opacity: 0.45, cursor: 'help', flexShrink: 0 }}
          />
        </Tooltip>
      </Box>
      <Typography variant="body2" color="text.secondary">
        {t('sshConnections.subtitle')}
      </Typography>
    </Box>
  )
}

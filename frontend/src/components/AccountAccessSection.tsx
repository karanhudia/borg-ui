import { Box, Stack, Typography } from '@mui/material'
import { ShieldCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import ApiTokensSection from './ApiTokensSection'
import UserPermissionsPanel from './UserPermissionsPanel'

interface AccountAccessSectionProps {
  hasGlobalRepositoryAccess: boolean
}

export default function AccountAccessSection({
  hasGlobalRepositoryAccess,
}: AccountAccessSectionProps) {
  const { t } = useTranslation()

  return (
    <Stack spacing={3}>
      <Box>
        <Stack direction="row" spacing={1.25} alignItems="center" sx={{ mb: 1 }}>
          <ShieldCheck size={16} style={{ opacity: 0.6 }} />
          <Typography variant="subtitle1" fontWeight={700}>
            {t('settings.account.access.title')}
          </Typography>
        </Stack>
        <Typography variant="body2" color="text.secondary">
          {t('settings.account.access.description')}
        </Typography>
      </Box>
      <ApiTokensSection />
      {!hasGlobalRepositoryAccess ? (
        <UserPermissionsPanel
          title={t('settings.account.access.permissions.title')}
          subtitle={t('settings.account.access.permissions.subtitle')}
        />
      ) : (
        <Box
          sx={{
            px: 2.5,
            py: 2,
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 2.5,
            display: 'flex',
            alignItems: 'center',
            gap: 1.5,
            bgcolor: 'action.hover',
          }}
        >
          <ShieldCheck size={16} style={{ color: '#f87171', flexShrink: 0 }} />
          <Box>
            <Typography variant="body2" fontWeight={700}>
              {t('settings.account.access.globalAccess.title')}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t('settings.account.access.globalAccess.description')}
            </Typography>
          </Box>
        </Box>
      )}
    </Stack>
  )
}

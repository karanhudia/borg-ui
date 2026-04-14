import { Box, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'

export default function AccountTabHeader() {
  const { t } = useTranslation()

  return (
    <Box>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        {t('settings.account.title')}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {t('settings.account.description')}
      </Typography>
    </Box>
  )
}

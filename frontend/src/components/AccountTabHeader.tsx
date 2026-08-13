import { Box, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'

export default function AccountTabHeader() {
  const { t } = useTranslation()

  return (
    <Box>
      <Typography
        variant="h5"
        gutterBottom
        sx={{
          fontWeight: 700,
        }}
      >
        {t('settings.account.title')}
      </Typography>
      <Typography
        variant="body2"
        sx={{
          color: 'text.secondary',
        }}
      >
        {t('settings.account.description')}
      </Typography>
    </Box>
  )
}

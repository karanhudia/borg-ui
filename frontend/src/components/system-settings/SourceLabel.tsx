import { Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'

export function SourceLabel({ source }: { source: string | null | undefined }) {
  const { t } = useTranslation()

  if (source === 'saved') {
    return (
      <Typography
        component="span"
        sx={{ color: 'success.main', fontSize: '0.7rem', fontWeight: 500 }}
      >
        {' '}
        {t('systemSettings.sourceCustomized')}
      </Typography>
    )
  }

  if (source === 'env') {
    return (
      <Typography
        component="span"
        sx={{ color: 'warning.main', fontSize: '0.7rem', fontWeight: 500 }}
      >
        {' '}
        {t('systemSettings.sourceFromEnv')}
      </Typography>
    )
  }

  return (
    <Typography component="span" sx={{ color: 'info.main', fontSize: '0.7rem', fontWeight: 500 }}>
      {' '}
      {t('systemSettings.sourceDefault')}
    </Typography>
  )
}

import { Skeleton, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'

import AppTemplateSelect from '../../app-templates/AppTemplateSelect'
import { useAppTemplates } from '../../app-templates/appTemplates'
import { appPatch, type QuickStartStepProps } from '../quickStartState'

export default function QuickStartAppStep({ answers, onChange }: QuickStartStepProps) {
  const { t } = useTranslation()
  const { templates, loading } = useAppTemplates()
  return (
    <Stack spacing={2}>
      <Typography variant="h6" component="h3">
        {t('quickStart.app.title')}
      </Typography>
      {loading ? (
        <Skeleton variant="rounded" height={56} />
      ) : (
        <AppTemplateSelect
          templates={templates}
          value={answers.app}
          onChange={(app) => onChange(appPatch(answers, app))}
          allowNone
        />
      )}
      <Typography variant="body2" sx={{ color: 'text.secondary' }}>
        {t('quickStart.app.hint')}
      </Typography>
    </Stack>
  )
}

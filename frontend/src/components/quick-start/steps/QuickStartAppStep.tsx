import { Skeleton, Stack, Typography } from '@mui/material'
import { AppWindow, FolderOpen } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useAppTemplates } from '../../app-templates/appTemplates'
import QuickStartChoiceCard from '../QuickStartChoiceCard'
import { appPatch, type QuickStartStepProps } from '../quickStartState'

export default function QuickStartAppStep({ answers, onChange }: QuickStartStepProps) {
  const { t } = useTranslation()
  const { templates, loading } = useAppTemplates()
  return (
    <Stack spacing={2}>
      <Typography variant="h6" component="h3">
        {t('quickStart.app.title')}
      </Typography>
      <Stack spacing={1.5} role="radiogroup" aria-label={t('quickStart.app.title')}>
        {loading && <Skeleton variant="rounded" height={72} />}
        {templates.map((template) => (
          <QuickStartChoiceCard
            key={template.id}
            icon={<AppWindow size={20} />}
            title={template.name}
            description={template.description}
            selected={answers.app?.id === template.id}
            onSelect={() => onChange(appPatch(answers, template))}
          />
        ))}
        <QuickStartChoiceCard
          icon={<FolderOpen size={20} />}
          title={t('quickStart.app.other')}
          description={t('quickStart.app.otherDesc')}
          selected={answers.app === null}
          onSelect={() => onChange(appPatch(answers, null))}
        />
      </Stack>
      <Typography variant="body2" sx={{ color: 'text.secondary' }}>
        {t('quickStart.app.hint')}
      </Typography>
    </Stack>
  )
}

import { Skeleton, Stack, Typography } from '@mui/material'
import { AppWindow, FolderOpen } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import AppTemplateSelect from '../../app-templates/AppTemplateSelect'
import { useAppTemplates } from '../../app-templates/appTemplates'
import QuickStartChoiceCard from '../QuickStartChoiceCard'
import { appPatch, type QuickStartStepProps } from '../quickStartState'

export default function QuickStartAppStep({ answers, onChange }: QuickStartStepProps) {
  const { t } = useTranslation()
  const { templates, loading } = useAppTemplates()
  const choosingApp = answers.appChoice === 'app'
  return (
    <Stack spacing={2}>
      <Typography variant="h6" component="h3">
        {t('quickStart.app.title')}
      </Typography>
      <Stack spacing={1.5} role="radiogroup" aria-label={t('quickStart.app.title')}>
        <QuickStartChoiceCard
          icon={<FolderOpen size={20} />}
          title={t('quickStart.app.other')}
          description={t('quickStart.app.otherDesc')}
          selected={!choosingApp}
          onSelect={() => onChange({ appChoice: 'folders', ...appPatch(answers, null) })}
        />
        <QuickStartChoiceCard
          icon={<AppWindow size={20} />}
          title={t('quickStart.app.pickApp')}
          description={t('quickStart.app.pickAppDesc')}
          selected={choosingApp}
          onSelect={() => onChange({ appChoice: 'app' })}
        />
      </Stack>
      {/* Below both cards, so revealing it moves nothing above. */}
      {choosingApp &&
        (loading ? (
          <Skeleton variant="rounded" height={56} />
        ) : (
          <AppTemplateSelect
            templates={templates}
            value={answers.app}
            onChange={(app) => onChange(appPatch(answers, app))}
          />
        ))}
      <Typography variant="body2" sx={{ color: 'text.secondary' }}>
        {t('quickStart.app.hint')}
      </Typography>
    </Stack>
  )
}

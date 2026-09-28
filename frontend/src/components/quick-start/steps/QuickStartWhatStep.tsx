import { Stack, Typography } from '@mui/material'
import { Laptop, Lock, Monitor, Server } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import QuickStartChoiceCard from '../QuickStartChoiceCard'
import { sourceKindPatch, type QuickStartStepProps } from '../quickStartState'

interface QuickStartWhatStepProps extends QuickStartStepProps {
  /** managed_agents plan feature. */
  canUseAgents?: boolean
}

export default function QuickStartWhatStep({
  answers,
  onChange,
  canUseAgents = false,
}: QuickStartWhatStepProps) {
  const { t } = useTranslation()
  return (
    <Stack spacing={2}>
      <Typography variant="h6" component="h3">
        {t('quickStart.what.title')}
      </Typography>
      <Stack spacing={1.5} role="radiogroup" aria-label={t('quickStart.what.title')}>
        <QuickStartChoiceCard
          icon={<Server size={20} />}
          title={t('quickStart.what.server')}
          description={t('quickStart.what.serverDesc')}
          selected={answers.sourceKind === 'server'}
          onSelect={() => onChange(sourceKindPatch(answers, 'server'))}
        />
        <QuickStartChoiceCard
          icon={<Monitor size={20} />}
          title={t('quickStart.what.ssh')}
          description={t('quickStart.what.sshDesc')}
          selected={answers.sourceKind === 'ssh'}
          onSelect={() => onChange(sourceKindPatch(answers, 'ssh'))}
        />
        <QuickStartChoiceCard
          icon={canUseAgents ? <Laptop size={20} /> : <Lock size={20} />}
          title={t('quickStart.what.agent')}
          description={
            canUseAgents ? t('quickStart.what.agentDesc') : t('quickStart.what.agentPro')
          }
          disabled={!canUseAgents}
          selected={answers.sourceKind === 'agent'}
          onSelect={() => onChange(sourceKindPatch(answers, 'agent'))}
        />
      </Stack>
      <Typography variant="body2" sx={{ color: 'text.secondary' }}>
        {t('quickStart.what.notSure')}
      </Typography>
    </Stack>
  )
}

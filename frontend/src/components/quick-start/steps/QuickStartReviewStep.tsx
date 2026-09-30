import type { ReactNode } from 'react'
import { Box, Stack, Typography, useTheme } from '@mui/material'
import { useTranslation } from 'react-i18next'

import { getWizardStepColor } from '../../shared/wizardStepColors'
import {
  ReviewAttrRow,
  ReviewCodePill,
  ReviewSectionCard,
  ReviewSectionGrid,
  ReviewStatus,
} from '../../wizard/WizardReviewComponents'
import QuickStartCustomize from '../QuickStartCustomize'
import { appScriptPayload } from '../quickStartActions'
import { STEP_META } from '../quickStartStepMeta'
import { agentLabel, useManagedAgent } from '../quickStartAgent'
import { useSshConnection } from '../quickStartSsh'
import type {
  QuickStartAnswers,
  QuickStartSettingsChange,
  QuickStartStepKey,
} from '../quickStartState'

// Value text sized like the other wizard reviews.
function Value({ children }: { children: ReactNode }) {
  return (
    <Typography component="span" sx={{ fontSize: '0.75rem', fontWeight: 500, textAlign: 'right' }}>
      {children}
    </Typography>
  )
}

interface QuickStartReviewStepProps {
  answers: QuickStartAnswers
  onSettingsChange: QuickStartSettingsChange
  canUseBorg2: boolean
}

export default function QuickStartReviewStep({
  answers,
  onSettingsChange,
  canUseBorg2,
}: QuickStartReviewStepProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  // Each card wears the color and icon of the step its answers came from.
  const card = (step: QuickStartStepKey) => {
    const { colorKey, icon: Icon } = STEP_META[step]
    return {
      icon: <Icon size={15} />,
      accentColor: getWizardStepColor(colorKey, theme.palette.mode),
    }
  }
  const { settings } = answers
  const prune = settings.prune
  const sourceConnection = useSshConnection(
    answers.sourceKind === 'ssh' ? answers.sourceConnectionId : ''
  )
  const destinationConnection = useSshConnection(
    answers.destinationKind === 'ssh' ? answers.destinationConnectionId : ''
  )
  const agent = useManagedAgent(answers.sourceKind === 'agent' ? answers.sourceAgentId : '')
  const machine = (connection?: { username: string; host: string }) =>
    connection
      ? `${connection.username}@${connection.host}`
      : agent
        ? agentLabel(agent)
        : t('quickStart.review.thisServer')
  const keep = (
    [
      ['keepHourly', prune.keepHourly],
      ['keepDaily', prune.keepDaily],
      ['keepWeekly', prune.keepWeekly],
      ['keepMonthly', prune.keepMonthly],
      ['keepQuarterly', prune.keepQuarterly],
      ['keepYearly', prune.keepYearly],
    ] as const
  )
    .filter(([, count]) => count > 0)
    .map(([key, count]) => t(`quickStart.review.keep.${key}`, { count }))
  const maintenance = [
    settings.runPruneAfter && t('quickStart.review.maintenance.prune'),
    settings.runCompactAfter && t('quickStart.review.maintenance.compact'),
    settings.runCheckAfter && t('quickStart.review.maintenance.check'),
  ].filter(Boolean)
  const schedule = !settings.scheduleEnabled
    ? t('quickStart.review.manualOnly')
    : answers.schedulePreset === 'custom'
      ? `${answers.cronExpression} (${answers.timezone})`
      : `${t(`quickStart.schedule.presets.${answers.schedulePreset}`)} (${answers.timezone})`
  const encrypted = settings.encryption !== 'none'

  return (
    <Stack spacing={2.5}>
      <Box>
        <Typography variant="h6" component="h3">
          {t('quickStart.review.title')}
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
          {t('quickStart.review.hint')}
        </Typography>
      </Box>

      <ReviewSectionGrid>
        <ReviewSectionCard label={t('quickStart.review.backUp')} {...card('folders')}>
          {answers.sourcePaths.map((path) => (
            <ReviewCodePill key={path} block>
              {path}
            </ReviewCodePill>
          ))}
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            {t('quickStart.review.onMachine', { machine: machine(sourceConnection) })}
          </Typography>
          {answers.app && answers.appExcludes.length > 0 && (
            <ReviewAttrRow label={t('quickStart.review.skips')}>
              <Value>{answers.appExcludes.map((path) => `${path}/`).join(', ')}</Value>
            </ReviewAttrRow>
          )}
          {appScriptPayload(answers) && (
            <ReviewAttrRow label={t('quickStart.review.checksFirst')}>
              <Value>{answers.app?.pre_backup_script?.name}</Value>
            </ReviewAttrRow>
          )}
        </ReviewSectionCard>

        <ReviewSectionCard label={t('quickStart.review.storeIn')} {...card('destination')}>
          <ReviewCodePill block>{answers.destinationPath}</ReviewCodePill>
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            {t('quickStart.review.onMachine', { machine: machine(destinationConnection) })}
          </Typography>
        </ReviewSectionCard>

        <ReviewSectionCard label={t('quickStart.review.encryption')} {...card('protect')}>
          <ReviewStatus
            enabled={encrypted}
            tone={encrypted ? 'success' : 'warning'}
            label={
              encrypted
                ? t('quickStart.review.encrypted', { mode: settings.encryption })
                : t('quickStart.review.unencrypted')
            }
          />
        </ReviewSectionCard>

        <ReviewSectionCard
          label={t('quickStart.review.schedule')}
          {...card('schedule')}
          trailing={
            settings.scheduleEnabled ? undefined : (
              <ReviewStatus enabled={false} label={t('quickStart.review.manualOnly')} />
            )
          }
        >
          {settings.scheduleEnabled && (
            <ReviewAttrRow label={t('quickStart.steps.schedule')}>
              <Value>{schedule}</Value>
            </ReviewAttrRow>
          )}
          <ReviewAttrRow label={t('quickStart.review.keepLabel')}>
            <Value>
              {settings.runPruneAfter && keep.length
                ? keep.join(', ')
                : t('quickStart.review.keepAll')}
            </Value>
          </ReviewAttrRow>
          <ReviewAttrRow label={t('quickStart.review.afterEachRun')}>
            <Value>
              {maintenance.length ? maintenance.join(', ') : t('quickStart.review.nothing')}
            </Value>
          </ReviewAttrRow>
        </ReviewSectionCard>
      </ReviewSectionGrid>

      <Typography variant="body2" sx={{ color: 'text.secondary' }}>
        {t('quickStart.review.creates')}:{' '}
        <Typography component="span" variant="body2" sx={{ color: 'text.primary' }}>
          {t('quickStart.review.createsList', { name: answers.name.trim() })}
        </Typography>
      </Typography>

      <QuickStartCustomize
        answers={answers}
        onSettingsChange={onSettingsChange}
        canUseBorg2={canUseBorg2}
      />
    </Stack>
  )
}

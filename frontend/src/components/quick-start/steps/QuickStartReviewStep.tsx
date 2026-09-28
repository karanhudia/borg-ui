import type { ReactNode } from 'react'
import { Box, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'

import QuickStartCustomize from '../QuickStartCustomize'
import { agentLabel, useManagedAgent } from '../quickStartAgent'
import { useSshConnection } from '../quickStartSsh'
import type { QuickStartAnswers, QuickStartSettingsChange } from '../quickStartState'

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', sm: '140px 1fr' },
        gap: { xs: 0.25, sm: 2 },
        py: 1.25,
        borderBottom: 1,
        borderColor: 'divider',
        '&:last-of-type': { borderBottom: 0 },
      }}
    >
      <Typography variant="body2" sx={{ color: 'text.secondary' }}>
        {label}
      </Typography>
      <Typography variant="body2" component="div" sx={{ minWidth: 0, overflowWrap: 'anywhere' }}>
        {children}
      </Typography>
    </Box>
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

      <Box>
        <Row label={t('quickStart.review.backUp')}>
          {answers.sourcePaths.map((path) => (
            <Box key={path} component="span" sx={{ display: 'block', fontFamily: 'monospace' }}>
              {path}
            </Box>
          ))}
          <Box component="span" sx={{ color: 'text.secondary' }}>
            {t('quickStart.review.onMachine', { machine: machine(sourceConnection) })}
          </Box>
        </Row>
        <Row label={t('quickStart.review.storeIn')}>
          <Box component="span" sx={{ fontFamily: 'monospace' }}>
            {answers.destinationPath}
          </Box>
          <Box component="span" sx={{ display: 'block', color: 'text.secondary' }}>
            {t('quickStart.review.onMachine', { machine: machine(destinationConnection) })}
          </Box>
        </Row>
        <Row label={t('quickStart.review.schedule')}>{schedule}</Row>
        <Row label={t('quickStart.review.keepLabel')}>
          {settings.runPruneAfter && keep.length ? keep.join(', ') : t('quickStart.review.keepAll')}
        </Row>
        <Row label={t('quickStart.review.afterEachRun')}>
          {maintenance.length ? maintenance.join(', ') : t('quickStart.review.nothing')}
        </Row>
        <Row label={t('quickStart.review.encryption')}>
          {settings.encryption === 'none'
            ? t('quickStart.review.unencrypted')
            : t('quickStart.review.encrypted', { mode: settings.encryption })}
        </Row>
        <Row label={t('quickStart.review.creates')}>
          {t('quickStart.review.createsList', { name: answers.name.trim() })}
        </Row>
      </Box>

      <QuickStartCustomize
        answers={answers}
        onSettingsChange={onSettingsChange}
        canUseBorg2={canUseBorg2}
      />
    </Stack>
  )
}

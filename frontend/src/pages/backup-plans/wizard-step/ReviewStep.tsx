import { Box, Stack, Typography } from '@mui/material'
import {
  CalendarClock,
  Code,
  Database,
  HardDrive,
  Laptop,
  ListChecks,
  Settings,
  Wrench,
} from 'lucide-react'

import {
  ReviewAttrRow,
  ReviewCodePill,
  ReviewCount,
  ReviewKicker,
  ReviewSectionCard,
  ReviewSectionGrid,
  ReviewStatus,
} from '../../../components/wizard/WizardReviewComponents'
import type { Repository } from '../../../types'
import { formatSshConnectionLabel, getPathBasename } from './helpers'
import type { BackupPlanWizardStepProps } from './types'

const REVIEW_BLUE = '#3b82f6'
const REVIEW_VIOLET = '#8b5cf6'
const REVIEW_EMERALD = '#10b981'

type ReviewStepProps = Pick<
  BackupPlanWizardStepProps,
  'wizardState' | 'repositories' | 'selectedSourceConnection' | 'scripts' | 't'
>

export function ReviewStep({
  wizardState,
  repositories,
  selectedSourceConnection,
  scripts,
  t,
}: ReviewStepProps) {
  const sourceLocationLabel =
    wizardState.sourceType === 'remote'
      ? t('backupPlans.wizard.review.remoteSource')
      : wizardState.sourceType === 'mixed'
        ? t('backupPlans.sourceChooser.mixedSources')
        : t('backupPlans.wizard.review.localSource')
  const sourceConnectionLabel = selectedSourceConnection
    ? formatSshConnectionLabel(selectedSourceConnection)
    : wizardState.sourceSshConnectionId
      ? t('backupPlans.wizard.review.connectionFallback', {
          id: wizardState.sourceSshConnectionId,
        })
      : t('backupPlans.wizard.review.notSet')
  const prePlanScript = scripts.find((script) => script.id === wizardState.preBackupScriptId)
  const postPlanScript = scripts.find((script) => script.id === wizardState.postBackupScriptId)
  const selectedRepositories = wizardState.repositoryIds
    .map((repositoryId) => repositories.find((repository) => repository.id === repositoryId))
    .filter((repository): repository is Repository => Boolean(repository))
  const visibleSourceDirectories = wizardState.sourceDirectories.slice(0, 6)
  const hiddenSourceDirectoryCount = Math.max(
    wizardState.sourceDirectories.length - visibleSourceDirectories.length,
    0
  )
  const visibleExcludePatterns = wizardState.excludePatterns.slice(0, 4)
  const hiddenExcludePatternCount = Math.max(
    wizardState.excludePatterns.length - visibleExcludePatterns.length,
    0
  )
  const retentionLabel = t('backupPlans.wizard.review.retentionValue', {
    hourly: wizardState.pruneKeepHourly,
    daily: wizardState.pruneKeepDaily,
    weekly: wizardState.pruneKeepWeekly,
    monthly: wizardState.pruneKeepMonthly,
    quarterly: wizardState.pruneKeepQuarterly,
    yearly: wizardState.pruneKeepYearly,
  })

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <ReviewKicker>{t('backupPlans.wizard.steps.review')}</ReviewKicker>

      <ReviewSectionGrid>
        <ReviewSectionCard
          icon={<ListChecks size={14} />}
          label={t('backupPlans.wizard.review.plan')}
          accentColor={REVIEW_BLUE}
        >
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.25 }}>
            <Typography
              variant="body2"
              sx={{
                fontWeight: 700,
                fontSize: '0.95rem',
                lineHeight: 1.3,
                color: 'text.primary',
                wordBreak: 'break-word',
              }}
            >
              {wizardState.name}
            </Typography>
            {wizardState.description && (
              <Typography
                variant="body2"
                sx={{
                  fontSize: '0.75rem',
                  color: 'text.secondary',
                  lineHeight: 1.45,
                }}
              >
                {wizardState.description}
              </Typography>
            )}
          </Box>

          <ReviewAttrRow label={t('backupPlans.wizard.review.sourceLocation')}>
            <Stack direction="row" spacing={0.5} alignItems="center" sx={{ minWidth: 0 }}>
              {wizardState.sourceType === 'remote' || wizardState.sourceType === 'mixed' ? (
                <Laptop size={12} style={{ opacity: 0.6, flexShrink: 0 }} />
              ) : (
                <HardDrive size={12} style={{ opacity: 0.6, flexShrink: 0 }} />
              )}
              <Typography variant="body2" fontSize="0.75rem" noWrap>
                {sourceLocationLabel}
              </Typography>
            </Stack>
          </ReviewAttrRow>

          {wizardState.sourceType === 'remote' && (
            <ReviewAttrRow label={t('backupPlans.wizard.review.sourceConnection')}>
              <Typography variant="body2" fontSize="0.75rem" fontWeight={500} noWrap>
                {sourceConnectionLabel}
              </Typography>
            </ReviewAttrRow>
          )}

          <Box
            sx={{
              display: 'flex',
              flexDirection: 'column',
              gap: 0.5,
              minWidth: 0,
            }}
          >
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 1,
              }}
            >
              <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: '0.7rem' }}>
                {t('backupPlans.wizard.review.sources')}
              </Typography>
              <ReviewCount>
                {t('backupPlans.wizard.review.pathCount', {
                  count: wizardState.sourceDirectories.length,
                })}
              </ReviewCount>
            </Box>
            <Box
              sx={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 0.5,
                minWidth: 0,
              }}
            >
              {visibleSourceDirectories.map((sourcePath) => (
                <ReviewCodePill key={sourcePath} tooltip={sourcePath} maxChars={22}>
                  {getPathBasename(sourcePath)}
                </ReviewCodePill>
              ))}
              {hiddenSourceDirectoryCount > 0 && (
                <ReviewCount>
                  {t('repositories.moreCount', { count: hiddenSourceDirectoryCount })}
                </ReviewCount>
              )}
            </Box>
          </Box>

          {visibleExcludePatterns.length > 0 && (
            <Box
              sx={{
                display: 'flex',
                flexDirection: 'column',
                gap: 0.5,
                minWidth: 0,
              }}
            >
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 1,
                }}
              >
                <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: '0.7rem' }}>
                  {t('wizard.review.excludePatterns')}
                </Typography>
                <ReviewCount>{wizardState.excludePatterns.length}</ReviewCount>
              </Box>
              <Box
                sx={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: 0.5,
                  minWidth: 0,
                }}
              >
                {visibleExcludePatterns.map((pattern) => (
                  <ReviewCodePill key={pattern} maxChars={22}>
                    {pattern}
                  </ReviewCodePill>
                ))}
                {hiddenExcludePatternCount > 0 && (
                  <ReviewCount>
                    {t('repositories.moreCount', { count: hiddenExcludePatternCount })}
                  </ReviewCount>
                )}
              </Box>
            </Box>
          )}
        </ReviewSectionCard>

        <ReviewSectionCard
          icon={<Database size={14} />}
          label={t('backupPlans.wizard.review.repositories')}
          accentColor={REVIEW_BLUE}
          trailing={
            wizardState.repositoryIds.length > 1 ? (
              <ReviewCount>{wizardState.repositoryIds.length}</ReviewCount>
            ) : undefined
          }
        >
          <Box
            sx={{
              display: 'flex',
              flexDirection: 'column',
              gap: 0.5,
              minWidth: 0,
            }}
          >
            {selectedRepositories.map((repository) => (
              <Box
                key={repository.id}
                sx={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 0.125,
                  minWidth: 0,
                }}
              >
                <Typography
                  variant="body2"
                  sx={{
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    color: 'text.primary',
                    lineHeight: 1.35,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                  title={repository.name}
                >
                  {repository.name}
                </Typography>
                <Typography
                  variant="caption"
                  sx={{
                    fontFamily: 'monospace',
                    fontSize: '0.68rem',
                    color: 'text.disabled',
                    lineHeight: 1.4,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                  title={repository.path}
                >
                  {repository.path}
                </Typography>
              </Box>
            ))}
          </Box>
        </ReviewSectionCard>

        <ReviewSectionCard
          icon={<Settings size={14} />}
          label={t('backupPlans.wizard.steps.settings')}
          accentColor={REVIEW_VIOLET}
        >
          <ReviewAttrRow label={t('backupPlans.wizard.fields.archiveNameTemplate')}>
            <ReviewCodePill maxChars={28}>{wizardState.archiveNameTemplate}</ReviewCodePill>
          </ReviewAttrRow>
          <ReviewAttrRow label={t('backupPlans.wizard.review.compression')}>
            <ReviewCodePill>{wizardState.compression}</ReviewCodePill>
          </ReviewAttrRow>
          {wizardState.customFlags && (
            <ReviewAttrRow label={t('backupPlans.wizard.review.customFlags')}>
              <ReviewCodePill maxChars={28}>{wizardState.customFlags}</ReviewCodePill>
            </ReviewAttrRow>
          )}
          {wizardState.uploadRatelimitMb && (
            <ReviewAttrRow label={t('backupPlans.wizard.fields.uploadSpeedLimit')}>
              <ReviewCodePill>{wizardState.uploadRatelimitMb} MB/s</ReviewCodePill>
            </ReviewAttrRow>
          )}
          <ReviewAttrRow label={t('backupPlans.wizard.review.runMode')}>
            <Typography
              component="span"
              sx={{
                fontSize: '0.72rem',
                fontWeight: 600,
                color: 'text.primary',
                lineHeight: 1.4,
              }}
            >
              {wizardState.repositoryRunMode === 'parallel'
                ? t('backupPlans.status.parallel')
                : t('backupPlans.status.series')}
            </Typography>
          </ReviewAttrRow>
          {wizardState.repositoryRunMode === 'parallel' && (
            <ReviewAttrRow label={t('backupPlans.wizard.fields.maxParallelRepositories')}>
              <ReviewCodePill>{wizardState.maxParallelRepositories}</ReviewCodePill>
            </ReviewAttrRow>
          )}
        </ReviewSectionCard>

        <ReviewSectionCard
          icon={<Code size={14} />}
          label={t('backupPlans.wizard.steps.scripts')}
          accentColor={REVIEW_VIOLET}
        >
          <ReviewAttrRow label={t('backupPlans.wizard.review.planPreScript')}>
            <Typography
              variant="body2"
              fontSize="0.75rem"
              fontWeight={prePlanScript ? 600 : 400}
              color={prePlanScript ? 'text.primary' : 'text.disabled'}
            >
              {prePlanScript?.name || t('backupPlans.wizard.review.noScript')}
            </Typography>
          </ReviewAttrRow>
          <ReviewAttrRow label={t('backupPlans.wizard.review.planPostScript')}>
            <Typography
              variant="body2"
              fontSize="0.75rem"
              fontWeight={postPlanScript ? 600 : 400}
              color={postPlanScript ? 'text.primary' : 'text.disabled'}
            >
              {postPlanScript?.name || t('backupPlans.wizard.review.noScript')}
            </Typography>
          </ReviewAttrRow>
          <ReviewAttrRow label={t('backupPlans.wizard.review.repositoryScripts')}>
            <ReviewStatus
              enabled={wizardState.runRepositoryScripts}
              label={wizardState.runRepositoryScripts ? t('common.enabled') : t('common.disabled')}
            />
          </ReviewAttrRow>
        </ReviewSectionCard>

        <ReviewSectionCard
          icon={<CalendarClock size={14} />}
          label={t('backupPlans.wizard.steps.schedule')}
          accentColor={REVIEW_EMERALD}
          trailing={
            <ReviewStatus
              enabled={wizardState.scheduleEnabled}
              label={
                wizardState.scheduleEnabled
                  ? t('common.enabled')
                  : t('backupPlans.status.manualOnly')
              }
            />
          }
        >
          {wizardState.scheduleEnabled ? (
            <>
              <ReviewAttrRow label={t('backupPlans.wizard.fields.cronExpression')}>
                <ReviewCodePill>{wizardState.cronExpression}</ReviewCodePill>
              </ReviewAttrRow>
              <ReviewAttrRow label={t('backupPlans.wizard.fields.timezone')}>
                <ReviewCodePill maxChars={20}>{wizardState.timezone}</ReviewCodePill>
              </ReviewAttrRow>
            </>
          ) : (
            <Typography
              variant="caption"
              sx={{
                fontSize: '0.72rem',
                color: 'text.disabled',
                lineHeight: 1.5,
              }}
            >
              {t('backupPlans.wizard.review.manualOnlyHint', {
                defaultValue: 'Runs only when triggered manually.',
              })}
            </Typography>
          )}
        </ReviewSectionCard>

        <ReviewSectionCard
          icon={<Wrench size={14} />}
          label={t('backupPlans.wizard.maintenance.title')}
          accentColor={REVIEW_EMERALD}
        >
          <ReviewAttrRow label={t('backupPlans.wizard.review.prune')}>
            <ReviewStatus
              enabled={wizardState.runPruneAfter}
              label={wizardState.runPruneAfter ? t('common.enabled') : t('common.disabled')}
            />
          </ReviewAttrRow>
          {wizardState.runPruneAfter && (
            <ReviewAttrRow label={t('backupPlans.wizard.review.retention')}>
              <ReviewCodePill>{retentionLabel}</ReviewCodePill>
            </ReviewAttrRow>
          )}
          <ReviewAttrRow label={t('backupPlans.wizard.review.compact')}>
            <ReviewStatus
              enabled={wizardState.runCompactAfter}
              label={wizardState.runCompactAfter ? t('common.enabled') : t('common.disabled')}
            />
          </ReviewAttrRow>
          <ReviewAttrRow label={t('backupPlans.wizard.review.check')}>
            <ReviewStatus
              enabled={wizardState.runCheckAfter}
              label={
                wizardState.runCheckAfter
                  ? t('backupPlans.wizard.review.checkDuration', {
                      seconds: wizardState.checkMaxDuration,
                    })
                  : t('common.disabled')
              }
            />
          </ReviewAttrRow>
        </ReviewSectionCard>
      </ReviewSectionGrid>
    </Box>
  )
}

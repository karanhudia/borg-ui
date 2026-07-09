import { Alert, Box, Stack, Typography } from '@mui/material'
import {
  CalendarClock,
  Code,
  Container as ContainerIcon,
  Database,
  HardDrive,
  Laptop,
  ListChecks,
  Settings,
  Wrench,
} from 'lucide-react'

import {
  ReviewAttrRow,
  ReviewAttrStack,
  ReviewCodePill,
  ReviewCount,
  ReviewKicker,
  ReviewSectionCard,
  ReviewSectionGrid,
  ReviewStatus,
} from '../../../components/wizard/WizardReviewComponents'
import type { Repository, SourceLocation } from '../../../types'
import { buildRoutePreviews, routeExecutorLabelKey } from '../routePreview'
import { formatSshConnectionLabel, getPathBasename } from './helpers'
import type { BackupPlanWizardStepProps } from './types'

const REVIEW_BLUE = '#3b82f6'
const REVIEW_VIOLET = '#8b5cf6'
const REVIEW_EMERALD = '#10b981'

type ReviewStepProps = Pick<
  BackupPlanWizardStepProps,
  'wizardState' | 'repositories' | 'agentMachines' | 'selectedSourceConnection' | 'scripts' | 't'
>

export function ReviewStep({
  wizardState,
  repositories,
  agentMachines,
  selectedSourceConnection,
  scripts,
  t,
}: ReviewStepProps) {
  const sourceLocationLabel =
    wizardState.sourceType === 'agent'
      ? t('backupPlans.sourceChooser.managedAgent')
      : wizardState.sourceType === 'remote'
        ? t('backupPlans.wizard.review.remoteSource')
        : wizardState.sourceType === 'mixed'
          ? t('backupPlans.sourceChooser.mixedSources')
          : t('backupPlans.sourceChooser.borgUiServer')
  const sourceConnectionLabel = selectedSourceConnection
    ? formatSshConnectionLabel(selectedSourceConnection)
    : wizardState.sourceSshConnectionId
      ? t('backupPlans.wizard.review.connectionFallback', {
          id: wizardState.sourceSshConnectionId,
        })
      : t('backupPlans.wizard.review.notSet')
  const planScriptHooks = wizardState.scriptHooks || []
  const prePlanScripts = planScriptHooks
    .filter((hook) => hook.hook_type === 'pre-backup' && hook.enabled !== false)
    .sort((left, right) => left.execution_order - right.execution_order)
  const postPlanScripts = planScriptHooks
    .filter((hook) => hook.hook_type === 'post-backup' && hook.enabled !== false)
    .sort((left, right) => left.execution_order - right.execution_order)
  const scriptName = (scriptId: number) =>
    scripts.find((script) => script.id === scriptId)?.name || `Script #${scriptId}`
  const hookLabel = (hook: (typeof planScriptHooks)[number]) =>
    hook.agent_script_name
      ? `${hook.agent_script_name} (${t('backupPlans.wizard.scripts.agentScriptBadge')})`
      : scriptName(Number(hook.script_id))
  const selectedRepositories = wizardState.repositoryIds
    .map((repositoryId) => repositories.find((repository) => repository.id === repositoryId))
    .filter((repository): repository is Repository => Boolean(repository))
  const routePreviews = buildRoutePreviews(selectedRepositories, wizardState, agentMachines)
  const routePreviewByRepositoryId = new Map(
    routePreviews.map((preview) => [preview.repository.id, preview])
  )
  const sourceLocations = wizardState.sourceLocations || []
  const databaseSourceLocations = sourceLocations.filter((location) => Boolean(location.database))
  const containerSourceLocations = sourceLocations.filter((location) => Boolean(location.container))
  const hasDatabaseSourceLocations = databaseSourceLocations.length > 0
  const hasContainerSourceLocations = containerSourceLocations.length > 0
  const hasStructuredSourceLocations = hasDatabaseSourceLocations || hasContainerSourceLocations
  const fileSourceDirectories = hasStructuredSourceLocations
    ? sourceLocations
        .filter((location) => !location.database && !location.container)
        .flatMap((location) => location.paths)
    : wizardState.sourceDirectories
  const visibleDatabaseSourceLocations = databaseSourceLocations.slice(0, 4)
  const visibleContainerSourceLocations = containerSourceLocations.slice(0, 4)
  const hiddenDatabaseSourceCount = Math.max(
    databaseSourceLocations.length - visibleDatabaseSourceLocations.length,
    0
  )
  const hiddenContainerSourceCount = Math.max(
    containerSourceLocations.length - visibleContainerSourceLocations.length,
    0
  )
  const visibleSourceDirectories = fileSourceDirectories.slice(0, 6)
  const hiddenSourceDirectoryCount = Math.max(
    fileSourceDirectories.length - visibleSourceDirectories.length,
    0
  )
  const visibleExcludePatterns = wizardState.excludePatterns.slice(0, 4)
  const hiddenExcludePatternCount = Math.max(
    wizardState.excludePatterns.length - visibleExcludePatterns.length,
    0
  )
  const uploadPolicies = wizardState.uploadRatelimitSchedulePolicies || []
  const pruneKeepWithin = wizardState.pruneKeepWithin?.trim() ?? ''
  const retentionLabel = t(
    pruneKeepWithin
      ? 'backupPlans.wizard.review.retentionValueWithWithin'
      : 'backupPlans.wizard.review.retentionValue',
    {
      hourly: wizardState.pruneKeepHourly,
      daily: wizardState.pruneKeepDaily,
      weekly: wizardState.pruneKeepWeekly,
      monthly: wizardState.pruneKeepMonthly,
      quarterly: wizardState.pruneKeepQuarterly,
      yearly: wizardState.pruneKeepYearly,
      within: pruneKeepWithin,
    }
  )

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
              {hasStructuredSourceLocations ? (
                <Stack spacing={0.75} sx={{ width: '100%', minWidth: 0 }}>
                  {visibleDatabaseSourceLocations.map((location, index) => (
                    <DatabaseSourceReviewItem
                      key={`${location.source_type}:${location.source_ssh_connection_id || 'local'}:${location.database?.template_id || index}`}
                      location={location}
                      t={t}
                    />
                  ))}
                  {hiddenDatabaseSourceCount > 0 && (
                    <ReviewCount>
                      {t('repositories.moreCount', { count: hiddenDatabaseSourceCount })}
                    </ReviewCount>
                  )}
                  {visibleContainerSourceLocations.map((location, index) => (
                    <ContainerSourceReviewItem
                      key={`${location.source_type}:${location.source_ssh_connection_id || 'local'}:${location.container?.container_name || index}`}
                      location={location}
                      t={t}
                    />
                  ))}
                  {hiddenContainerSourceCount > 0 && (
                    <ReviewCount>
                      {t('repositories.moreCount', { count: hiddenContainerSourceCount })}
                    </ReviewCount>
                  )}
                  {visibleSourceDirectories.length > 0 && (
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, minWidth: 0 }}>
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
                  )}
                </Stack>
              ) : (
                <>
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
                </>
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
            {selectedRepositories.map((repository) => {
              const routePreview = routePreviewByRepositoryId.get(repository.id)
              return (
                <Box
                  key={repository.id}
                  sx={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 0.375,
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
                  {routePreview &&
                    (routePreview.supported ? (
                      <Typography variant="caption" color="text.secondary">
                        {t(routeExecutorLabelKey(routePreview.executor))}
                      </Typography>
                    ) : (
                      <Alert severity="warning" sx={{ py: 0, px: 1 }}>
                        {t(routePreview.messageKey || '', routePreview.messageParams)}
                      </Alert>
                    ))}
                </Box>
              )
            })}
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
          {uploadPolicies.length > 0 && (
            <ReviewAttrStack label={t('backupPlans.wizard.review.scheduledUploadLimits')}>
              {uploadPolicies.map((policy, index) => (
                <Box
                  key={`${policy.label}-${policy.startTime}-${policy.endTime}-${index}`}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 1,
                    minWidth: 0,
                  }}
                >
                  <Box sx={{ minWidth: 0 }}>
                    <Typography
                      variant="body2"
                      sx={{
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: 'text.primary',
                        lineHeight: 1.35,
                      }}
                    >
                      {policy.label}
                    </Typography>
                    <Typography
                      variant="caption"
                      sx={{ color: 'text.secondary', fontSize: '0.68rem' }}
                    >
                      {policy.startTime}-{policy.endTime}
                    </Typography>
                  </Box>
                  <ReviewCodePill>
                    {policy.uploadRatelimitMb
                      ? t('backupPlans.wizard.review.uploadPolicyLimit', {
                          limit: policy.uploadRatelimitMb,
                        })
                      : t('backupPlans.wizard.review.uploadPolicyUnlimited')}
                  </ReviewCodePill>
                </Box>
              ))}
            </ReviewAttrStack>
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
              fontWeight={prePlanScripts.length > 0 ? 600 : 400}
              color={prePlanScripts.length > 0 ? 'text.primary' : 'text.disabled'}
            >
              {prePlanScripts.length > 0
                ? prePlanScripts.map((hook) => hookLabel(hook)).join(', ')
                : t('backupPlans.wizard.review.noScript')}
            </Typography>
          </ReviewAttrRow>
          <ReviewAttrRow label={t('backupPlans.wizard.review.planPostScript')}>
            <Typography
              variant="body2"
              fontSize="0.75rem"
              fontWeight={postPlanScripts.length > 0 ? 600 : 400}
              color={postPlanScripts.length > 0 ? 'text.primary' : 'text.disabled'}
            >
              {postPlanScripts.length > 0
                ? postPlanScripts.map((hook) => hookLabel(hook)).join(', ')
                : t('backupPlans.wizard.review.noScript')}
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
          {wizardState.runCheckAfter && wizardState.checkExtraFlags.trim() && (
            <ReviewAttrRow label={t('backupPlans.wizard.review.checkExtraFlags')}>
              <ReviewCodePill>{wizardState.checkExtraFlags.trim()}</ReviewCodePill>
            </ReviewAttrRow>
          )}
        </ReviewSectionCard>
      </ReviewSectionGrid>
    </Box>
  )
}

function DatabaseSourceReviewItem({
  location,
  t,
}: {
  location: SourceLocation
  t: ReviewStepProps['t']
}) {
  const database = location.database
  if (!database) return null

  const livePath = database.detected_source_path?.trim()
  const backupPaths = database.backup_paths?.filter((path) => path.trim().length > 0) || []
  const backupPathLabel = (backupPaths.length > 0 ? backupPaths : location.paths).join(', ')

  return (
    <Box
      sx={{
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 1,
        bgcolor: 'background.paper',
        display: 'flex',
        flexDirection: 'column',
        gap: 0.6,
        minWidth: 0,
        px: 1,
        py: 0.85,
      }}
    >
      <Typography
        variant="body2"
        sx={{
          color: 'text.primary',
          fontSize: '0.78rem',
          fontWeight: 700,
          lineHeight: 1.35,
        }}
      >
        {database.display_name}
      </Typography>
      {livePath && (
        <ReviewDatabasePath
          label={t('backupPlans.sourceChooser.databaseLivePath')}
          value={livePath}
        />
      )}
      <ReviewDatabasePath
        label={t('backupPlans.sourceChooser.databaseBackupPaths')}
        value={backupPathLabel}
      />
    </Box>
  )
}

function ContainerSourceReviewItem({
  location,
  t,
}: {
  location: SourceLocation
  t: ReviewStepProps['t']
}) {
  const container = location.container
  if (!container) return null

  return (
    <Box
      sx={{
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 1,
        bgcolor: 'background.paper',
        display: 'flex',
        flexDirection: 'column',
        gap: 0.6,
        minWidth: 0,
        px: 1,
        py: 0.85,
      }}
    >
      <Stack direction="row" spacing={0.75} alignItems="center" sx={{ minWidth: 0 }}>
        <ContainerIcon size={12} style={{ opacity: 0.7, flexShrink: 0 }} />
        <Typography
          variant="caption"
          sx={{
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 0.75,
            color: 'text.secondary',
            flexShrink: 0,
            fontSize: '0.68rem',
            fontWeight: 700,
            lineHeight: 1.35,
            px: 0.55,
            py: 0.1,
          }}
        >
          {t('backupPlans.sourceChooser.containerTitle')}
        </Typography>
        <Typography
          variant="body2"
          sx={{
            color: 'text.primary',
            fontSize: '0.78rem',
            fontWeight: 700,
            lineHeight: 1.35,
            minWidth: 0,
          }}
          noWrap
          title={container.display_name}
        >
          {container.display_name}
        </Typography>
        {container.image && (
          <Typography
            variant="caption"
            color="text.secondary"
            noWrap
            title={container.image}
            sx={{ minWidth: 0 }}
          >
            {container.image}
          </Typography>
        )}
      </Stack>
      <ReviewDatabasePath
        label={t('backupPlans.sourceChooser.containerBackupPath')}
        value={container.export_path || location.paths.join(', ')}
      />
    </Box>
  )
}

function ReviewDatabasePath({ label, value }: { label: string; value: string }) {
  return (
    <ReviewAttrStack label={label}>
      <ReviewCodePill tooltip={value} maxChars={38}>
        {value}
      </ReviewCodePill>
    </ReviewAttrStack>
  )
}

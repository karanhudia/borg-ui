import React from 'react'
import { useTranslation } from 'react-i18next'
import { Box, Typography, Chip, Tooltip, useTheme, alpha } from '@mui/material'
import { Calendar, Code, Wrench, Rocket, Database } from 'lucide-react'
import { Repository } from '../../../types'
import { Script } from '../../ScheduleWizard'

interface WizardStepScheduleReviewProps {
  data: {
    name: string
    description: string
    repositoryIds: number[]
    cronExpression: string
    archiveNameTemplate: string
    preBackupScriptId: number | null
    postBackupScriptId: number | null
    runRepositoryScripts: boolean
    runPruneAfter: boolean
    runCompactAfter: boolean
    pruneKeepHourly: number
    pruneKeepDaily: number
    pruneKeepWeekly: number
    pruneKeepMonthly: number
    pruneKeepQuarterly: number
    pruneKeepYearly: number
  }
  repositories: Repository[]
  scripts: Script[]
}

const BLUE = '#3b82f6'
const VIOLET = '#8b5cf6'
const EMERALD = '#10b981'
const AMBER = '#f59e0b'

function IconBadge({ icon, accentColor }: { icon: React.ReactNode; accentColor: string }) {
  const theme = useTheme()
  return (
    <Box
      sx={{
        width: 28,
        height: 28,
        borderRadius: '8px',
        bgcolor: alpha(accentColor, theme.palette.mode === 'dark' ? 0.2 : 0.15),
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: accentColor,
        flexShrink: 0,
      }}
    >
      {icon}
    </Box>
  )
}

function CodePill({ children }: { children: React.ReactNode }) {
  const theme = useTheme()
  return (
    <Tooltip title={children} placement="top">
      <Typography
        component="span"
        sx={{
          fontFamily: 'monospace',
          fontSize: '0.72rem',
          px: 0.75,
          py: 0.15,
          borderRadius: '4px',
          bgcolor: alpha(theme.palette.text.primary, theme.palette.mode === 'dark' ? 0.08 : 0.06),
          color: 'text.primary',
          maxWidth: '100%',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          display: 'inline-block',
          verticalAlign: 'middle',
          cursor: 'default',
          lineHeight: 1.6,
        }}
      >
        {children}
      </Typography>
    </Tooltip>
  )
}

function AttrRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 1,
        minWidth: 0,
      }}
    >
      <Typography
        variant="caption"
        sx={{ color: 'text.disabled', fontSize: '0.7rem', flexShrink: 0 }}
      >
        {label}
      </Typography>
      <Box
        sx={{
          minWidth: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 0.5,
          flexWrap: 'wrap',
          justifyContent: 'flex-end',
        }}
      >
        {children}
      </Box>
    </Box>
  )
}

function SectionCard({
  icon,
  label,
  accentColor,
  children,
}: {
  icon: React.ReactNode
  label: string
  accentColor: string
  children: React.ReactNode
}) {
  const theme = useTheme()
  return (
    <Box
      sx={{
        borderRadius: 2,
        bgcolor: alpha(accentColor, theme.palette.mode === 'dark' ? 0.07 : 0.05),
        p: 1.5,
        display: 'flex',
        flexDirection: 'column',
        gap: 1.25,
        minWidth: 0,
        overflow: 'hidden',
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <IconBadge icon={icon} accentColor={accentColor} />
        <Typography
          variant="caption"
          sx={{
            color: 'text.secondary',
            fontWeight: 700,
            fontSize: '0.68rem',
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
          }}
        >
          {label}
        </Typography>
      </Box>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.6 }}>{children}</Box>
    </Box>
  )
}

const WizardStepScheduleReview: React.FC<WizardStepScheduleReviewProps> = ({
  data,
  repositories,
  scripts,
}) => {
  const { t } = useTranslation()

  const selectedRepos = repositories.filter((r) => data.repositoryIds.includes(r.id))
  const preScript = scripts.find((s) => s.id === data.preBackupScriptId)
  const postScript = scripts.find((s) => s.id === data.postBackupScriptId)

  const pruneKeeps = [
    data.pruneKeepHourly > 0 && `${data.pruneKeepHourly}h`,
    `${data.pruneKeepDaily}d`,
    `${data.pruneKeepWeekly}w`,
    `${data.pruneKeepMonthly}m`,
    data.pruneKeepQuarterly > 0 && `${data.pruneKeepQuarterly}q`,
    `${data.pruneKeepYearly}y`,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography
          variant="caption"
          sx={{
            color: 'text.disabled',
            fontWeight: 700,
            fontSize: '0.6rem',
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
          }}
        >
          {t('wizard.scheduleWizard.review.jobSummary')}
        </Typography>
        <Tooltip title={t('wizard.scheduleWizard.review.readyToCreate')} placement="top" arrow>
          <Chip
            icon={<Rocket size={11} />}
            label={t('wizard.scheduleWizard.review.readyToCreate')}
            size="small"
            sx={{
              height: 20,
              fontSize: '0.65rem',
              fontWeight: 600,
              bgcolor: alpha(EMERALD, 0.1),
              color: EMERALD,
              border: `1px solid ${alpha(EMERALD, 0.25)}`,
              cursor: 'help',
              '& .MuiChip-icon': { color: EMERALD, ml: '6px' },
              '& .MuiChip-label': { px: '8px' },
            }}
          />
        </Tooltip>
      </Box>

      {/* 2-column grid */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' },
          gap: 1.25,
          minWidth: 0,
          overflow: 'hidden',
        }}
      >
        {/* Job card */}
        <SectionCard
          icon={<Calendar size={14} />}
          label={t('wizard.scheduleWizard.review.name')}
          accentColor={BLUE}
        >
          <AttrRow label={t('wizard.scheduleWizard.review.name')}>
            <Typography variant="body2" fontWeight={700} fontSize="0.8rem">
              {data.name}
            </Typography>
          </AttrRow>
          {data.description && (
            <AttrRow label={t('wizard.scheduleWizard.steps.basicInfo') || 'Description'}>
              <Typography
                variant="body2"
                fontSize="0.75rem"
                color="text.secondary"
                sx={{ textAlign: 'right' }}
              >
                {data.description}
              </Typography>
            </AttrRow>
          )}
          <AttrRow label={t('wizard.scheduleWizard.review.schedule')}>
            <CodePill>{data.cronExpression}</CodePill>
          </AttrRow>
          <AttrRow label={t('wizard.scheduleWizard.review.archiveNameTemplate')}>
            <CodePill>{data.archiveNameTemplate}</CodePill>
          </AttrRow>
        </SectionCard>

        {/* Repositories card */}
        <SectionCard
          icon={<Database size={14} />}
          label={t('wizard.scheduleWizard.review.repositories', { count: selectedRepos.length })}
          accentColor={AMBER}
        >
          {selectedRepos.length === 0 ? (
            <Typography variant="body2" fontSize="0.75rem" color="text.secondary">
              None selected
            </Typography>
          ) : (
            selectedRepos.map((repo) => (
              <AttrRow key={repo.id} label={repo.name}>
                <CodePill>{repo.path}</CodePill>
              </AttrRow>
            ))
          )}
        </SectionCard>

        {/* Scripts card */}
        <SectionCard
          icon={<Code size={14} />}
          label={t('wizard.scheduleWizard.review.scriptsConfiguration')}
          accentColor={VIOLET}
        >
          <AttrRow label={t('wizard.scheduleWizard.review.preBackupScript')}>
            {preScript ? (
              <Typography variant="body2" fontSize="0.75rem" fontWeight={500}>
                {preScript.name}
              </Typography>
            ) : (
              <Typography variant="body2" fontSize="0.75rem" color="text.disabled">
                —
              </Typography>
            )}
          </AttrRow>
          <AttrRow label={t('wizard.scheduleWizard.review.postBackupScript')}>
            {postScript ? (
              <Typography variant="body2" fontSize="0.75rem" fontWeight={500}>
                {postScript.name}
              </Typography>
            ) : (
              <Typography variant="body2" fontSize="0.75rem" color="text.disabled">
                —
              </Typography>
            )}
          </AttrRow>
          <AttrRow label={t('wizard.scheduleWizard.review.repositoryLevelScripts')}>
            <Chip
              label={
                data.runRepositoryScripts
                  ? t('wizard.scheduleWizard.review.enabled')
                  : t('wizard.scheduleWizard.review.disabled')
              }
              color={data.runRepositoryScripts ? 'primary' : 'default'}
              size="small"
              sx={{ height: 17, fontSize: '0.62rem', fontWeight: 600 }}
            />
          </AttrRow>
        </SectionCard>

        {/* Maintenance card */}
        <SectionCard
          icon={<Wrench size={14} />}
          label={t('wizard.scheduleWizard.review.maintenanceSettings')}
          accentColor={EMERALD}
        >
          <AttrRow label={t('wizard.scheduleWizard.review.pruneAfterBackup')}>
            <Chip
              label={
                data.runPruneAfter
                  ? t('wizard.scheduleWizard.review.enabled')
                  : t('wizard.scheduleWizard.review.disabled')
              }
              color={data.runPruneAfter ? 'success' : 'default'}
              size="small"
              sx={{ height: 17, fontSize: '0.62rem', fontWeight: 600 }}
            />
          </AttrRow>
          {data.runPruneAfter && (
            <AttrRow label="Keep">
              <CodePill>{pruneKeeps}</CodePill>
            </AttrRow>
          )}
          <AttrRow label={t('wizard.scheduleWizard.review.compactAfterPrune')}>
            <Chip
              label={
                data.runCompactAfter
                  ? t('wizard.scheduleWizard.review.enabled')
                  : t('wizard.scheduleWizard.review.disabled')
              }
              color={data.runCompactAfter ? 'success' : 'default'}
              size="small"
              sx={{ height: 17, fontSize: '0.62rem', fontWeight: 600 }}
            />
          </AttrRow>
        </SectionCard>
      </Box>
    </Box>
  )
}

export default WizardStepScheduleReview

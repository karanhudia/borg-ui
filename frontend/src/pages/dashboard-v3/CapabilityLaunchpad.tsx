import { Box, Stack, Typography } from '@mui/material'
import { alpha } from '@mui/material/styles'
import { ArrowRight, Cloud, ListChecks, Server, ShieldCheck, type LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useT } from './tokens'
import type { DashboardOverview } from './types'

type LaunchpadRoute =
  | '/backup-plans'
  | '/cloud-storage'
  | '/remote-clients'
  | '/schedule/restore-checks'
type LaunchpadSource = 'backup_plans' | 'cloud_storage' | 'remote_clients' | 'restore_verification'

type LaunchpadCard = {
  key: LaunchpadSource
  title: string
  value: string
  status: string
  route: LaunchpadRoute
  color: string
  icon: LucideIcon
  ariaLabel: string
}

function pluralKey(baseKey: string, count: number) {
  return `${baseKey}_${count === 1 ? 'one' : 'other'}`
}

export function CapabilityLaunchpad({
  summary,
  repositories,
  cloudRemoteCount = 0,
  remoteClientCount = 0,
  onNavigate,
}: {
  summary: DashboardOverview['summary']
  repositories: DashboardOverview['repository_health']
  cloudRemoteCount?: number
  remoteClientCount?: number
  onNavigate: (route: LaunchpadRoute, source: LaunchpadSource) => void
}) {
  const T = useT()
  const { t } = useTranslation()
  const backupPlanCount = summary.total_backup_plans ?? summary.total_schedules
  const activeBackupPlanCount = summary.active_backup_plans ?? summary.active_schedules
  const restoreConfiguredCount = repositories.filter(
    (repository) => repository.restore_check_configured
  ).length
  const repositoryCount = repositories.length

  const cards: LaunchpadCard[] = [
    {
      key: 'backup_plans',
      title: t('dashboard.launchpad.backupPlans.title'),
      value: t(pluralKey('dashboard.launchpad.backupPlans.value', backupPlanCount), {
        count: backupPlanCount,
      }),
      status:
        backupPlanCount > 0
          ? t(pluralKey('dashboard.launchpad.backupPlans.active', activeBackupPlanCount), {
              count: activeBackupPlanCount,
            })
          : t('dashboard.launchpad.backupPlans.empty'),
      route: '/backup-plans',
      color: T.blue,
      icon: ListChecks,
      ariaLabel: t('dashboard.launchpad.openAction', {
        title: t('dashboard.launchpad.backupPlans.title'),
        value: t(pluralKey('dashboard.launchpad.backupPlans.value', backupPlanCount), {
          count: backupPlanCount,
        }),
        status:
          backupPlanCount > 0
            ? t(pluralKey('dashboard.launchpad.backupPlans.active', activeBackupPlanCount), {
                count: activeBackupPlanCount,
              })
            : t('dashboard.launchpad.backupPlans.empty'),
      }),
    },
    {
      key: 'cloud_storage',
      title: t('dashboard.launchpad.cloudStorage.title'),
      value: t(pluralKey('dashboard.launchpad.cloudStorage.value', cloudRemoteCount), {
        count: cloudRemoteCount,
      }),
      status:
        cloudRemoteCount > 0
          ? t('dashboard.launchpad.cloudStorage.active')
          : t('dashboard.launchpad.cloudStorage.empty'),
      route: '/cloud-storage',
      color: T.indigo,
      icon: Cloud,
      ariaLabel: t('dashboard.launchpad.openAction', {
        title: t('dashboard.launchpad.cloudStorage.title'),
        value: t(pluralKey('dashboard.launchpad.cloudStorage.value', cloudRemoteCount), {
          count: cloudRemoteCount,
        }),
        status:
          cloudRemoteCount > 0
            ? t('dashboard.launchpad.cloudStorage.active')
            : t('dashboard.launchpad.cloudStorage.empty'),
      }),
    },
    {
      key: 'remote_clients',
      title: t('dashboard.launchpad.remoteClients.title'),
      value: t(pluralKey('dashboard.launchpad.remoteClients.value', remoteClientCount), {
        count: remoteClientCount,
      }),
      status:
        remoteClientCount > 0
          ? t('dashboard.launchpad.remoteClients.active')
          : t('dashboard.launchpad.remoteClients.empty'),
      route: '/remote-clients',
      color: T.blue,
      icon: Server,
      ariaLabel: t('dashboard.launchpad.openAction', {
        title: t('dashboard.launchpad.remoteClients.title'),
        value: t(pluralKey('dashboard.launchpad.remoteClients.value', remoteClientCount), {
          count: remoteClientCount,
        }),
        status:
          remoteClientCount > 0
            ? t('dashboard.launchpad.remoteClients.active')
            : t('dashboard.launchpad.remoteClients.empty'),
      }),
    },
    {
      key: 'restore_verification',
      title: t('dashboard.launchpad.restoreVerification.title'),
      value: t('dashboard.launchpad.restoreVerification.value', {
        configured: restoreConfiguredCount,
        total: repositoryCount,
      }),
      status:
        repositoryCount === 0
          ? t('dashboard.launchpad.restoreVerification.noRepositories')
          : restoreConfiguredCount === repositoryCount
            ? t('dashboard.launchpad.restoreVerification.complete')
            : t('dashboard.launchpad.restoreVerification.partial'),
      route: '/schedule/restore-checks',
      color: restoreConfiguredCount === repositoryCount && repositoryCount > 0 ? T.green : T.amber,
      icon: ShieldCheck,
      ariaLabel: t('dashboard.launchpad.openAction', {
        title: t('dashboard.launchpad.restoreVerification.title'),
        value: t('dashboard.launchpad.restoreVerification.value', {
          configured: restoreConfiguredCount,
          total: repositoryCount,
        }),
        status:
          repositoryCount === 0
            ? t('dashboard.launchpad.restoreVerification.noRepositories')
            : restoreConfiguredCount === repositoryCount
              ? t('dashboard.launchpad.restoreVerification.complete')
              : t('dashboard.launchpad.restoreVerification.partial'),
      }),
    },
  ]

  return (
    <Box
      component="section"
      aria-labelledby="dashboard-launchpad-heading"
      sx={{
        bgcolor: T.bgCard,
        border: `1px solid ${T.border}`,
        borderRadius: T.radius,
        transition: 'border-color 0.2s',
        p: 2,
        '&:hover': { borderColor: T.borderHover },
      }}
    >
      <Typography
        id="dashboard-launchpad-heading"
        sx={{ fontSize: '0.8125rem', fontWeight: 600, color: T.textPrimary, mb: 1.5 }}
      >
        {t('dashboard.launchpad.title')}
      </Typography>

      <Stack spacing={0.5}>
        {cards.map(({ key, title, value, status, route, color, icon: Icon, ariaLabel }) => (
          <Box
            key={key}
            component="button"
            type="button"
            aria-label={ariaLabel}
            onClick={() => onNavigate(route, key)}
            sx={{
              appearance: 'none',
              border: '1px solid transparent',
              borderRadius: '8px',
              bgcolor: 'transparent',
              color: 'inherit',
              cursor: 'pointer',
              display: 'grid',
              gridTemplateColumns: '28px minmax(0, 1fr) 16px',
              alignItems: 'center',
              gap: 1,
              font: 'inherit',
              minWidth: 0,
              p: 0.75,
              textAlign: 'left',
              width: '100%',
              transition: 'background-color 0.16s, border-color 0.16s',
              '&:hover': {
                bgcolor: T.hoverBg,
                borderColor: alpha(color, 0.24),
              },
              '&:focus-visible': {
                outline: `2px solid ${alpha(color, 0.65)}`,
                outlineOffset: 2,
              },
            }}
          >
            <Box
              sx={{
                width: 28,
                height: 28,
                borderRadius: '8px',
                display: 'grid',
                placeItems: 'center',
                bgcolor: alpha(color, 0.11),
                color,
                flexShrink: 0,
              }}
            >
              <Icon size={14} />
            </Box>
            <Box sx={{ minWidth: 0 }}>
              <Typography
                sx={{
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  color: T.textPrimary,
                  lineHeight: 1.25,
                  minWidth: 0,
                }}
              >
                {title}
              </Typography>
              <Typography
                sx={{
                  color: T.textMuted,
                  fontSize: '0.75rem',
                  lineHeight: 1.35,
                  minWidth: 0,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                <Box
                  component="span"
                  sx={{ color: T.textPrimary, fontFamily: T.mono, fontWeight: 700 }}
                >
                  {value}
                </Box>
                {' · '}
                {status}
              </Typography>
            </Box>
            <ArrowRight size={14} color={T.textMuted} aria-hidden="true" />
          </Box>
        ))}
      </Stack>
    </Box>
  )
}

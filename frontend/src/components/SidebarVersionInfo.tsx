import { useState } from 'react'
import { Box, Typography, Tooltip, Skeleton } from '@mui/material'
import { Info } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import VersionChip from './VersionChip'
import PlanBadge from './PlanBadge'
import PlanInfoDrawer from './PlanInfoDrawer'
import { usePlan } from '../hooks/usePlan'
import { useAnalytics } from '../hooks/useAnalytics'

interface SystemInfo {
  app_version: string
  borg_version: string | null
  borg2_version: string | null
}

interface SidebarVersionInfoProps {
  systemInfo: SystemInfo | null
}

export default function SidebarVersionInfo({ systemInfo }: SidebarVersionInfoProps) {
  const { t } = useTranslation()
  const { plan, features, entitlement, isLoading: isPlanLoading } = usePlan()
  const { track, EventCategory } = useAnalytics()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const displayedPlan =
    entitlement?.is_full_access && entitlement.status === 'active'
      ? 'enterprise'
      : entitlement?.access_level === 'pro' || entitlement?.access_level === 'enterprise'
        ? entitlement.access_level
        : plan === 'pro' || plan === 'enterprise'
          ? plan
          : 'pro'

  const handleBadgeClick = () => {
    track(EventCategory.PLAN, 'OpenDrawer', { plan: displayedPlan })
    setDrawerOpen(true)
  }

  return (
    <Box sx={{ mt: 'auto', px: 2, py: 1.5, borderTop: 1, borderColor: 'divider' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
        <Tooltip title={t('layout.systemInformation')} arrow placement="right">
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
            <Info size={13} style={{ color: '#555', flexShrink: 0 }} />
            <Typography
              variant="caption"
              sx={{
                fontWeight: 600,
                fontSize: '0.65rem',
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                color: 'text.disabled',
              }}
            >
              {t('navigation.versionInfo')}
            </Typography>
          </Box>
        </Tooltip>
        {isPlanLoading ? (
          <Skeleton variant="rounded" width={32} height={12} sx={{ borderRadius: '3px' }} />
        ) : (
          <PlanBadge plan={plan} entitlement={entitlement} onClick={handleBadgeClick} />
        )}
      </Box>
      {systemInfo ? (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
          <VersionChip label="UI" version={systemInfo.app_version} />
          {systemInfo.borg_version && (
            <VersionChip label="B1" version={systemInfo.borg_version.replace(/^borg\s*/i, '')} />
          )}
          {systemInfo.borg2_version && (
            <VersionChip
              label="B2"
              version={systemInfo.borg2_version.replace(/^borg2\s*/i, '')}
              accent
            />
          )}
        </Box>
      ) : (
        <Typography variant="caption" display="block" color="text.secondary">
          {t('navigation.loading')}
        </Typography>
      )}
      <PlanInfoDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        plan={plan}
        initialSelectedPlan={displayedPlan}
        features={features}
        entitlement={entitlement}
      />
    </Box>
  )
}

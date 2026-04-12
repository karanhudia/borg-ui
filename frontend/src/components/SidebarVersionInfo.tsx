import { useState } from 'react'
import { Box, Skeleton } from '@mui/material'
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
  const { plan, features, entitlement, isLoading: isPlanLoading } = usePlan()
  const { trackPlan, EventAction } = useAnalytics()
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
    trackPlan(EventAction.VIEW, {
      surface: 'plan_badge',
      operation: 'open_drawer',
      displayed_plan: displayedPlan,
    })
    setDrawerOpen(true)
  }

  return (
    <Box sx={{ mt: 'auto', px: 2, pt: 1, pb: 1.5, borderTop: 1, borderColor: 'divider' }}>
      {/* Plan badge — own row, full width */}
      <Box sx={{ mb: 1 }}>
        {isPlanLoading ? (
          <Skeleton variant="rounded" width={80} height={14} sx={{ borderRadius: '3px' }} />
        ) : (
          <PlanBadge plan={plan} entitlement={entitlement} onClick={handleBadgeClick} />
        )}
      </Box>

      {/* Version chips */}
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
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
          <Skeleton variant="rounded" width={118} height={16} sx={{ borderRadius: '4px' }} />
          <Skeleton variant="rounded" width={54} height={16} sx={{ borderRadius: '4px' }} />
          <Skeleton variant="rounded" width={70} height={16} sx={{ borderRadius: '4px' }} />
        </Box>
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

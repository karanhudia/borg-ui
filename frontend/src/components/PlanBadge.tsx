import { Box, Typography } from '@mui/material'
import { ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Plan, PLAN_COLOR, PLAN_LABEL } from '../core/features'
import type { EntitlementInfo } from '../hooks/useSystemInfo'

interface PlanBadgeProps {
  plan: Plan
  entitlement?: EntitlementInfo
  onClick: () => void
}

export default function PlanBadge({ plan, entitlement, onClick }: PlanBadgeProps) {
  const { t } = useTranslation()
  const isFullAccess = entitlement?.is_full_access && entitlement.status === 'active'
  const color = isFullAccess ? PLAN_COLOR.enterprise : PLAN_COLOR[plan]
  const label = isFullAccess ? t('plan.fullAccessLabel') : PLAN_LABEL[plan]

  return (
    <Box
      onClick={onClick}
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 0.5,
        cursor: 'pointer',
        borderRadius: '3px',
        px: 0.5,
        py: 0.25,
        mx: -0.5,
        transition: 'background-color 0.15s ease',
        '&:hover': {
          bgcolor: `${color}18`,
        },
      }}
    >
      <Box
        sx={{
          width: 5,
          height: 5,
          borderRadius: '50%',
          bgcolor: color,
          flexShrink: 0,
          boxShadow: `0 0 4px ${color}80`,
        }}
      />
      <Typography
        sx={{
          fontSize: '0.6rem',
          fontWeight: 700,
          color: color,
          letterSpacing: '0.05em',
          textTransform: 'uppercase',
          lineHeight: 1,
          opacity: 0.9,
        }}
      >
        {label}
      </Typography>
      <ChevronRight size={9} style={{ color, opacity: 0.6, marginLeft: 1 }} />
    </Box>
  )
}

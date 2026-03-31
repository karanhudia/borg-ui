import { Box, Typography } from '@mui/material'
import { Plan, PLAN_COLOR, PLAN_LABEL } from '../core/features'

interface PlanBadgeProps {
  plan: Plan
  onClick: () => void
}

export default function PlanBadge({ plan, onClick }: PlanBadgeProps) {
  const color = PLAN_COLOR[plan]
  const label = PLAN_LABEL[plan]

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
    </Box>
  )
}

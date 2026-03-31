import { Box, Typography, Chip } from '@mui/material'
import { alpha } from '@mui/material/styles'
import { Lock } from 'lucide-react'
import { Plan, PLAN_LABEL, PLAN_COLOR } from '../core/features'

interface UpgradePromptProps {
  requiredPlan: Plan
  message?: string
}

export default function UpgradePrompt({ requiredPlan, message }: UpgradePromptProps) {
  const color = PLAN_COLOR[requiredPlan]
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 1.5,
        py: 3,
        px: 2,
        border: '1px dashed',
        borderColor: 'divider',
        borderRadius: 2,
        textAlign: 'center',
      }}
    >
      <Lock size={24} color={color} />
      <Chip
        label={`${PLAN_LABEL[requiredPlan]} feature`}
        size="small"
        sx={{
          bgcolor: alpha(color, 0.12),
          color,
          border: `1px solid ${alpha(color, 0.25)}`,
          fontWeight: 700,
          fontSize: '0.7rem',
        }}
      />
      <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 280 }}>
        {message ?? `This feature requires the ${PLAN_LABEL[requiredPlan]} plan.`}
      </Typography>
    </Box>
  )
}

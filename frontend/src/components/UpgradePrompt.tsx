import { Box, Typography, Chip, Button } from '@mui/material'
import { alpha } from '@mui/material/styles'
import { Lock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Plan, PLAN_LABEL, PLAN_COLOR } from '../core/features'
import { BUY_URL } from '../utils/externalLinks'

interface UpgradePromptProps {
  requiredPlan: Plan
  message?: string
}

export default function UpgradePrompt({ requiredPlan, message }: UpgradePromptProps) {
  const { t } = useTranslation()
  const color = PLAN_COLOR[requiredPlan]
  const planLabel = PLAN_LABEL[requiredPlan]
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
        label={t('upgradePrompt.featureLabel', { plan: planLabel })}
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
        {message ?? t('upgradePrompt.defaultMessage', { plan: planLabel })}
      </Typography>
      <Button
        component="a"
        href={BUY_URL}
        target="_blank"
        rel="noreferrer"
        variant="contained"
        size="small"
        sx={{ mt: 0.5 }}
      >
        {t('upgradePrompt.buyLink')}
      </Button>
    </Box>
  )
}

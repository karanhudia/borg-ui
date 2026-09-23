import { Box, Typography } from '@mui/material'
import { Clock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { PlanDrawerPlanColors } from './planDrawerColors'

interface UpcomingFeature {
  id: string
  label: string
  description: string
  available_in?: string
}

interface PlanUpcomingFeaturesProps {
  title: string
  features: UpcomingFeature[]
  colors: PlanDrawerPlanColors
  sectionColor: string
}

/** Features the manifest ties to a release this install does not have yet. */
export default function PlanUpcomingFeatures({
  title,
  features,
  colors,
  sectionColor,
}: PlanUpcomingFeaturesProps) {
  const { t } = useTranslation()

  return (
    <>
      <Box
        sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.25 }}
      >
        <Typography
          variant="caption"
          sx={{
            fontWeight: 700,
            fontSize: '0.6rem',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: sectionColor,
          }}
        >
          {title}
        </Typography>
      </Box>
      {features.map((feature) => (
        <Box key={feature.id} sx={{ display: 'flex', gap: 1.25, mb: 1.5 }}>
          <Box
            sx={{
              width: 16,
              height: 16,
              borderRadius: '4px',
              bgcolor: colors.iconSurface,
              border: '1px dashed',
              borderColor: colors.iconBorder,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              mt: 0.125,
            }}
          >
            <Clock size={9} style={{ color: colors.accent }} strokeWidth={2.5} />
          </Box>
          <Box>
            <Typography
              sx={{ fontSize: '0.78rem', fontWeight: 600, color: 'text.primary', lineHeight: 1.3 }}
            >
              {feature.label}
            </Typography>
            <Typography
              sx={{ fontSize: '0.7rem', color: colors.description, lineHeight: 1.4, mt: 0.25 }}
            >
              {feature.description}
            </Typography>
            <Typography
              sx={{
                fontSize: '0.68rem',
                color: colors.accent,
                lineHeight: 1.4,
                mt: 0.35,
                fontWeight: 700,
              }}
            >
              {t('plan.availableIn', { version: feature.available_in })}
            </Typography>
          </Box>
        </Box>
      ))}
    </>
  )
}

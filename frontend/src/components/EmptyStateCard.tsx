import type { ReactNode } from 'react'
import type { SxProps, Theme } from '@mui/material'
import { Box, Card, CardContent, Typography } from '@mui/material'

interface EmptyStateCardProps {
  icon: ReactNode
  title: ReactNode
  description?: ReactNode
  secondaryDescription?: ReactNode
  actions?: ReactNode
  maxWidth?: number | string
  centered?: boolean
  cardSx?: SxProps<Theme>
}

export default function EmptyStateCard({
  icon,
  title,
  description,
  secondaryDescription,
  actions,
  maxWidth,
  centered = true,
  cardSx,
}: EmptyStateCardProps) {
  const cardSxList = Array.isArray(cardSx) ? cardSx : cardSx ? [cardSx] : []

  const card = (
    <Card sx={[{ width: '100%', ...(maxWidth ? { maxWidth } : {}) }, ...cardSxList]}>
      <CardContent sx={{ textAlign: 'center', py: 8 }}>
        <Box
          sx={{
            display: 'flex',
            justifyContent: 'center',
            color: 'text.disabled',
            lineHeight: 0,
            mb: 2,
          }}
        >
          {icon}
        </Box>
        <Typography variant="h6" gutterBottom>
          {title}
        </Typography>
        {description && (
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ mb: secondaryDescription ? 1.5 : actions ? 3 : 0 }}
          >
            {description}
          </Typography>
        )}
        {secondaryDescription && (
          <Typography variant="body2" color="text.secondary" sx={{ mb: actions ? 3 : 0 }}>
            {secondaryDescription}
          </Typography>
        )}
        {actions}
      </CardContent>
    </Card>
  )

  if (!centered) return card

  return <Box sx={{ display: 'flex', justifyContent: 'center', mt: { xs: 4, md: 6 } }}>{card}</Box>
}

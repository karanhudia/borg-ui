import { Box, Chip, useTheme, alpha } from '@mui/material'
import { useTranslation } from 'react-i18next'
import type { OperationCategory } from '../types/operations'
import { CATEGORY_ICONS, categoryColor } from './categoryStyle'

interface CategoryTokenProps {
  category: OperationCategory
  size?: 'small' | 'medium'
}

export default function CategoryToken({ category, size = 'small' }: CategoryTokenProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const Icon = CATEGORY_ICONS[category]
  const color = categoryColor(theme, category)
  return (
    <Chip
      size={size}
      icon={
        <Box sx={{ display: 'flex', alignItems: 'center', pl: 0.5 }}>
          <Icon size={size === 'small' ? 12 : 14} />
        </Box>
      }
      label={t(`operations.category.${category}`)}
      sx={{
        bgcolor: alpha(color, 0.12),
        color,
        fontWeight: 600,
        '& .MuiChip-icon': { color },
      }}
    />
  )
}

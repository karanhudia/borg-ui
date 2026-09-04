import { Box, Chip, useTheme, alpha } from '@mui/material'
import type { ComponentType } from 'react'
import { Download, Save, RotateCcw, Wrench, Database, Cloud, Package } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { OperationCategory } from '../types/operations'

const ICONS: Record<OperationCategory, ComponentType<{ size?: number }>> = {
  import: Download,
  backup: Save,
  restore: RotateCcw,
  maintenance: Wrench,
  index: Database,
  mirror: Cloud,
  system: Package,
}

const PALETTE_KEYS: Record<
  OperationCategory,
  'primary' | 'success' | 'warning' | 'info' | 'secondary'
> = {
  import: 'info',
  backup: 'success',
  restore: 'primary',
  maintenance: 'warning',
  index: 'secondary',
  mirror: 'info',
  system: 'secondary',
}

interface CategoryTokenProps {
  category: OperationCategory
  size?: 'small' | 'medium'
}

export default function CategoryToken({ category, size = 'small' }: CategoryTokenProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const Icon = ICONS[category]
  const colorKey = PALETTE_KEYS[category]
  const color = (theme.palette[colorKey] as { main: string }).main
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

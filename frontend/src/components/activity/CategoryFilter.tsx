import { ToggleButton, ToggleButtonGroup, alpha, useTheme } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { CATEGORY_ICONS, categoryColor } from '../categoryStyle'
import type { OperationCategory } from '../../types/operations'

const CATEGORIES: OperationCategory[] = [
  'import',
  'backup',
  'restore',
  'maintenance',
  'index',
  'mirror',
  'system',
]

interface CategoryFilterProps {
  value: OperationCategory[]
  onChange: (categories: OperationCategory[]) => void
}

// The one category control for the global Activity page and the
// repository view, so the two never drift. Multi-select: the API takes a
// list, and "Backup and Maintenance" is a real question. A selected
// category fills with its own colour; unselected ones stay neutral so the
// active filter reads at a glance.
export default function CategoryFilter({ value, onChange }: CategoryFilterProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  return (
    <ToggleButtonGroup
      size="small"
      value={value}
      onChange={(_event, next: OperationCategory[]) => onChange(next)}
      aria-label={t('activity.filterCategory')}
      sx={{ flexWrap: 'wrap', bgcolor: 'background.paper', width: 'fit-content' }}
    >
      {CATEGORIES.map((category) => {
        const Icon = CATEGORY_ICONS[category]
        const color = categoryColor(theme, category)
        return (
          <ToggleButton
            key={category}
            value={category}
            aria-label={t(`operations.category.${category}`)}
            sx={{
              textTransform: 'none',
              fontWeight: 600,
              fontSize: '0.8125rem',
              height: 40,
              px: 1.5,
              gap: 0.75,
              color: 'text.secondary',
              borderColor: 'divider',
              '&:hover': { bgcolor: alpha(color, 0.06), color },
              '&.Mui-selected': {
                color,
                bgcolor: alpha(color, 0.12),
                '&:hover': { bgcolor: alpha(color, 0.18) },
              },
            }}
          >
            <Icon size={14} />
            {t(`operations.category.${category}`)}
          </ToggleButton>
        )
      })}
    </ToggleButtonGroup>
  )
}

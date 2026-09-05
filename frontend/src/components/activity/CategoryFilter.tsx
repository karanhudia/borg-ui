import { ToggleButton, ToggleButtonGroup } from '@mui/material'
import { useTranslation } from 'react-i18next'
import CategoryToken from '../CategoryToken'
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
// list, and "Backup and Maintenance" is a real question.
export default function CategoryFilter({ value, onChange }: CategoryFilterProps) {
  const { t } = useTranslation()
  return (
    <ToggleButtonGroup
      size="small"
      value={value}
      onChange={(_event, next: OperationCategory[]) => onChange(next)}
      aria-label={t('activity.filterCategory')}
      sx={{
        flexWrap: 'wrap',
        '& .MuiToggleButton-root': {
          textTransform: 'none',
          py: 0.25,
          px: 0.75,
          border: 1,
          borderColor: 'divider',
          '& .MuiChip-root': { bgcolor: 'transparent', opacity: 0.6 },
          '&.Mui-selected .MuiChip-root': { opacity: 1 },
        },
      }}
    >
      {CATEGORIES.map((category) => (
        <ToggleButton
          key={category}
          value={category}
          aria-label={t(`operations.category.${category}`)}
        >
          <CategoryToken category={category} />
        </ToggleButton>
      ))}
    </ToggleButtonGroup>
  )
}

import type { Meta, StoryObj } from '@storybook/react-vite'
import { Stack } from '@mui/material'
import CategoryToken from './CategoryToken'
import type { OperationCategory } from '../types/operations'

const CATEGORIES: OperationCategory[] = [
  'import',
  'backup',
  'restore',
  'maintenance',
  'index',
  'mirror',
  'system',
]

const meta = {
  title: 'Components/CategoryToken',
} satisfies Meta<typeof CategoryToken>

export default meta

type Story = StoryObj<typeof meta>

export const AllCategories: Story = {
  render: () => (
    <Stack direction="row" spacing={1} flexWrap="wrap">
      {CATEGORIES.map((category) => (
        <CategoryToken key={category} category={category} />
      ))}
    </Stack>
  ),
}

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import { describe, expect, it, vi } from 'vitest'

import { RepositoriesToolbar } from '../RepositoriesToolbar'

const theme = createTheme()

function renderToolbar(overrides: Partial<React.ComponentProps<typeof RepositoriesToolbar>> = {}) {
  const props: React.ComponentProps<typeof RepositoriesToolbar> = {
    isVisible: true,
    searchQuery: '',
    sortBy: 'name-asc',
    groupBy: 'none',
    processedRepositories: { groups: [{ name: null, repositories: [] }] },
    backupPlans: [
      { id: 7, name: 'Daily Plan' },
      { id: 8, name: 'Weekly Plan' },
    ],
    backupPlanFilterLoading: false,
    selectedBackupPlanId: 7,
    onSearchChange: vi.fn(),
    onSortChange: vi.fn(),
    onGroupChange: vi.fn(),
    onBackupPlanFilterChange: vi.fn(),
    onFilterTracked: vi.fn(),
    ...overrides,
  }

  return render(
    <ThemeProvider theme={theme}>
      <RepositoriesToolbar {...props} />
    </ThemeProvider>
  )
}

describe('RepositoriesToolbar', () => {
  it('shows the selected backup plan filter and reports manual filter changes', async () => {
    const user = userEvent.setup()
    const onBackupPlanFilterChange = vi.fn()

    renderToolbar({ onBackupPlanFilterChange })

    expect(screen.getByRole('combobox', { name: 'Backup Plan' })).toHaveTextContent('Daily Plan')

    await user.click(screen.getByRole('combobox', { name: 'Backup Plan' }))
    await user.click(screen.getByRole('option', { name: 'Weekly Plan' }))

    expect(onBackupPlanFilterChange).toHaveBeenCalledWith(8)
  })
})

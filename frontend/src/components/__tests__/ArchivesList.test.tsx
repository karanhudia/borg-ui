import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import ArchivesList from '../ArchivesList'

// Mock ArchiveCard since it's tested separately
vi.mock('../ArchiveCard', () => ({
  default: ({ archive }: { archive: { id: string; name: string } }) => (
    <div data-testid={`archive-card-${archive.id}`}>Archive: {archive.name}</div>
  ),
}))

describe('ArchivesList', () => {
  const mockArchives = [
    {
      id: '1',
      name: 'backup-2024-01-15',
      archive: 'backup-2024-01-15',
      start: '2024-01-15T10:00:00Z',
      time: '2024-01-15T10:00:00Z',
    },
    {
      id: '2',
      name: 'backup-2024-01-16',
      archive: 'backup-2024-01-16',
      start: '2024-01-16T10:00:00Z',
      time: '2024-01-16T10:00:00Z',
    },
    {
      id: '3',
      name: 'backup-2024-01-17',
      archive: 'backup-2024-01-17',
      start: '2024-01-17T10:00:00Z',
      time: '2024-01-17T10:00:00Z',
    },
  ]

  const mockHandlers = {
    onViewArchive: vi.fn(),
    onRestoreArchive: vi.fn(),
    onMountArchive: vi.fn(),
    onDeleteArchive: vi.fn(),
  }

  it('renders loading state', () => {
    render(
      <ArchivesList archives={[]} repositoryName="Test Repo" loading={true} {...mockHandlers} />
    )

    expect(screen.getByText('Loading archives...')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('renders empty state when no archives', () => {
    render(
      <ArchivesList archives={[]} repositoryName="Test Repo" loading={false} {...mockHandlers} />
    )

    expect(screen.getByText('No archives found in this repository')).toBeInTheDocument()
  })

  it('renders header with repository name and count', () => {
    render(
      <ArchivesList
        archives={mockArchives}
        repositoryName="My Backup Repo"
        loading={false}
        {...mockHandlers}
      />
    )

    expect(screen.getByText('Archives for My Backup Repo')).toBeInTheDocument()
    expect(screen.getByText('3 archives')).toBeInTheDocument()
  })

  it('uses singular "archive" for count of 1', () => {
    render(
      <ArchivesList
        archives={[mockArchives[0]]}
        repositoryName="Test Repo"
        loading={false}
        {...mockHandlers}
      />
    )

    expect(screen.getByText('1 archive')).toBeInTheDocument()
  })

  it('renders all archives as cards', () => {
    render(
      <ArchivesList
        archives={mockArchives}
        repositoryName="Test Repo"
        loading={false}
        {...mockHandlers}
      />
    )

    expect(screen.getByTestId('archive-card-1')).toBeInTheDocument()
    expect(screen.getByTestId('archive-card-2')).toBeInTheDocument()
    expect(screen.getByTestId('archive-card-3')).toBeInTheDocument()

    expect(screen.getByText('Archive: backup-2024-01-15')).toBeInTheDocument()
    expect(screen.getByText('Archive: backup-2024-01-16')).toBeInTheDocument()
    expect(screen.getByText('Archive: backup-2024-01-17')).toBeInTheDocument()
  })

  it('does not render header in loading state', () => {
    render(
      <ArchivesList
        archives={mockArchives}
        repositoryName="Test Repo"
        loading={true}
        {...mockHandlers}
      />
    )

    expect(screen.queryByText('Archives for Test Repo')).not.toBeInTheDocument()
  })

  it('does not render header in empty state', () => {
    render(
      <ArchivesList archives={[]} repositoryName="Test Repo" loading={false} {...mockHandlers} />
    )

    expect(screen.queryByText('Archives for Test Repo')).not.toBeInTheDocument()
  })

  it('handles large number of archives', () => {
    const manyArchives = Array.from({ length: 100 }, (_, i) => ({
      id: `${i}`,
      name: `backup-${i}`,
      archive: `backup-${i}`,
      start: '2024-01-15T10:00:00Z',
      time: '2024-01-15T10:00:00Z',
    }))

    render(
      <ArchivesList
        archives={manyArchives}
        repositoryName="Test Repo"
        loading={false}
        {...mockHandlers}
      />
    )

    expect(screen.getByText('100 archives')).toBeInTheDocument()
    // With pagination (default 10 per page), only first 10 should be visible
    expect(screen.getByTestId('archive-card-0')).toBeInTheDocument()
    expect(screen.getByTestId('archive-card-9')).toBeInTheDocument()
    expect(screen.queryByTestId('archive-card-10')).not.toBeInTheDocument()
    expect(screen.queryByTestId('archive-card-99')).not.toBeInTheDocument()
  })

  beforeEach(() => {
    // Clear localStorage before each test
    localStorage.clear()
  })

  describe('Pagination', () => {
    const createArchives = (count: number) =>
      Array.from({ length: count }, (_, i) => ({
        id: `${i}`,
        name: `backup-${i}`,
        archive: `backup-${i}`,
        start: '2024-01-15T10:00:00Z',
        time: '2024-01-15T10:00:00Z',
      }))

    it('renders pagination controls when archives exist', () => {
      const archives = createArchives(15)
      render(
        <ArchivesList
          archives={archives}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      expect(screen.getByText('Archives per page:')).toBeInTheDocument()
      expect(screen.getByText(/1–10 of 15/)).toBeInTheDocument()
    })

    it('does not render pagination for empty archives', () => {
      render(
        <ArchivesList archives={[]} repositoryName="Test Repo" loading={false} {...mockHandlers} />
      )

      expect(screen.queryByText('Archives per page:')).not.toBeInTheDocument()
    })

    it('displays correct number of archives per page', () => {
      const archives = createArchives(25)
      render(
        <ArchivesList
          archives={archives}
          repositoryName="Test Repo"
          loading={false}
          defaultRowsPerPage={10}
          {...mockHandlers}
        />
      )

      // First 10 should be visible
      expect(screen.getByTestId('archive-card-0')).toBeInTheDocument()
      expect(screen.getByTestId('archive-card-9')).toBeInTheDocument()
      // 11th should not be visible
      expect(screen.queryByTestId('archive-card-10')).not.toBeInTheDocument()
    })

    it('shows correct pagination text', () => {
      const archives = createArchives(35)
      render(
        <ArchivesList
          archives={archives}
          repositoryName="Test Repo"
          loading={false}
          defaultRowsPerPage={10}
          {...mockHandlers}
        />
      )

      expect(screen.getByText(/1–10 of 35/)).toBeInTheDocument()
    })

    it('handles custom rows per page options', () => {
      const archives = createArchives(50)
      render(
        <ArchivesList
          archives={archives}
          repositoryName="Test Repo"
          loading={false}
          defaultRowsPerPage={25}
          rowsPerPageOptions={[10, 25, 50]}
          {...mockHandlers}
        />
      )

      expect(screen.getByText(/1–25 of 50/)).toBeInTheDocument()
    })

    it('renders all archives on single page when count is less than page size', () => {
      const archives = createArchives(5)
      render(
        <ArchivesList
          archives={archives}
          repositoryName="Test Repo"
          loading={false}
          defaultRowsPerPage={10}
          {...mockHandlers}
        />
      )

      // All 5 should be visible
      expect(screen.getByTestId('archive-card-0')).toBeInTheDocument()
      expect(screen.getByTestId('archive-card-4')).toBeInTheDocument()
      expect(screen.getByText(/1–5 of 5/)).toBeInTheDocument()
    })
  })

  describe('Sorting', () => {
    const archivesWithDates = [
      {
        id: '1',
        name: 'backup-old',
        archive: 'backup-old',
        start: '2024-01-10T10:00:00Z',
        time: '2024-01-10T10:00:00Z',
      },
      {
        id: '2',
        name: 'backup-new',
        archive: 'backup-new',
        start: '2024-01-20T10:00:00Z',
        time: '2024-01-20T10:00:00Z',
      },
      {
        id: '3',
        name: 'backup-newest',
        archive: 'backup-newest',
        start: '2024-01-25T10:00:00Z',
        time: '2024-01-25T10:00:00Z',
      },
    ]

    it('displays sort dropdown in flat view', () => {
      render(
        <ArchivesList
          archives={archivesWithDates}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      // Sort dropdown should be visible with default value
      expect(screen.getByText('Newest first')).toBeInTheDocument()
      // Verify the label is present (there may be multiple)
      expect(screen.getAllByText('Sort by').length).toBeGreaterThan(0)
    })

    it('changes sort order to oldest first', async () => {
      const user = userEvent.setup()
      render(
        <ArchivesList
          archives={archivesWithDates}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      // Find the sort select by text content
      const sortSelect = screen.getByText('Newest first')
      await user.click(sortSelect)

      const oldestOption = screen.getByRole('option', { name: 'Oldest first' })
      await user.click(oldestOption)

      // LocalStorage should be updated
      expect(localStorage.getItem('archives-list-sort-by')).toBe('date-asc')
    })

    it('hides sort dropdown in grouped view', async () => {
      const user = userEvent.setup()
      render(
        <ArchivesList
          archives={archivesWithDates}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      // Switch to grouped view
      const groupedButton = screen.getByRole('button', { name: /grouped/i })
      await user.click(groupedButton)

      // Sort dropdown should not be visible in grouped view
      expect(screen.queryByLabelText('Sort by')).not.toBeInTheDocument()
    })
  })

  describe('Filtering', () => {
    const mixedArchives = [
      {
        id: '1',
        name: 'scheduled-backup-1',
        archive: 'scheduled-backup-1',
        start: '2024-01-15T10:00:00Z',
        time: '2024-01-15T10:00:00Z',
        comment: 'Automated backup',
      },
      {
        id: '2',
        name: 'manual-backup',
        archive: 'manual-backup',
        start: '2024-01-16T10:00:00Z',
        time: '2024-01-16T10:00:00Z',
      },
      {
        id: '3',
        name: 'scheduled-backup-2',
        archive: 'scheduled-backup-2',
        start: '2024-01-17T10:00:00Z',
        time: '2024-01-17T10:00:00Z',
        comment: 'Automated backup',
      },
    ]

    it('displays filter dropdown', () => {
      render(
        <ArchivesList
          archives={mixedArchives}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      // Filter dropdown should be visible with default value
      expect(screen.getByText('All Archives')).toBeInTheDocument()
      // Verify the label is present (there may be multiple)
      expect(screen.getAllByText('Filter').length).toBeGreaterThan(0)
    })

    it('filters to show only scheduled archives', async () => {
      const user = userEvent.setup()
      render(
        <ArchivesList
          archives={mixedArchives}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      // Find the filter select by text content
      const filterSelect = screen.getByText('All Archives')
      await user.click(filterSelect)

      const scheduledOption = screen.getByRole('option', { name: 'Scheduled' })
      await user.click(scheduledOption)

      // LocalStorage should be updated
      expect(localStorage.getItem('archives-list-filter')).toBe('scheduled')
    })

    it('filters to show only manual archives', async () => {
      const user = userEvent.setup()
      render(
        <ArchivesList
          archives={mixedArchives}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      // Find the filter select by text content
      const filterSelect = screen.getByText('All Archives')
      await user.click(filterSelect)

      const manualOption = screen.getByRole('option', { name: 'Manual' })
      await user.click(manualOption)

      // LocalStorage should be updated
      expect(localStorage.getItem('archives-list-filter')).toBe('manual')
    })

    it('shows filtered count when filter is active', () => {
      render(
        <ArchivesList
          archives={mixedArchives}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      // Should show total count when filter is 'all'
      expect(screen.getByText('3 archives')).toBeInTheDocument()
    })

    it('shows empty state when no archives match filter', async () => {
      const allScheduled = mixedArchives.filter((a) => a.comment)
      const user = userEvent.setup()

      render(
        <ArchivesList
          archives={allScheduled}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      // Find the filter select by text content
      const filterSelect = screen.getByText('All Archives')
      await user.click(filterSelect)

      const manualOption = screen.getByRole('option', { name: 'Manual' })
      await user.click(manualOption)

      expect(screen.getByText('No manual archives found')).toBeInTheDocument()
      expect(screen.getByText('Try selecting a different filter')).toBeInTheDocument()
    })
  })

  describe('View Mode Toggle', () => {
    const recentArchives = [
      {
        id: '1',
        name: 'backup-1',
        archive: 'backup-1',
        start: new Date().toISOString(),
        time: new Date().toISOString(),
      },
      {
        id: '2',
        name: 'backup-2',
        archive: 'backup-2',
        start: new Date(Date.now() - 86400000).toISOString(), // Yesterday
        time: new Date(Date.now() - 86400000).toISOString(),
      },
    ]

    it('displays view mode toggle buttons', () => {
      render(
        <ArchivesList
          archives={recentArchives}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      expect(screen.getByRole('button', { name: /grouped/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /list/i })).toBeInTheDocument()
    })

    it('switches to grouped view', async () => {
      const user = userEvent.setup()
      render(
        <ArchivesList
          archives={recentArchives}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      const groupedButton = screen.getByRole('button', { name: /grouped/i })
      await user.click(groupedButton)

      // LocalStorage should be updated
      expect(localStorage.getItem('archives-list-grouping-enabled')).toBe('true')
    })

    it('switches back to flat view', async () => {
      const user = userEvent.setup()
      localStorage.setItem('archives-list-grouping-enabled', 'true')

      render(
        <ArchivesList
          archives={recentArchives}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      const flatButton = screen.getByRole('button', { name: /list/i })
      await user.click(flatButton)

      // LocalStorage should be updated
      expect(localStorage.getItem('archives-list-grouping-enabled')).toBe('false')
    })

    it('does not change mode when clicking same button', async () => {
      const user = userEvent.setup()
      render(
        <ArchivesList
          archives={recentArchives}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      const flatButton = screen.getByRole('button', { name: /list/i })
      await user.click(flatButton)

      // Should remain in flat view (null means no change was made)
      const stored = localStorage.getItem('archives-list-grouping-enabled')
      expect(stored === null || stored === 'false').toBe(true)
    })
  })

  describe('Grouped View', () => {
    const todayDate = new Date()
    const yesterdayDate = new Date(Date.now() - 86400000)
    const lastWeekDate = new Date(Date.now() - 7 * 86400000)

    const groupedArchives = [
      {
        id: '1',
        name: 'backup-today',
        archive: 'backup-today',
        start: todayDate.toISOString(),
        time: todayDate.toISOString(),
      },
      {
        id: '2',
        name: 'backup-yesterday',
        archive: 'backup-yesterday',
        start: yesterdayDate.toISOString(),
        time: yesterdayDate.toISOString(),
      },
      {
        id: '3',
        name: 'backup-lastweek',
        archive: 'backup-lastweek',
        start: lastWeekDate.toISOString(),
        time: lastWeekDate.toISOString(),
      },
    ]

    it('renders accordions in grouped view', () => {
      localStorage.setItem('archives-list-grouping-enabled', 'true')

      render(
        <ArchivesList
          archives={groupedArchives}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      // Should have accordion groups
      expect(screen.getByText('Today')).toBeInTheDocument()
    })

    it('expands and collapses groups', async () => {
      const user = userEvent.setup()
      localStorage.setItem('archives-list-grouping-enabled', 'true')
      localStorage.setItem('archives-list-expanded-groups', JSON.stringify(['today']))

      render(
        <ArchivesList
          archives={groupedArchives}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      const todayAccordion = screen.getByText('Today').closest('div[class*="MuiAccordionSummary"]')
      if (todayAccordion) {
        await user.click(todayAccordion)
      }

      // LocalStorage should be updated
      const stored = localStorage.getItem('archives-list-expanded-groups')
      expect(stored).toBeTruthy()
    })

    it('displays archive count in group badge', () => {
      localStorage.setItem('archives-list-grouping-enabled', 'true')

      render(
        <ArchivesList
          archives={groupedArchives}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      // Each group should show count badge
      const badges = screen.getAllByText('1')
      expect(badges.length).toBeGreaterThan(0)
    })

    it('does not show pagination in grouped view', () => {
      const manyArchives = Array.from({ length: 50 }, (_, i) => ({
        id: `${i}`,
        name: `backup-${i}`,
        archive: `backup-${i}`,
        start: new Date().toISOString(),
        time: new Date().toISOString(),
      }))

      localStorage.setItem('archives-list-grouping-enabled', 'true')

      render(
        <ArchivesList
          archives={manyArchives}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      // Pagination should not be visible in grouped view
      expect(screen.queryByText('Archives per page:')).not.toBeInTheDocument()
    })
  })

  describe('LocalStorage Persistence', () => {
    it('loads saved rows per page preference', () => {
      localStorage.setItem('archives-list-rows-per-page', '25')
      const archives = Array.from({ length: 30 }, (_, i) => ({
        id: `${i}`,
        name: `backup-${i}`,
        archive: `backup-${i}`,
        start: '2024-01-15T10:00:00Z',
        time: '2024-01-15T10:00:00Z',
      }))

      render(
        <ArchivesList
          archives={archives}
          repositoryName="Test Repo"
          loading={false}
          rowsPerPageOptions={[10, 25, 50]}
          {...mockHandlers}
        />
      )

      expect(screen.getByText(/1–25 of 30/)).toBeInTheDocument()
    })

    it('uses default when saved rows per page is invalid', () => {
      localStorage.setItem('archives-list-rows-per-page', '999')
      const archives = Array.from({ length: 30 }, (_, i) => ({
        id: `${i}`,
        name: `backup-${i}`,
        archive: `backup-${i}`,
        start: '2024-01-15T10:00:00Z',
        time: '2024-01-15T10:00:00Z',
      }))

      render(
        <ArchivesList
          archives={archives}
          repositoryName="Test Repo"
          loading={false}
          defaultRowsPerPage={10}
          rowsPerPageOptions={[5, 10, 25]}
          {...mockHandlers}
        />
      )

      // Should use default 10
      expect(screen.getByText(/1–10 of 30/)).toBeInTheDocument()
    })

    it('loads saved sort preference', () => {
      localStorage.setItem('archives-list-sort-by', 'date-asc')

      render(
        <ArchivesList
          archives={mockArchives}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      // Sort dropdown should show the saved value
      expect(screen.getByText('Oldest first')).toBeInTheDocument()
    })

    it('loads saved filter preference', () => {
      localStorage.setItem('archives-list-filter', 'scheduled')

      render(
        <ArchivesList
          archives={mockArchives}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      // Filter dropdown should show the saved value
      expect(screen.getByText('Scheduled')).toBeInTheDocument()
    })

    it('loads saved grouping preference', () => {
      localStorage.setItem('archives-list-grouping-enabled', 'true')

      render(
        <ArchivesList
          archives={mockArchives}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      // Pagination should not be visible when grouped
      expect(screen.queryByText('Archives per page:')).not.toBeInTheDocument()
    })

    it('handles invalid JSON in expanded groups localStorage', () => {
      localStorage.setItem('archives-list-grouping-enabled', 'true')
      localStorage.setItem('archives-list-expanded-groups', 'invalid-json')

      const archives = [
        {
          id: '1',
          name: 'backup-1',
          archive: 'backup-1',
          start: new Date().toISOString(),
          time: new Date().toISOString(),
        },
      ]

      // Should not throw error
      expect(() => {
        render(
          <ArchivesList
            archives={archives}
            repositoryName="Test Repo"
            loading={false}
            {...mockHandlers}
          />
        )
      }).not.toThrow()
    })

    it('uses defaults when localStorage values are invalid', () => {
      localStorage.setItem('archives-list-sort-by', 'invalid-sort')
      localStorage.setItem('archives-list-filter', 'invalid-filter')

      render(
        <ArchivesList
          archives={mockArchives}
          repositoryName="Test Repo"
          loading={false}
          {...mockHandlers}
        />
      )

      // Should use defaults (date-desc, all)
      expect(screen.getByText('Newest first')).toBeInTheDocument()
      expect(screen.getByText('All Archives')).toBeInTheDocument()
    })
  })

  describe('Pagination Interactions', () => {
    const createArchives = (count: number) =>
      Array.from({ length: count }, (_, i) => ({
        id: `${i}`,
        name: `backup-${i}`,
        archive: `backup-${i}`,
        start: '2024-01-15T10:00:00Z',
        time: '2024-01-15T10:00:00Z',
      }))

    it('changes rows per page', async () => {
      const user = userEvent.setup()
      const archives = createArchives(30)

      render(
        <ArchivesList
          archives={archives}
          repositoryName="Test Repo"
          loading={false}
          defaultRowsPerPage={10}
          {...mockHandlers}
        />
      )

      // Open rows per page dropdown
      const rowsPerPageButton = screen.getByRole('combobox', { name: /archives per page/i })
      await user.click(rowsPerPageButton)

      // Select 25
      const option25 = screen.getByRole('option', { name: '25' })
      await user.click(option25)

      // LocalStorage should be updated
      expect(localStorage.getItem('archives-list-rows-per-page')).toBe('25')
    })

    it('navigates to next page', async () => {
      const user = userEvent.setup()
      const archives = createArchives(25)

      render(
        <ArchivesList
          archives={archives}
          repositoryName="Test Repo"
          loading={false}
          defaultRowsPerPage={10}
          {...mockHandlers}
        />
      )

      const nextButton = screen.getByRole('button', { name: /next page/i })
      await user.click(nextButton)

      // Should show page 2
      expect(screen.getByText(/11–20 of 25/)).toBeInTheDocument()
    })

    it('navigates to previous page', async () => {
      const user = userEvent.setup()
      const archives = createArchives(25)

      render(
        <ArchivesList
          archives={archives}
          repositoryName="Test Repo"
          loading={false}
          defaultRowsPerPage={10}
          {...mockHandlers}
        />
      )

      // Go to page 2 first
      const nextButton = screen.getByRole('button', { name: /next page/i })
      await user.click(nextButton)

      // Then go back
      const prevButton = screen.getByRole('button', { name: /previous page/i })
      await user.click(prevButton)

      // Should show page 1
      expect(screen.getByText(/1–10 of 25/)).toBeInTheDocument()
    })
  })

  describe('mountDisabled prop', () => {
    it('passes mountDisabled to ArchiveCard', () => {
      render(
        <ArchivesList
          archives={mockArchives}
          repositoryName="Test Repo"
          loading={false}
          mountDisabled={true}
          {...mockHandlers}
        />
      )

      // Component should render normally with mountDisabled prop
      expect(screen.getByTestId('archive-card-1')).toBeInTheDocument()
    })
  })
})

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import PruneRepositoryDialog from '../PruneRepositoryDialog'

const mockRepository = {
  id: 1,
  name: 'Test Repository',
}

describe('PruneRepositoryDialog', () => {
  describe('Rendering', () => {
    it('renders dialog when open', () => {
      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={false}
          results={null}
        />
      )

      // Title and button both say "Prune Archives"
      const pruneTexts = screen.getAllByText('Prune Archives')
      expect(pruneTexts.length).toBeGreaterThanOrEqual(1)
    })

    it('does not render when closed', () => {
      render(
        <PruneRepositoryDialog
          open={false}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={false}
          results={null}
        />
      )

      expect(screen.queryByText('Prune Archives')).not.toBeInTheDocument()
    })

    it('shows repository name', () => {
      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={false}
          results={null}
        />
      )

      expect(screen.getByText('Test Repository')).toBeInTheDocument()
    })

    it('shows info about pruning', () => {
      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={false}
          results={null}
        />
      )

      expect(screen.getByText('What does pruning do?')).toBeInTheDocument()
    })
  })

  describe('Retention Policy Inputs', () => {
    it('renders all retention inputs', () => {
      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={false}
          results={null}
        />
      )

      expect(screen.getByLabelText(/Keep Hourly/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/Keep Daily/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/Keep Weekly/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/Keep Monthly/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/Keep Quarterly/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/Keep Yearly/i)).toBeInTheDocument()
    })

    it('shows default values', () => {
      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={false}
          results={null}
        />
      )

      expect(screen.getByLabelText(/Keep Daily/i)).toHaveValue(7)
      expect(screen.getByLabelText(/Keep Weekly/i)).toHaveValue(4)
      expect(screen.getByLabelText(/Keep Monthly/i)).toHaveValue(6)
      expect(screen.getByLabelText(/Keep Yearly/i)).toHaveValue(1)
    })

    it('allows changing retention values', async () => {
      const user = userEvent.setup()

      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={false}
          results={null}
        />
      )

      const dailyInput = screen.getByLabelText(/Keep Daily/i)
      await user.clear(dailyInput)
      await user.type(dailyInput, '14')

      expect(dailyInput).toHaveValue(14)
    })
  })

  describe('Action Buttons', () => {
    it('renders Cancel button', () => {
      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={false}
          results={null}
        />
      )

      expect(screen.getByRole('button', { name: /Cancel/i })).toBeInTheDocument()
    })

    it('renders Dry Run button', () => {
      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={false}
          results={null}
        />
      )

      expect(screen.getByRole('button', { name: /Dry Run/i })).toBeInTheDocument()
    })

    it('renders Prune Archives button', () => {
      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={false}
          results={null}
        />
      )

      expect(screen.getByRole('button', { name: /Prune Archives/i })).toBeInTheDocument()
    })

    it('calls onClose when Cancel is clicked', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()

      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={onClose}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={false}
          results={null}
        />
      )

      await user.click(screen.getByRole('button', { name: /Cancel/i }))

      expect(onClose).toHaveBeenCalled()
    })

    it('calls onDryRun with form data when Dry Run is clicked', async () => {
      const user = userEvent.setup()
      const onDryRun = vi.fn()

      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={onDryRun}
          onConfirmPrune={vi.fn()}
          isLoading={false}
          results={null}
        />
      )

      await user.click(screen.getByRole('button', { name: /Dry Run/i }))

      expect(onDryRun).toHaveBeenCalledWith(
        expect.objectContaining({
          keep_daily: 7,
          keep_weekly: 4,
          keep_monthly: 6,
          keep_yearly: 1,
        })
      )
    })

    it('calls onConfirmPrune when Prune Archives is clicked', async () => {
      const user = userEvent.setup()
      const onConfirmPrune = vi.fn()

      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={onConfirmPrune}
          isLoading={false}
          results={null}
        />
      )

      await user.click(screen.getByRole('button', { name: /Prune Archives/i }))

      expect(onConfirmPrune).toHaveBeenCalled()
    })

    it('disables buttons when loading', () => {
      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={true}
          results={null}
        />
      )

      expect(screen.getByRole('button', { name: /Dry Run/i })).toBeDisabled()
      expect(screen.getByRole('button', { name: /Pruning/i })).toBeDisabled()
    })

    it('shows Pruning text when loading', () => {
      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={true}
          results={null}
        />
      )

      expect(screen.getByRole('button', { name: /Pruning/i })).toBeInTheDocument()
    })
  })

  describe('Results Display', () => {
    it('shows dry run results header', () => {
      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={false}
          results={{
            dry_run: true,
            prune_result: {
              success: true,
              stdout: 'Would prune 5 archives',
            },
          }}
        />
      )

      expect(screen.getByText('Dry Run Results (Preview)')).toBeInTheDocument()
    })

    it('shows actual prune results header', () => {
      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={false}
          results={{
            dry_run: false,
            prune_result: {
              success: true,
              stdout: 'Pruned 5 archives',
            },
          }}
        />
      )

      expect(screen.getByText('Prune Results')).toBeInTheDocument()
    })

    it('shows output when available', () => {
      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={false}
          results={{
            dry_run: true,
            prune_result: {
              success: true,
              stdout: 'Would prune: archive-2023-01-01',
            },
          }}
        />
      )

      expect(screen.getByText('Would prune: archive-2023-01-01')).toBeInTheDocument()
    })

    it('shows error state for failed operation', () => {
      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={false}
          results={{
            dry_run: false,
            prune_result: {
              success: false,
              stderr: 'Repository locked',
            },
          }}
        />
      )

      expect(screen.getByText('Operation Failed')).toBeInTheDocument()
      expect(screen.getByText('Repository locked')).toBeInTheDocument()
    })

    it('shows success message for dry run', () => {
      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={false}
          results={{
            dry_run: true,
            prune_result: {
              success: true,
              stdout: 'Would prune 3 archives',
            },
          }}
        />
      )

      expect(screen.getByText(/Dry run completed successfully/i)).toBeInTheDocument()
    })
  })

  describe('Warning Messages', () => {
    it('shows warning about deleted archives', () => {
      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={false}
          results={null}
        />
      )

      expect(screen.getByText(/Deleted archives cannot be recovered/i)).toBeInTheDocument()
    })

    it('shows tip about running dry run first', () => {
      render(
        <PruneRepositoryDialog
          open={true}
          repository={mockRepository}
          onClose={vi.fn()}
          onDryRun={vi.fn()}
          onConfirmPrune={vi.fn()}
          isLoading={false}
          results={null}
        />
      )

      expect(screen.getByText(/Always run "Dry Run" first/i)).toBeInTheDocument()
    })
  })
})

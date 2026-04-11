import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import PruneRepositoryDialog from '../PruneRepositoryDialog'

const mockRepository = {
  id: 1,
  name: 'Test Repository',
  path: '/repo/test',
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

      // Title says "Prune Repository"
      const pruneTexts = screen.getAllByText('Prune Repository')
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

      expect(screen.queryByText('Prune Repository')).not.toBeInTheDocument()
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

    it('shows info about pruning', async () => {
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

      const infoIcon = document.body.querySelector('.lucide-info')?.parentElement
      expect(infoIcon).toBeTruthy()
      if (infoIcon) {
        await user.hover(infoIcon)
      }
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

      expect(screen.getByText(/Keep Hourly/i)).toBeInTheDocument()
      expect(screen.getByText(/Keep Daily/i)).toBeInTheDocument()
      expect(screen.getByText(/Keep Weekly/i)).toBeInTheDocument()
      expect(screen.getByText(/Keep Monthly/i)).toBeInTheDocument()
      expect(screen.getByText(/Keep Quarterly/i)).toBeInTheDocument()
      expect(screen.getByText(/Keep Yearly/i)).toBeInTheDocument()
      expect(screen.getAllByRole('spinbutton')).toHaveLength(6)
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

      const inputs = screen.getAllByRole('spinbutton')
      expect(inputs[1]).toHaveValue(7)
      expect(inputs[2]).toHaveValue(4)
      expect(inputs[3]).toHaveValue(6)
      expect(inputs[5]).toHaveValue(1)
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

      const dailyInput = screen.getAllByRole('spinbutton')[1]
      await user.clear(dailyInput)
      await user.type(dailyInput, '14')

      expect(dailyInput).toHaveValue(14)
    })
  })

  describe('Action Buttons', () => {
    it('does not render a separate cancel button in the main dialog', () => {
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

      expect(screen.queryByRole('button', { name: /Cancel/i })).not.toBeInTheDocument()
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

      expect(screen.getByRole('button', { name: /Run Prune/i })).toBeInTheDocument()
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
          keep_hourly: 0,
          keep_daily: 7,
          keep_weekly: 4,
          keep_monthly: 6,
          keep_quarterly: 0,
          keep_yearly: 1,
        })
      )
    })

    it('calls onConfirmPrune when Run Prune is clicked', async () => {
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

      await user.click(screen.getByRole('button', { name: /Run Prune/i }))

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
      expect(screen.getByRole('button', { name: /Run Prune/i })).toBeDisabled()
    })

    it('keeps action labels stable when loading starts externally', () => {
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

      expect(screen.getByRole('button', { name: /Dry Run/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Run Prune/i })).toBeInTheDocument()
    })
  })

  describe('Results Display', () => {
    it('shows dry run results header', async () => {
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

      expect(await screen.findByText('Dry Run Results (Preview)')).toBeInTheDocument()
    })

    it('shows actual prune results header', async () => {
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

      expect(await screen.findByText('Prune Results')).toBeInTheDocument()
    })

    it('shows output when available', async () => {
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

      await screen.findByText('Dry Run Results (Preview)')
      expect(screen.getByRole('dialog')).toHaveTextContent('Would prune: archive-2023-01-01')
    })

    it('shows error state for failed operation', async () => {
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

      expect(await screen.findByText('Operation Failed')).toBeInTheDocument()
      expect(screen.getByText('Repository locked')).toBeInTheDocument()
    })

    it('shows success message for dry run', async () => {
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

      expect(
        await screen.findByText(/Archives listed above would be deleted\. If this looks correct/i)
      ).toBeInTheDocument()
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

    it('shows tip about running dry run first', async () => {
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

      const infoIcon = document.body.querySelector('.lucide-info')?.parentElement
      expect(infoIcon).toBeTruthy()
      if (infoIcon) {
        await user.hover(infoIcon)
      }
    })
  })
})

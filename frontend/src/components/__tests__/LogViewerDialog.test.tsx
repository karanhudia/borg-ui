import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import LogViewerDialog from '../LogViewerDialog'

// Mock the TerminalLogViewer component
vi.mock('../TerminalLogViewer', () => ({
  TerminalLogViewer: ({ jobId, status, jobType }: { jobId: string; status: string; jobType: string }) => (
    <div data-testid="terminal-log-viewer">
      <span>Job ID: {jobId}</span>
      <span>Status: {status}</span>
      <span>Job Type: {jobType}</span>
    </div>
  ),
}))

// Mock StatusBadge component
vi.mock('../StatusBadge', () => ({
  default: ({ status }: { status: string }) => <div data-testid="status-badge">{status}</div>,
}))

describe('LogViewerDialog', () => {
  const mockJob = {
    id: 123,
    status: 'completed',
    type: 'backup',
  }

  describe('Dialog Visibility', () => {
    it('does not render when job is null', () => {
      const { container } = render(
        <LogViewerDialog job={null} open={true} onClose={vi.fn()} />
      )
      // Dialog exists but content should be minimal/hidden
      expect(container.querySelector('[role="dialog"]')).toBeNull()
    })

    it('renders when open is true and job is provided', () => {
      render(
        <LogViewerDialog job={mockJob} open={true} onClose={vi.fn()} />
      )
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
  })

  describe('Dialog Content', () => {
    it('displays job ID in title', () => {
      render(
        <LogViewerDialog job={mockJob} open={true} onClose={vi.fn()} />
      )
      expect(screen.getByText(/Job #123/)).toBeInTheDocument()
    })

    it('displays status badge', () => {
      render(
        <LogViewerDialog job={mockJob} open={true} onClose={vi.fn()} />
      )
      expect(screen.getByTestId('status-badge')).toBeInTheDocument()
      expect(screen.getByText('completed')).toBeInTheDocument()
    })

    it('renders TerminalLogViewer component', () => {
      render(
        <LogViewerDialog job={mockJob} open={true} onClose={vi.fn()} />
      )
      expect(screen.getByTestId('terminal-log-viewer')).toBeInTheDocument()
    })

    it('passes correct props to TerminalLogViewer', () => {
      render(
        <LogViewerDialog job={mockJob} open={true} onClose={vi.fn()} />
      )
      expect(screen.getByText('Job ID: 123')).toBeInTheDocument()
      expect(screen.getByText('Status: completed')).toBeInTheDocument()
      expect(screen.getByText('Job Type: backup')).toBeInTheDocument()
    })
  })

  describe('Job Type Labels', () => {
    it('displays default Backup label when no type provided', () => {
      const jobWithoutType = { id: 1, status: 'completed' }
      render(
        <LogViewerDialog job={jobWithoutType} open={true} onClose={vi.fn()} />
      )
      expect(screen.getByText(/Backup Logs/)).toBeInTheDocument()
    })

    it('displays Restore label for restore jobs', () => {
      const restoreJob = { ...mockJob, type: 'restore' }
      render(
        <LogViewerDialog job={restoreJob} open={true} onClose={vi.fn()} />
      )
      expect(screen.getByText(/Restore Logs/)).toBeInTheDocument()
    })

    it('displays Check label for check jobs', () => {
      const checkJob = { ...mockJob, type: 'check' }
      render(
        <LogViewerDialog job={checkJob} open={true} onClose={vi.fn()} />
      )
      expect(screen.getByText(/Check Logs/)).toBeInTheDocument()
    })

    it('displays Compact label for compact jobs', () => {
      const compactJob = { ...mockJob, type: 'compact' }
      render(
        <LogViewerDialog job={compactJob} open={true} onClose={vi.fn()} />
      )
      expect(screen.getByText(/Compact Logs/)).toBeInTheDocument()
    })

    it('displays Prune label for prune jobs', () => {
      const pruneJob = { ...mockJob, type: 'prune' }
      render(
        <LogViewerDialog job={pruneJob} open={true} onClose={vi.fn()} />
      )
      expect(screen.getByText(/Prune Logs/)).toBeInTheDocument()
    })

    it('displays Package label for package jobs', () => {
      const packageJob = { ...mockJob, type: 'package' }
      render(
        <LogViewerDialog job={packageJob} open={true} onClose={vi.fn()} />
      )
      expect(screen.getByText(/Package Logs/)).toBeInTheDocument()
    })

    it('uses custom jobTypeLabel when provided', () => {
      render(
        <LogViewerDialog
          job={mockJob}
          open={true}
          onClose={vi.fn()}
          jobTypeLabel="Custom Job Type"
        />
      )
      expect(screen.getByText(/Custom Job Type Logs/)).toBeInTheDocument()
    })

    it('capitalizes unknown job types', () => {
      const unknownJob = { ...mockJob, type: 'custom' }
      render(
        <LogViewerDialog job={unknownJob} open={true} onClose={vi.fn()} />
      )
      expect(screen.getByText(/Custom Logs/)).toBeInTheDocument()
    })
  })

  describe('Dialog Actions', () => {
    it('displays close button', () => {
      render(
        <LogViewerDialog job={mockJob} open={true} onClose={vi.fn()} />
      )
      expect(screen.getByRole('button', { name: /close/i })).toBeInTheDocument()
    })

    it('calls onClose when close button is clicked', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()
      render(
        <LogViewerDialog job={mockJob} open={true} onClose={onClose} />
      )

      const closeButton = screen.getByRole('button', { name: /close/i })
      await user.click(closeButton)

      expect(onClose).toHaveBeenCalledTimes(1)
    })
  })

  describe('Edge Cases', () => {
    it('handles string job IDs', () => {
      const jobWithStringId = { ...mockJob, id: 'job-abc-123' }
      render(
        <LogViewerDialog job={jobWithStringId} open={true} onClose={vi.fn()} />
      )
      expect(screen.getByText(/Job #job-abc-123/)).toBeInTheDocument()
    })

    it('handles jobs with different statuses', () => {
      const runningJob = { ...mockJob, status: 'running' }
      render(
        <LogViewerDialog job={runningJob} open={true} onClose={vi.fn()} />
      )
      expect(screen.getByText('running')).toBeInTheDocument()
    })
  })
})

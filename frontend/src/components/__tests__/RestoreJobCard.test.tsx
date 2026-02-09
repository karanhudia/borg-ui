import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import RestoreJobCard from '../RestoreJobCard'

describe('RestoreJobCard', () => {
  const baseJob = {
    id: 1,
    repository: '/path/to/repo',
    destination: '/restore/path',
  }

  describe('Job ID display', () => {
    it('shows job ID when showJobId is true', () => {
      const job = { ...baseJob, archive: 'backup-2024-01-15', status: 'completed' }
      render(<RestoreJobCard job={job} showJobId={true} />)

      expect(screen.getByText('Restore Job #1')).toBeInTheDocument()
    })

    it('hides job ID when showJobId is false', () => {
      const job = { ...baseJob, archive: 'backup-2024-01-15', status: 'completed' }
      render(<RestoreJobCard job={job} showJobId={false} />)

      expect(screen.queryByText('Restore Job #1')).not.toBeInTheDocument()
    })

    it('shows job ID by default when showJobId is not provided', () => {
      const job = { ...baseJob, archive: 'backup-2024-01-15', status: 'completed' }
      render(<RestoreJobCard job={job} />)

      expect(screen.getByText('Restore Job #1')).toBeInTheDocument()
    })
  })

  describe('Archive name formatting', () => {
    it('displays archive name without timestamp', () => {
      const job = {
        ...baseJob,
        archive: 'Downloads Backup-2026-02-09T03:01:22.066',
        status: 'completed',
      }
      render(<RestoreJobCard job={job} />)

      expect(screen.getByText('Downloads Backup')).toBeInTheDocument()
      expect(screen.queryByText('-2026-02-09T03:01:22.066')).not.toBeInTheDocument()
    })

    it('displays archive name as-is when no timestamp present', () => {
      const job = { ...baseJob, archive: 'my-backup', status: 'completed' }
      render(<RestoreJobCard job={job} />)

      expect(screen.getByText('my-backup')).toBeInTheDocument()
    })

    it('handles archive name with multiple timestamps', () => {
      const job = {
        ...baseJob,
        archive: 'backup-2024-01-01T00:00:00.000-2026-02-09T03:01:22.066',
        status: 'completed',
      }
      render(<RestoreJobCard job={job} />)

      // Should remove the last timestamp pattern
      expect(screen.getByText(/backup-2024-01-01T00:00:00.000/)).toBeInTheDocument()
    })
  })

  describe('Destination display', () => {
    it('displays destination path in monospace', () => {
      const job = {
        ...baseJob,
        archive: 'backup',
        status: 'completed',
        destination: '/Users/karanhudia/Documents',
      }
      render(<RestoreJobCard job={job} />)

      const destinationElement = screen.getByText('/Users/karanhudia/Documents')
      expect(destinationElement).toBeInTheDocument()
      expect(destinationElement).toHaveStyle({ fontFamily: 'monospace' })
    })

    it('displays arrow separator between archive and destination', () => {
      const job = { ...baseJob, archive: 'backup', status: 'completed' }
      render(<RestoreJobCard job={job} />)

      expect(screen.getByText('→')).toBeInTheDocument()
    })
  })

  describe('Completed status', () => {
    it('displays completed status with checkmark', () => {
      const job = {
        ...baseJob,
        archive: 'backup',
        status: 'completed',
        started_at: '2024-01-15T10:00:00Z',
        completed_at: '2024-01-15T10:30:00Z',
      }
      render(<RestoreJobCard job={job} />)

      expect(screen.getByText('✓ Completed')).toBeInTheDocument()
    })

    it('does not display CheckCircle icon for completed status', () => {
      const job = {
        ...baseJob,
        archive: 'backup',
        status: 'completed',
        completed_at: '2024-01-15T10:30:00Z',
      }
      const { container } = render(<RestoreJobCard job={job} />)

      // CheckCircle icon should not be present
      const icons = container.querySelectorAll('svg')
      expect(icons.length).toBe(0)
    })

    it('displays relative time when completed', () => {
      const job = {
        ...baseJob,
        archive: 'backup',
        status: 'completed',
        completed_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(), // 2 hours ago
      }
      render(<RestoreJobCard job={job} />)

      // formatRelativeTime should show something like "2 hours ago"
      expect(screen.getByText(/ago/)).toBeInTheDocument()
    })

    it('displays duration when started_at and completed_at are present', () => {
      const job = {
        ...baseJob,
        archive: 'backup',
        status: 'completed',
        started_at: '2024-01-15T10:00:00Z',
        completed_at: '2024-01-15T10:05:00Z',
      }
      render(<RestoreJobCard job={job} />)

      // Should show bullet separator and duration with "Duration:" prefix
      expect(screen.getByText('•')).toBeInTheDocument()
      expect(screen.getByText(/Duration:/)).toBeInTheDocument()
    })

    it('hides duration when it is 0 sec', () => {
      const job = {
        ...baseJob,
        archive: 'backup',
        status: 'completed',
        started_at: '2024-01-15T10:00:00Z',
        completed_at: '2024-01-15T10:00:00Z', // Same time = 0 duration
      }
      render(<RestoreJobCard job={job} />)

      // Should not show bullet or duration
      expect(screen.queryByText('•')).not.toBeInTheDocument()
      expect(screen.queryByText(/Duration:/)).not.toBeInTheDocument()
    })
  })

  describe('Running status', () => {
    it('displays running status with pulsing indicator', () => {
      const job = {
        ...baseJob,
        archive: 'backup',
        status: 'running',
        started_at: '2024-01-15T10:00:00Z',
      }
      render(<RestoreJobCard job={job} />)

      expect(screen.getByText('Restoring files...')).toBeInTheDocument()
    })

    it('displays RefreshCw icon for running status', () => {
      const job = {
        ...baseJob,
        archive: 'backup',
        status: 'running',
        started_at: '2024-01-15T10:00:00Z',
      }
      const { container } = render(<RestoreJobCard job={job} />)

      // Should have spinning icon
      const icons = container.querySelectorAll('svg')
      expect(icons.length).toBeGreaterThan(0)
    })

    it('displays progress details when available', () => {
      const job = {
        ...baseJob,
        archive: 'backup',
        status: 'running',
        started_at: '2024-01-15T10:00:00Z',
        progress_details: {
          nfiles: 1500,
          current_file: '/home/user/documents/file.txt',
          progress_percent: 45.5,
          restore_speed: 10.5,
          estimated_time_remaining: 120,
        },
      }
      render(<RestoreJobCard job={job} />)

      expect(screen.getByText('Files Restored:')).toBeInTheDocument()
      expect(screen.getByText('1,500')).toBeInTheDocument()
      expect(screen.getByText('Progress:')).toBeInTheDocument()
      expect(screen.getByText('45.5%')).toBeInTheDocument()
      expect(screen.getByText('Speed:')).toBeInTheDocument()
      expect(screen.getByText('10.50 MB/s')).toBeInTheDocument()
      expect(screen.getByText('ETA:')).toBeInTheDocument()
    })

    it('displays current file being restored', () => {
      const job = {
        ...baseJob,
        archive: 'backup',
        status: 'running',
        started_at: '2024-01-15T10:00:00Z',
        progress_details: {
          nfiles: 100,
          current_file: '/home/user/documents/important.pdf',
          progress_percent: 50,
          restore_speed: 5.0,
          estimated_time_remaining: 60,
        },
      }
      render(<RestoreJobCard job={job} />)

      expect(screen.getByText('Current File:')).toBeInTheDocument()
      expect(screen.getByText('/home/user/documents/important.pdf')).toBeInTheDocument()
    })

    it('does not show ETA when estimated_time_remaining is 0', () => {
      const job = {
        ...baseJob,
        archive: 'backup',
        status: 'running',
        started_at: '2024-01-15T10:00:00Z',
        progress_details: {
          nfiles: 100,
          current_file: '/some/file.txt',
          progress_percent: 50,
          restore_speed: 5.0,
          estimated_time_remaining: 0,
        },
      }
      render(<RestoreJobCard job={job} />)

      expect(screen.queryByText('ETA:')).not.toBeInTheDocument()
    })

    it('handles missing progress_details gracefully', () => {
      const job = {
        ...baseJob,
        archive: 'backup',
        status: 'running',
        started_at: '2024-01-15T10:00:00Z',
      }
      render(<RestoreJobCard job={job} />)

      expect(screen.getByText('Restoring files...')).toBeInTheDocument()
      expect(screen.queryByText('Files Restored:')).not.toBeInTheDocument()
    })
  })

  describe('Failed status', () => {
    it('displays error message for failed jobs', () => {
      const job = {
        ...baseJob,
        archive: 'backup',
        status: 'failed',
        error_message: 'Disk full - cannot restore files',
      }
      render(<RestoreJobCard job={job} />)

      expect(screen.getByText('Disk full - cannot restore files')).toBeInTheDocument()
    })

    it('displays AlertCircle icon for failed status', () => {
      const job = {
        ...baseJob,
        archive: 'backup',
        status: 'failed',
        error_message: 'Error occurred',
      }
      const { container } = render(<RestoreJobCard job={job} />)

      const icons = container.querySelectorAll('svg')
      expect(icons.length).toBeGreaterThan(0)
    })

    it('does not display error alert when error_message is missing', () => {
      const job = {
        ...baseJob,
        archive: 'backup',
        status: 'failed',
      }
      render(<RestoreJobCard job={job} />)

      // Should not have error alert
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    })
  })

  describe('Other statuses', () => {
    it('displays Clock icon for pending status', () => {
      const job = {
        ...baseJob,
        archive: 'backup',
        status: 'pending',
      }
      const { container } = render(<RestoreJobCard job={job} />)

      const icons = container.querySelectorAll('svg')
      expect(icons.length).toBeGreaterThan(0)
    })
  })

  describe('Edge cases', () => {
    it('handles job without started_at or completed_at', () => {
      const job = {
        ...baseJob,
        archive: 'backup',
        status: 'completed',
      }
      render(<RestoreJobCard job={job} />)

      // Without completed_at, the completed status section is not rendered
      expect(screen.queryByText('✓ Completed')).not.toBeInTheDocument()
      // But the job info should still be displayed
      expect(screen.getByText('backup')).toBeInTheDocument()
    })

    it('handles very long destination paths', () => {
      const job = {
        ...baseJob,
        archive: 'backup',
        status: 'completed',
        destination: '/very/long/path/that/goes/on/and/on/and/on/and/on/to/test/wrapping/behavior',
      }
      render(<RestoreJobCard job={job} />)

      const destinationElement = screen.getByText(job.destination)
      expect(destinationElement).toBeInTheDocument()
    })

    it('handles job with progress but no progress_details', () => {
      const job = {
        ...baseJob,
        archive: 'backup',
        status: 'running',
        progress: 50,
      }
      render(<RestoreJobCard job={job} />)

      expect(screen.getByText('Restoring files...')).toBeInTheDocument()
    })
  })
})

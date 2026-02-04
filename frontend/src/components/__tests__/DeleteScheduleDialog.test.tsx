import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import DeleteScheduleDialog from '../DeleteScheduleDialog'

describe('DeleteScheduleDialog', () => {
  const mockJob = {
    id: 1,
    name: 'Test Schedule',
    cron_expression: '0 2 * * *',
    repository: null,
    repository_id: null,
    repository_ids: [1],
    enabled: true,
    last_run: null,
    next_run: '2024-01-01T02:00:00Z',
    created_at: '2023-12-01T00:00:00Z',
    updated_at: null,
    description: 'Test description',
    archive_name_template: '{job_name}-{now}',
    run_repository_scripts: false,
    pre_backup_script_id: null,
    post_backup_script_id: null,
    run_prune_after: true,
    run_compact_after: false,
    prune_keep_hourly: 0,
    prune_keep_daily: 7,
    prune_keep_weekly: 4,
    prune_keep_monthly: 6,
    prune_keep_quarterly: 0,
    prune_keep_yearly: 1,
    last_prune: null,
    last_compact: null,
  }

  it('renders when open', () => {
    const onClose = vi.fn()
    const onConfirm = vi.fn()

    render(
      <DeleteScheduleDialog
        open={true}
        job={mockJob}
        onClose={onClose}
        onConfirm={onConfirm}
        isDeleting={false}
      />
    )

    expect(screen.getByText('Delete Scheduled Job')).toBeInTheDocument()
    expect(screen.getByText(/Are you sure you want to delete/i)).toBeInTheDocument()
    expect(screen.getByText(/"Test Schedule"/i)).toBeInTheDocument()
  })

  it('does not render when closed', () => {
    const onClose = vi.fn()
    const onConfirm = vi.fn()

    render(
      <DeleteScheduleDialog
        open={false}
        job={mockJob}
        onClose={onClose}
        onConfirm={onConfirm}
        isDeleting={false}
      />
    )

    expect(screen.queryByText('Delete Scheduled Job')).not.toBeInTheDocument()
  })

  it('displays job name in dialog', () => {
    const onClose = vi.fn()
    const onConfirm = vi.fn()

    render(
      <DeleteScheduleDialog
        open={true}
        job={mockJob}
        onClose={onClose}
        onConfirm={onConfirm}
        isDeleting={false}
      />
    )

    expect(screen.getByText(/"Test Schedule"/i)).toBeInTheDocument()
  })

  it('calls onClose when Cancel button is clicked', () => {
    const onClose = vi.fn()
    const onConfirm = vi.fn()

    render(
      <DeleteScheduleDialog
        open={true}
        job={mockJob}
        onClose={onClose}
        onConfirm={onConfirm}
        isDeleting={false}
      />
    )

    const cancelButton = screen.getByRole('button', { name: /cancel/i })
    fireEvent.click(cancelButton)

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('calls onConfirm when Delete button is clicked', () => {
    const onClose = vi.fn()
    const onConfirm = vi.fn()

    render(
      <DeleteScheduleDialog
        open={true}
        job={mockJob}
        onClose={onClose}
        onConfirm={onConfirm}
        isDeleting={false}
      />
    )

    const deleteButton = screen.getByRole('button', { name: /delete job/i })
    fireEvent.click(deleteButton)

    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onClose).not.toHaveBeenCalled()
  })

  it('shows loading state when isDeleting is true', () => {
    const onClose = vi.fn()
    const onConfirm = vi.fn()

    render(
      <DeleteScheduleDialog
        open={true}
        job={mockJob}
        onClose={onClose}
        onConfirm={onConfirm}
        isDeleting={true}
      />
    )

    expect(screen.getByText(/deleting\.\.\./i)).toBeInTheDocument()
  })

  it('disables delete button when isDeleting is true', () => {
    const onClose = vi.fn()
    const onConfirm = vi.fn()

    render(
      <DeleteScheduleDialog
        open={true}
        job={mockJob}
        onClose={onClose}
        onConfirm={onConfirm}
        isDeleting={true}
      />
    )

    const deleteButton = screen.getByRole('button', { name: /deleting\.\.\./i })
    expect(deleteButton).toBeDisabled()
  })

  it('shows warning message about action being irreversible', () => {
    const onClose = vi.fn()
    const onConfirm = vi.fn()

    render(
      <DeleteScheduleDialog
        open={true}
        job={mockJob}
        onClose={onClose}
        onConfirm={onConfirm}
        isDeleting={false}
      />
    )

    expect(screen.getByText(/this action cannot be undone/i)).toBeInTheDocument()
  })

  it('handles null job gracefully', () => {
    const onClose = vi.fn()
    const onConfirm = vi.fn()

    render(
      <DeleteScheduleDialog
        open={true}
        job={null}
        onClose={onClose}
        onConfirm={onConfirm}
        isDeleting={false}
      />
    )

    expect(screen.getByText('Delete Scheduled Job')).toBeInTheDocument()
  })

  it('renders dialog with title and buttons', () => {
    const onClose = vi.fn()
    const onConfirm = vi.fn()

    render(
      <DeleteScheduleDialog
        open={true}
        job={mockJob}
        onClose={onClose}
        onConfirm={onConfirm}
        isDeleting={false}
      />
    )

    // Check that key dialog elements are rendered
    expect(screen.getByText('Delete Scheduled Job')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /delete job/i })).toBeInTheDocument()
  })
})

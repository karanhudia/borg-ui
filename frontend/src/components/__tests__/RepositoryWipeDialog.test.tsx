import { describe, expect, it, vi } from 'vitest'
import type { ComponentProps } from 'react'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../test/test-utils'
import RepositoryWipeDialog from '../RepositoryWipeDialog'
import type { Repository, RepositoryWipeJob } from '../../types'

const repository: Repository = {
  id: 7,
  name: 'Primary',
  path: '/srv/borg/primary',
  borg_version: 2,
  archive_count: 2,
  total_size: '18.4 GB',
  last_backup: '2026-05-17T21:15:00Z',
}

const preview: RepositoryWipeJob = {
  id: 11,
  repository_id: 7,
  status: 'previewed',
  phase: 'preview',
  archive_count: 2,
  archive_fingerprint: 'sha256:abc',
  run_compact: true,
  progress: 0,
  progress_message: 'Wipe preview generated',
  has_logs: false,
  blocked: false,
  blocking_reason: null,
  protected_archives: [],
  dry_run_output: 'Would delete archive-a\nWould delete archive-b',
  archives: [
    {
      identity: 'archive-id-a',
      name: 'archive-a',
      time: '2026-05-17T20:00:00Z',
      id: 'archive-id-a',
    },
    {
      identity: 'archive-id-b',
      name: 'archive-b',
      time: '2026-05-17T21:00:00Z',
      id: 'archive-id-b',
    },
  ],
}

function renderDialog(overrides: Partial<ComponentProps<typeof RepositoryWipeDialog>> = {}) {
  const props = {
    open: true,
    repository,
    preview: null,
    job: null,
    isPreviewLoading: false,
    isExecuteLoading: false,
    onClose: vi.fn(),
    onGeneratePreview: vi.fn(),
    onExecute: vi.fn(),
    onCancelPreview: vi.fn(),
    ...overrides,
  }

  renderWithProviders(<RepositoryWipeDialog {...props} />)
  return props
}

describe('RepositoryWipeDialog', () => {
  it('shows BOR-31 scope copy and requests a compact-enabled preview by default', async () => {
    const user = userEvent.setup()
    const props = renderDialog()

    expect(screen.getByRole('heading', { name: 'Wipe repository contents' })).toBeInTheDocument()
    expect(
      screen.getByText(
        /This will delete every archive in this repository\. The repository configuration will remain/
      )
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Wipe all archives' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Generate wipe preview' }))

    expect(props.onGeneratePreview).toHaveBeenCalledWith(true)
  })

  it('requires both acknowledgement and exact typed phrase before execution', async () => {
    const user = userEvent.setup()
    const props = renderDialog({ preview })

    expect(screen.getByText('archive-a')).toBeInTheDocument()
    expect(screen.getByText('archive-b')).toBeInTheDocument()
    expect(screen.getByText('Would delete archive-a')).toBeInTheDocument()

    const finalButton = screen.getByRole('button', { name: 'Wipe all archives' })
    expect(finalButton).toBeDisabled()

    await user.click(
      screen.getByRole('checkbox', {
        name: 'I understand this removes every archive and restore point in this repository',
      })
    )
    await user.type(screen.getByLabelText('Type WIPE Primary to confirm'), 'wipe Primary')
    expect(screen.getByText('The confirmation phrase must match exactly.')).toBeInTheDocument()
    expect(finalButton).toBeDisabled()

    await user.clear(screen.getByLabelText('Type WIPE Primary to confirm'))
    await user.type(screen.getByLabelText('Type WIPE Primary to confirm'), 'WIPE Primary')
    expect(finalButton).toBeEnabled()

    await user.click(finalButton)

    expect(props.onExecute).toHaveBeenCalledWith({
      preview_id: 11,
      preview_fingerprint: 'sha256:abc',
      confirmation_phrase: 'WIPE Primary',
      understood: true,
      run_compact: true,
    })
  })

  it('blocks execution for empty and protected previews', () => {
    const emptyPreview: RepositoryWipeJob = {
      ...preview,
      id: 12,
      archive_count: 0,
      archives: [],
      dry_run_output: '',
    }
    const { rerender } = renderWithProviders(
      <RepositoryWipeDialog
        open
        repository={repository}
        preview={emptyPreview}
        job={null}
        isPreviewLoading={false}
        isExecuteLoading={false}
        onClose={vi.fn()}
        onGeneratePreview={vi.fn()}
        onExecute={vi.fn()}
        onCancelPreview={vi.fn()}
      />
    )

    expect(
      screen.getByText('No archives were found in this repository. There is nothing to wipe.')
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Wipe all archives' })).toBeDisabled()

    rerender(
      <RepositoryWipeDialog
        open
        repository={repository}
        preview={{
          ...preview,
          blocked: true,
          blocking_reason: 'protected_archives',
          protected_archives: ['protected-archive'],
        }}
        job={null}
        isPreviewLoading={false}
        isExecuteLoading={false}
        onClose={vi.fn()}
        onGeneratePreview={vi.fn()}
        onExecute={vi.fn()}
        onCancelPreview={vi.fn()}
      />
    )

    expect(screen.getByText(/Protected archives prevent this wipe/)).toBeInTheDocument()
    expect(screen.getByText('protected-archive')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Wipe all archives' })).toBeDisabled()
  })

  it('shows stale preview and terminal job recovery states', () => {
    const stalePreview: RepositoryWipeJob = { ...preview, phase: 'stale' }
    const { rerender } = renderWithProviders(
      <RepositoryWipeDialog
        open
        repository={repository}
        preview={stalePreview}
        job={null}
        isPreviewLoading={false}
        isExecuteLoading={false}
        onClose={vi.fn()}
        onGeneratePreview={vi.fn()}
        onExecute={vi.fn()}
        onCancelPreview={vi.fn()}
      />
    )

    expect(
      screen.getByText(
        'The archive list changed after this preview was generated. Generate a new preview before wiping contents.'
      )
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Wipe all archives' })).toBeDisabled()

    rerender(
      <RepositoryWipeDialog
        open
        repository={repository}
        preview={preview}
        job={{
          ...preview,
          status: 'completed_compaction_failed',
          phase: 'compact_failed',
          progress: 100,
          progress_message: 'Repository contents wipe completed',
          error_message: 'compact failed',
        }}
        isPreviewLoading={false}
        isExecuteLoading={false}
        onClose={vi.fn()}
        onGeneratePreview={vi.fn()}
        onExecute={vi.fn()}
        onCancelPreview={vi.fn()}
      />
    )

    const status = screen.getByRole('status')
    expect(
      within(status).getByText(
        'Archives were deleted, but compact failed. Run compact later to reclaim space.'
      )
    ).toBeInTheDocument()
  })
})

import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/test-utils'
import WizardStepRestoreDestination from '../WizardStepRestoreDestination'

describe('WizardStepRestoreDestination', () => {
  const selectedItems = [{ path: 'home/username/folder1/folder2', type: 'directory' as const }]

  it('previews preserved archive path for custom restores by default', () => {
    renderWithProviders(
      <WizardStepRestoreDestination
        data={{
          destinationType: 'local',
          destinationConnectionId: '',
          restoreStrategy: 'custom',
          customPath: '/recovery/folder1/folder2',
          restoreLayout: 'preserve_path',
          existingFiles: 'refuse',
        }}
        selectedItems={selectedItems}
        sshConnections={[]}
        repositoryType="local"
        onChange={vi.fn()}
        onBrowsePath={vi.fn()}
      />
    )

    expect(screen.getByText('Preserve archive path')).toBeInTheDocument()
    expect(screen.getByText('Restore selected contents here')).toBeInTheDocument()
    expect(
      screen.getByText('/recovery/folder1/folder2/home/username/folder1/folder2')
    ).toBeInTheDocument()
  })

  it('previews contents-only directory restores without appending the archive path', () => {
    renderWithProviders(
      <WizardStepRestoreDestination
        data={{
          destinationType: 'local',
          destinationConnectionId: '',
          restoreStrategy: 'custom',
          customPath: '/recovery/folder1/folder2',
          restoreLayout: 'contents_only',
          existingFiles: 'refuse',
        }}
        selectedItems={selectedItems}
        sshConnections={[]}
        repositoryType="local"
        onChange={vi.fn()}
        onBrowsePath={vi.fn()}
      />
    )

    expect(screen.getByText('/recovery/folder1/folder2', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('(contents)')).toBeInTheDocument()
    expect(
      screen.queryByText('/recovery/folder1/folder2/home/username/folder1/folder2')
    ).not.toBeInTheDocument()
  })

  it('emits restore layout changes from the layout options', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    renderWithProviders(
      <WizardStepRestoreDestination
        data={{
          destinationType: 'local',
          destinationConnectionId: '',
          restoreStrategy: 'custom',
          customPath: '/recovery/folder1/folder2',
          restoreLayout: 'preserve_path',
          existingFiles: 'refuse',
        }}
        selectedItems={selectedItems}
        sshConnections={[]}
        repositoryType="local"
        onChange={onChange}
        onBrowsePath={vi.fn()}
      />
    )

    await user.click(screen.getByText('Restore selected contents here'))

    expect(onChange).toHaveBeenCalledWith({ restoreLayout: 'contents_only' })
  })

  describe('existing files (#1261)', () => {
    const renderStep = (
      overrides: Partial<{
        restoreStrategy: 'original' | 'custom'
        existingFiles: 'refuse' | 'continue' | null
      }> = {},
      borgVersion: 1 | 2 = 2,
      onChange = vi.fn()
    ) =>
      renderWithProviders(
        <WizardStepRestoreDestination
          data={{
            destinationType: 'local',
            destinationConnectionId: '',
            restoreStrategy: 'custom',
            customPath: '/recovery',
            restoreLayout: 'preserve_path',
            existingFiles: 'refuse',
            ...overrides,
          }}
          borgVersion={borgVersion}
          selectedItems={selectedItems}
          sshConnections={[]}
          repositoryType="local"
          onChange={onChange}
          onBrowsePath={vi.fn()}
        />
      )

    it('offers Borg 2 the exact restore, selected, and the restore into existing files', () => {
      renderStep()

      expect(screen.getByRole('radio', { name: /Exact restore \(empty directory\)/ })).toBeChecked()
      expect(screen.getByRole('radio', { name: /Restore into existing files/ })).not.toBeChecked()
      expect(screen.queryByText(/is not repaired/)).not.toBeInTheDocument()
    })

    it('states the caveat once the restore into existing files is chosen', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      const { rerender } = renderStep({}, 2, onChange)

      await user.click(screen.getByText('Restore into existing files'))
      expect(onChange).toHaveBeenCalledWith({ existingFiles: 'continue' })

      rerender(
        <WizardStepRestoreDestination
          data={{
            destinationType: 'local',
            destinationConnectionId: '',
            restoreStrategy: 'custom',
            customPath: '/recovery',
            restoreLayout: 'preserve_path',
            existingFiles: 'continue',
          }}
          borgVersion={2}
          selectedItems={selectedItems}
          sshConnections={[]}
          repositoryType="local"
          onChange={onChange}
          onBrowsePath={vi.fn()}
        />
      )
      expect(screen.getByText(/is not repaired/)).toBeInTheDocument()
    })

    it('makes the original location wait for an explicit choice', () => {
      renderStep({ restoreStrategy: 'original', existingFiles: null })

      expect(screen.getByRole('radio', { name: /Exact restore/ })).toBeDisabled()
      expect(screen.getByRole('radio', { name: /Restore into existing files/ })).not.toBeChecked()
      expect(screen.getByText(/To restore to the original location/)).toBeInTheDocument()
    })

    it('tells Borg 1 what happens to existing files, without a choice', () => {
      renderStep({}, 1)

      expect(screen.getByText(/Files at the same path are overwritten/)).toBeInTheDocument()
      expect(screen.queryByText('Restore into existing files')).not.toBeInTheDocument()
    })
  })
})

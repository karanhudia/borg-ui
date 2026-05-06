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
})

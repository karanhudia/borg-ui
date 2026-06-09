import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../../test/test-utils'
import AdvancedRepositoryOptions from '../AdvancedRepositoryOptions'

vi.mock('../RepositoryScriptsSection', () => ({
  default: () => <div data-testid="repository-scripts-section" />,
}))

vi.mock('../ScriptEditorDialog', () => ({
  default: () => null,
}))

const renderOptions = (props = {}) =>
  renderWithProviders(
    <AdvancedRepositoryOptions
      repositoryId={null}
      mode="full"
      remotePath=""
      preBackupScript=""
      postBackupScript=""
      preHookTimeout={300}
      postHookTimeout={300}
      hookFailureMode="fail"
      customFlags=""
      uploadRatelimitMb=""
      onRemotePathChange={vi.fn()}
      onPreBackupScriptChange={vi.fn()}
      onPostBackupScriptChange={vi.fn()}
      onPreHookTimeoutChange={vi.fn()}
      onPostHookTimeoutChange={vi.fn()}
      onHookFailureModeChange={vi.fn()}
      onCustomFlagsChange={vi.fn()}
      onUploadRatelimitMbChange={vi.fn()}
      {...props}
    />
  )

describe('AdvancedRepositoryOptions', () => {
  it('renders upload speed limit as an optional MB/s field', () => {
    renderOptions({ uploadRatelimitMb: '1.5' })

    expect(screen.getByLabelText(/Upload speed limit/i)).toHaveValue(1.5)
    expect(screen.getByText(/MB\/s/i)).toBeInTheDocument()
  })

  it('emits upload speed limit edits', async () => {
    const user = userEvent.setup()
    const onUploadRatelimitMbChange = vi.fn()
    renderOptions({ onUploadRatelimitMbChange })

    await user.type(screen.getByLabelText(/Upload speed limit/i), '2')

    expect(onUploadRatelimitMbChange).toHaveBeenLastCalledWith('2')
  })
})

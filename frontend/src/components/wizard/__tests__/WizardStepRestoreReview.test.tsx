import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import WizardStepRestoreReview from '../WizardStepRestoreReview'

describe('WizardStepRestoreReview', () => {
  it('shows the contents-only restore layout and exact destination path', () => {
    renderWithProviders(
      <WizardStepRestoreReview
        data={{
          destinationType: 'local',
          destinationConnectionId: '',
          restoreStrategy: 'custom',
          customPath: '/recovery/folder1/folder2',
          restoreLayout: 'contents_only',
        }}
        selectedFiles={[
          {
            path: 'home/username/folder1/folder2',
            type: 'directory',
            mode: '',
            user: '',
            group: '',
            size: 0,
            mtime: '',
            healthy: true,
          },
        ]}
        sshConnections={[]}
        archiveName="archive-1"
      />
    )

    expect(screen.getByText('Restore selected contents here')).toBeInTheDocument()
    expect(
      screen.getAllByText('/recovery/folder1/folder2', { exact: false }).length
    ).toBeGreaterThan(0)
    expect(
      screen.queryByText('/recovery/folder1/folder2/home/username/folder1/folder2')
    ).not.toBeInTheDocument()
  })
})

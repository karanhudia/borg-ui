import { describe, expect, it, vi } from 'vitest'

import { renderWithProviders, screen, userEvent } from '../../../test/test-utils'
import AppFolderList from '../AppFolderList'
import { immichStats, immichTemplate } from '../appTemplates.fixtures'

function renderList(appFolderIncluded: boolean) {
  const onAppFolderIncludedChange = vi.fn()
  const onSkippedChange = vi.fn()
  renderWithProviders(
    <AppFolderList
      template={immichTemplate}
      appFolderIncluded={appFolderIncluded}
      onAppFolderIncludedChange={onAppFolderIncludedChange}
      extras={[]}
      includedExtras={[]}
      onIncludedExtrasChange={() => {}}
      user="backup"
      stats={immichStats}
      measuring={false}
      skipped={['thumbs', 'encoded-video']}
      onSkippedChange={onSkippedChange}
    />
  )
  const backUpBoxes = () => screen.getAllByRole('checkbox', { name: 'Back up' })
  return { onAppFolderIncludedChange, onSkippedChange, backUpBoxes }
}

describe('AppFolderList', () => {
  it('shows every app row unticked when the app folder was removed', () => {
    const { backUpBoxes } = renderList(false)
    expect(backUpBoxes().every((box) => !(box as HTMLInputElement).checked)).toBe(true)
    expect(screen.getByText('About 0 B will be backed up.')).toBeInTheDocument()
  })

  it('brings the app folder back with only the ticked part', async () => {
    const user = userEvent.setup()
    const { onAppFolderIncludedChange, onSkippedChange, backUpBoxes } = renderList(false)

    // Rows: upload, (library missing: no box), profile, backups, thumbs, encoded-video.
    await user.click(backUpBoxes()[0])

    expect(onAppFolderIncludedChange).toHaveBeenCalledWith(true)
    expect(onSkippedChange).toHaveBeenCalledWith([
      'library',
      'profile',
      'backups',
      'thumbs',
      'encoded-video',
    ])
  })

  it('lets any folder be unticked, not only rebuildable ones', async () => {
    const user = userEvent.setup()
    const { onSkippedChange, backUpBoxes } = renderList(true)

    await user.click(backUpBoxes()[0])

    expect(onSkippedChange).toHaveBeenCalledWith(['thumbs', 'encoded-video', 'upload'])
  })
})

describe('AppFolderList dumps the template makes itself', () => {
  it('does not warn about a missing dump Borg UI writes before each backup', () => {
    const template = {
      ...immichTemplate,
      folders: immichTemplate.folders.map((folder) =>
        folder.role === 'database' ? { ...folder, made_before_backup: true } : folder
      ),
    }
    const dumpPath = template.folders.find((folder) => folder.role === 'database')!.path
    renderWithProviders(
      <AppFolderList
        template={template}
        appFolderIncluded
        onAppFolderIncludedChange={() => {}}
        extras={[]}
        includedExtras={[]}
        onIncludedExtrasChange={() => {}}
        user="backup"
        stats={immichStats.map((item) =>
          item.path === dumpPath
            ? { ...item, exists: false, latest_name: null, latest_modified_at: null }
            : item
        )}
        measuring={false}
        skipped={[]}
        onSkippedChange={() => {}}
      />
    )
    expect(screen.getByText('Borg UI takes a fresh copy before each backup.')).toBeInTheDocument()
    expect(screen.queryByText(/No database dump/)).not.toBeInTheDocument()
  })
})

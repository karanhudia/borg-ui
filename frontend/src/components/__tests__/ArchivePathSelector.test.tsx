import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { AxiosResponse } from 'axios'

import ArchivePathSelector from '../ArchivePathSelector'
import { BorgApiClient } from '../../services/borgApi/client'
import { renderWithProviders, screen, userEvent } from '../../test/test-utils'

vi.mock('../../services/borgApi/client', () => ({
  BorgApiClient: vi.fn(function () {
    return { getArchiveContents: vi.fn() }
  }),
}))

describe('ArchivePathSelector', () => {
  const repository = { id: 1, name: 'Repo', path: '/repo', borg_version: 1 }
  const archive = { id: 'archive-1', name: 'archive-1' }
  const onChange = vi.fn()
  let getArchiveContents: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    getArchiveContents = vi.fn()
    vi.mocked(BorgApiClient).mockImplementation(function () {
      return { getArchiveContents } as unknown as BorgApiClient
    })
  })

  it('shows Borg UI canary paths but does not let users select them as probe paths', async () => {
    const user = userEvent.setup()
    getArchiveContents.mockImplementation((_archiveId, _archiveName, path) => {
      if (path === '') {
        return Promise.resolve({
          data: {
            items: [
              {
                name: '.borg-ui',
                path: '.borg-ui',
                type: 'directory',
                size: 923,
                managed: true,
                managed_type: 'restore_canary',
              },
            ],
          },
        } as AxiosResponse)
      }

      return Promise.resolve({
        data: {
          items: [
            {
              name: 'manifest.json',
              path: '.borg-ui/restore-canaries/repository-1/.borgui-canary/manifest.json',
              type: 'file',
              size: 128,
              managed: true,
              managed_type: 'restore_canary',
            },
          ],
        },
      } as AxiosResponse)
    })

    renderWithProviders(
      <ArchivePathSelector
        repository={repository}
        archive={archive}
        data={{ selectedPaths: [] }}
        onChange={onChange}
      />
    )

    expect(await screen.findByText('.borg-ui')).toBeInTheDocument()
    expect(screen.getByText('Borg UI canary')).toBeInTheDocument()

    await user.click(screen.getByText('.borg-ui'))

    expect(await screen.findByText('manifest.json')).toBeInTheDocument()
    expect(
      screen.getByText('Canary paths are verified automatically by canary mode.')
    ).toBeInTheDocument()

    await user.click(screen.getByText('manifest.json'))

    expect(onChange).not.toHaveBeenCalled()
  })
})

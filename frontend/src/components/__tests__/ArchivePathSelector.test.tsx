import { describe, expect, it, vi, beforeEach } from 'vitest'
import { useState } from 'react'
import type { AxiosResponse } from 'axios'

import ArchivePathSelector from '../ArchivePathSelector'
import type { ArchiveBrowseState, ArchivePathSelectionData } from '../ArchivePathSelector'
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

describe('ArchivePathSelector embedded variant', () => {
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

  it('drops its own heading, selection bar, and helper caption', async () => {
    vi.mocked(BorgApiClient).mockImplementation(function () {
      return {
        getArchiveContents: vi.fn().mockResolvedValue({ data: { items: [] } }),
      } as unknown as BorgApiClient
    })
    renderWithProviders(
      <ArchivePathSelector
        repository={repository}
        archive={archive}
        data={{ selectedPaths: [] }}
        onChange={vi.fn()}
        variant="embedded"
      />
    )
    expect(await screen.findByText(/no items found/i)).toBeInTheDocument()
    expect(screen.queryByText('Select files to restore')).not.toBeInTheDocument()
    expect(screen.queryByText('No items selected')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading')).not.toBeInTheDocument()
  })

  it('toggles against the selection as it is now, not as it was when published', async () => {
    // The Files tab holds the published callbacks and drives them from the
    // keyboard. If they captured `data`, a keyboard toggle after a mouse
    // click would emit a selection that has forgotten the earlier click.
    getArchiveContents.mockResolvedValue({
      data: {
        items: [
          { name: 'a.txt', path: 'a.txt', type: 'file', size: 10 },
          { name: 'b.txt', path: 'b.txt', type: 'file', size: 20 },
        ],
      },
    } as AxiosResponse)

    let published: ArchiveBrowseState | null = null
    const emitted: string[][] = []
    const Harness = () => {
      const [data, setData] = useState<ArchivePathSelectionData>({
        selectedPaths: [],
        selectedItems: [],
      })
      return (
        <ArchivePathSelector
          repository={repository}
          archive={archive}
          data={data}
          onChange={(partial) => {
            emitted.push(partial.selectedPaths ?? [])
            setData((current) => ({ ...current, ...partial }))
          }}
          onBrowseStateChange={(state) => {
            published = state
          }}
        />
      )
    }

    renderWithProviders(<Harness />)
    const first = await screen.findByText('a.txt')
    await userEvent.setup().click(first)
    expect(emitted[emitted.length - 1]).toEqual(['a.txt'])

    // Drive the second row through the callback published earlier, exactly
    // as the Files tab's keyboard handler does.
    const state = published as unknown as ArchiveBrowseState
    state.activateItem(state.items[1])
    expect(emitted[emitted.length - 1]).toEqual(['a.txt', 'b.txt'])
  })

  it('selecting a folder covers everything inside it and prunes selected children', async () => {
    getArchiveContents.mockImplementation((_id: string, _name: string, path: string) =>
      Promise.resolve({
        data: {
          items:
            path === 'docs'
              ? [{ name: 'a.txt', path: 'docs/a.txt', type: 'file', size: 10 }]
              : [{ name: 'docs', path: 'docs', type: 'directory', size: 10 }],
        },
      } as AxiosResponse)
    )
    const emitted: string[][] = []
    const Harness = () => {
      const [data, setData] = useState<ArchivePathSelectionData>({
        selectedPaths: ['docs/a.txt'],
        selectedItems: [{ path: 'docs/a.txt', type: 'file' }],
      })
      return (
        <ArchivePathSelector
          repository={repository}
          archive={archive}
          data={data}
          onChange={(partial) => {
            emitted.push(partial.selectedPaths ?? [])
            setData((current) => ({ ...current, ...partial }))
          }}
        />
      )
    }
    renderWithProviders(<Harness />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /select directory/i }))
    expect(emitted[emitted.length - 1]).toEqual(['docs'])

    await user.click(screen.getByText('docs'))
    const child = await screen.findByText('a.txt')
    expect(screen.getByLabelText(/included with docs/i)).toBeInTheDocument()
    await user.click(child)
    expect(emitted[emitted.length - 1]).toEqual(['docs'])
  })

  it('filters the current folder and reports the filtered rows', async () => {
    getArchiveContents.mockResolvedValue({
      data: {
        items: [
          { name: 'invoices.xlsx', path: 'invoices.xlsx', type: 'file', size: 10 },
          { name: 'notes.md', path: 'notes.md', type: 'file', size: 20 },
        ],
      },
    } as AxiosResponse)

    let published: ArchiveBrowseState | null = null
    renderWithProviders(
      <ArchivePathSelector
        repository={repository}
        archive={archive}
        variant="embedded"
        data={{ selectedPaths: [], selectedItems: [] }}
        onChange={onChange}
        onBrowseStateChange={(state) => {
          published = state
        }}
      />
    )
    await screen.findByText('invoices.xlsx')
    await userEvent.setup().type(screen.getByLabelText(/filter files/i), 'notes')
    expect(screen.queryByText('invoices.xlsx')).not.toBeInTheDocument()
    expect(screen.getByText('notes.md')).toBeInTheDocument()
    expect((published as unknown as ArchiveBrowseState).items.map((i) => i.name)).toEqual([
      'notes.md',
    ])
  })
})

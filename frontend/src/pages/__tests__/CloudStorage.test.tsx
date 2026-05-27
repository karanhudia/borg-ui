import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AxiosResponse } from 'axios'
import {
  act,
  fireEvent,
  renderWithProviders,
  screen,
  userEvent,
  waitFor,
  within,
} from '../../test/test-utils'
import CloudStorage from '../CloudStorage'
import { rcloneAPI } from '../../services/api'

vi.mock('../../services/api', () => ({
  rcloneAPI: {
    getStatus: vi.fn(),
    listRemotes: vi.fn(),
    createRemote: vi.fn(),
    updateRemote: vi.fn(),
    deleteRemote: vi.fn(),
    testRemote: vi.fn(),
    browseRemote: vi.fn(),
  },
}))

vi.mock('react-hot-toast', async () => {
  const actual = await vi.importActual('react-hot-toast')
  return {
    ...actual,
    toast: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }
})

const remote = {
  id: 10,
  name: 'prod-s3',
  provider: 's3',
  usage_count: 2,
  config_source: 'managed',
  last_test_status: 'connected',
  last_error: null,
}

describe('CloudStorage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(rcloneAPI.getStatus).mockResolvedValue({
      data: { available: true, version: 'rclone v1.66.0' },
    } as AxiosResponse)
    vi.mocked(rcloneAPI.listRemotes).mockResolvedValue({
      data: { remotes: [remote] },
    } as AxiosResponse)
    vi.mocked(rcloneAPI.createRemote).mockResolvedValue({
      data: { ...remote, id: 11, name: 'local-test', provider: 'local', usage_count: 0 },
    } as AxiosResponse)
    vi.mocked(rcloneAPI.updateRemote).mockResolvedValue({
      data: { ...remote, name: 'archive-b2', provider: 'b2', usage_count: 2 },
    } as AxiosResponse)
    vi.mocked(rcloneAPI.deleteRemote).mockResolvedValue({ data: null } as AxiosResponse)
    vi.mocked(rcloneAPI.testRemote).mockResolvedValue({
      data: { status: 'connected', remote },
    } as AxiosResponse)
    vi.mocked(rcloneAPI.browseRemote).mockResolvedValue({
      data: {
        remote_id: 10,
        path: '',
        entries: [
          { name: 'borg-ui', path: 'borg-ui', is_dir: true, size: null, modified: null },
          { name: 'README', path: 'README', is_dir: false, size: 128, modified: null },
        ],
      },
    } as AxiosResponse)
  })

  it('renders reusable rclone remotes with provider, status, and usage count', async () => {
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    expect(await screen.findByText('prod-s3')).toBeInTheDocument()
    const card = screen.getByTestId('cloud-storage-remote-prod-s3')
    expect(within(card).getByText('s3')).toBeInTheDocument()
    expect(within(card).getAllByText('connected').length).toBeGreaterThan(0)
    expect(within(card).getByText('2 repositories')).toBeInTheDocument()
    expect(
      screen.getByText('Manage reusable rclone remotes for repository mirrors.')
    ).toBeInTheDocument()

    expect(within(card).getByRole('button', { name: /Test connection/i })).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: /Browse remote/i })).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: /Edit remote/i })).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: /Delete remote/i })).toBeDisabled()
  })

  it('adds a managed rclone remote from the page action', async () => {
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    await screen.findByText('prod-s3')
    fireEvent.click(await screen.findByRole('button', { name: /Add remote/i }))
    fireEvent.change(screen.getByLabelText(/Remote name/i), {
      target: { value: 'local-test' },
    })
    fireEvent.change(screen.getByLabelText(/^Provider/i), {
      target: { value: 'local' },
    })
    fireEvent.change(screen.getByLabelText(/Config JSON/i), {
      target: { value: '{"type":"local"}' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Create remote/i }))

    await waitFor(() => {
      expect(rcloneAPI.createRemote).toHaveBeenCalledWith({
        name: 'local-test',
        provider: 'local',
        config_source: 'managed',
        redacted_config: { type: 'local' },
      })
    })
  }, 60000)

  it('tests and browses a remote from the remote card', async () => {
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    const card = await screen.findByTestId('cloud-storage-remote-prod-s3')
    fireEvent.click(within(card).getByRole('button', { name: /Test connection/i }))

    await waitFor(() => {
      expect(rcloneAPI.testRemote).toHaveBeenCalledWith(10)
    })

    await waitFor(() => {
      expect(rcloneAPI.listRemotes).toHaveBeenCalledTimes(2)
    })
    const refreshedCard = await screen.findByTestId('cloud-storage-remote-prod-s3')
    fireEvent.click(within(refreshedCard).getByRole('button', { name: /Browse remote/i }))
    await waitFor(() => {
      expect(rcloneAPI.browseRemote).toHaveBeenCalledWith(10, '')
    })
    expect(await screen.findByRole('dialog', { name: /Browse prod-s3/i })).toBeInTheDocument()
    expect(screen.getByText('borg-ui')).toBeInTheDocument()
    expect(screen.getByText('README')).toBeInTheDocument()
  })

  it('navigates folders in the reusable browse dialog', async () => {
    vi.mocked(rcloneAPI.browseRemote).mockImplementation((_remoteId, path = '') => {
      return Promise.resolve({
        data: {
          remote_id: 10,
          path,
          entries:
            path === ''
              ? [{ name: 'borg-ui', path: 'borg-ui', is_dir: true, size: null, modified: null }]
              : [
                  {
                    name: 'archive.tar',
                    path: 'borg-ui/archive.tar',
                    is_dir: false,
                    size: 2048,
                    modified: '2026-05-27T12:00:00Z',
                  },
                ],
        },
      } as AxiosResponse)
    })

    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    const card = await screen.findByTestId('cloud-storage-remote-prod-s3')
    fireEvent.click(within(card).getByRole('button', { name: /Browse remote/i }))

    expect(await screen.findByRole('dialog', { name: /Browse prod-s3/i })).toBeInTheDocument()
    expect(await screen.findByText('borg-ui')).toBeInTheDocument()
    const folderButton = screen.getByRole('button', { name: /borg-ui/i })
    fireEvent.click(folderButton)

    await waitFor(() => {
      expect(rcloneAPI.browseRemote).toHaveBeenCalledWith(10, 'borg-ui')
    })
    expect(await screen.findByText('archive.tar')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Root/i })).toBeInTheDocument()
  }, 60000)

  it('ignores stale browse responses after navigating away', async () => {
    let resolveFolderBrowse!: (value: AxiosResponse) => void
    const folderBrowse = new Promise<AxiosResponse>((resolve) => {
      resolveFolderBrowse = resolve
    })
    let rootBrowseCount = 0

    vi.mocked(rcloneAPI.browseRemote).mockImplementation((_remoteId, path = '') => {
      if (path === 'borg-ui') {
        return folderBrowse
      }

      rootBrowseCount += 1
      return Promise.resolve({
        data: {
          remote_id: 10,
          path: '',
          entries:
            rootBrowseCount === 1
              ? [{ name: 'borg-ui', path: 'borg-ui', is_dir: true, size: null, modified: null }]
              : [
                  {
                    name: 'root-readme',
                    path: 'root-readme',
                    is_dir: false,
                    size: 512,
                    modified: null,
                  },
                ],
        },
      } as AxiosResponse)
    })

    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    const card = await screen.findByTestId('cloud-storage-remote-prod-s3')
    fireEvent.click(within(card).getByRole('button', { name: /Browse remote/i }))
    fireEvent.click(await screen.findByRole('button', { name: /borg-ui/i }))

    await waitFor(() => {
      expect(rcloneAPI.browseRemote).toHaveBeenCalledWith(10, 'borg-ui')
    })
    const rootBreadcrumb = screen.getByRole('button', { name: /^Root$/i })
    await waitFor(() => {
      expect(rootBreadcrumb).toBeEnabled()
    })
    fireEvent.click(rootBreadcrumb)

    expect(await screen.findByText('root-readme')).toBeInTheDocument()

    await act(async () => {
      resolveFolderBrowse({
        data: {
          remote_id: 10,
          path: 'borg-ui',
          entries: [
            {
              name: 'archive.tar',
              path: 'borg-ui/archive.tar',
              is_dir: false,
              size: 2048,
              modified: null,
            },
          ],
        },
      } as AxiosResponse)
      await folderBrowse
    })

    expect(screen.getByText('root-readme')).toBeInTheDocument()
    expect(screen.queryByText('archive.tar')).not.toBeInTheDocument()
  }, 60000)

  it('edits a remote from the remote card', async () => {
    const user = userEvent.setup()
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    const card = await screen.findByTestId('cloud-storage-remote-prod-s3')
    fireEvent.click(within(card).getByRole('button', { name: /Edit remote/i }))
    expect(await screen.findByRole('dialog', { name: /Edit rclone remote/i })).toBeInTheDocument()

    await user.clear(screen.getByLabelText(/Remote name/i))
    await user.type(screen.getByLabelText(/Remote name/i), 'archive-b2')
    await user.clear(screen.getByLabelText(/^Provider/i))
    await user.type(screen.getByLabelText(/^Provider/i), 'b2')
    await user.clear(screen.getByLabelText(/Config JSON/i))
    fireEvent.change(screen.getByLabelText(/Config JSON/i), {
      target: { value: '{"type":"b2","account":"redacted"}' },
    })
    await user.click(screen.getByRole('button', { name: /Save remote/i }))

    await waitFor(() => {
      expect(rcloneAPI.updateRemote).toHaveBeenCalledWith(10, {
        name: 'archive-b2',
        provider: 'b2',
        config_source: 'managed',
        redacted_config: { type: 'b2', account: 'redacted' },
      })
    })
  }, 60000)

  it('deletes an unused remote from the remote card after confirmation', async () => {
    const user = userEvent.setup()
    vi.mocked(rcloneAPI.listRemotes).mockResolvedValue({
      data: { remotes: [{ ...remote, usage_count: 0 }] },
    } as AxiosResponse)
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    const card = await screen.findByTestId('cloud-storage-remote-prod-s3')
    fireEvent.click(within(card).getByRole('button', { name: /Delete remote/i }))
    expect(await screen.findByRole('dialog', { name: /Delete prod-s3/i })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Delete remote/i }))

    await waitFor(() => {
      expect(rcloneAPI.deleteRemote).toHaveBeenCalledWith(10)
    })
  })

  it('shows useful empty and unavailable states', async () => {
    vi.mocked(rcloneAPI.getStatus).mockResolvedValue({
      data: { available: false, version: null, error: 'rclone binary not found' },
    } as AxiosResponse)
    vi.mocked(rcloneAPI.listRemotes).mockResolvedValue({
      data: { remotes: [] },
    } as AxiosResponse)

    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    expect(await screen.findByText(/rclone binary not found/i)).toBeInTheDocument()
    expect(screen.getByText(/No cloud storage remotes yet/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Add remote/i })).toBeDisabled()
  })
})

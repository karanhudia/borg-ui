import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AxiosResponse } from 'axios'
import {
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
    getProviders: vi.fn(),
    startOAuthSession: vi.fn(),
    getOAuthSession: vi.fn(),
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

vi.mock('../../components/CodeEditor', () => ({
  default: ({
    label,
    value,
    onChange,
  }: {
    label?: string
    value: string
    onChange: (value: string) => void
  }) => (
    <textarea
      aria-label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}))

const remote = {
  id: 10,
  name: 'prod-s3',
  provider: 's3',
  usage_count: 2,
  config_source: 'managed',
  last_test_status: 'connected',
  last_error: null,
}

const providers = [
  {
    type: 'drive',
    label: 'Google Drive',
    description: 'Google Drive and shared drives.',
    auth_type: 'oauth_token',
    type_editable: false,
    docs_url: 'https://rclone.org/drive/',
    config_template: { type: 'drive', scope: 'drive', token: '' },
    fields: [{ name: 'token', label: 'OAuth token JSON', kind: 'json', secret: true }],
  },
  {
    type: 'onedrive',
    label: 'Microsoft OneDrive',
    description: 'OneDrive personal and business drives.',
    auth_type: 'oauth_token',
    type_editable: false,
    docs_url: 'https://rclone.org/onedrive/',
    config_template: { type: 'onedrive', token: '' },
    fields: [{ name: 'token', label: 'OAuth token JSON', kind: 'json', secret: true }],
  },
  {
    type: 's3',
    label: 'Amazon S3 / S3-compatible',
    description: 'S3-compatible object storage.',
    auth_type: 'access_key',
    type_editable: false,
    docs_url: 'https://rclone.org/s3/',
    config_template: { type: 's3', provider: 'AWS' },
    fields: [],
  },
  {
    type: 'b2',
    label: 'Backblaze B2',
    description: 'Backblaze B2 buckets.',
    auth_type: 'access_key',
    type_editable: false,
    docs_url: 'https://rclone.org/b2/',
    config_template: { type: 'b2', account: '' },
    fields: [],
  },
  {
    type: 'local',
    label: 'Local filesystem',
    description: 'Local path remote.',
    auth_type: 'none',
    type_editable: false,
    docs_url: 'https://rclone.org/local/',
    config_template: { type: 'local' },
    fields: [],
  },
  {
    type: 'custom',
    label: 'Custom rclone backend',
    description: 'Manual setup for any rclone backend.',
    auth_type: 'manual',
    type_editable: true,
    docs_url: 'https://rclone.org/docs/',
    config_template: { type: '' },
    fields: [],
  },
]

const setMobileViewport = () => {
  vi.mocked(window.matchMedia).mockImplementation((query) => ({
    matches: query.includes('max-width'),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}

const setDesktopViewport = () => {
  vi.mocked(window.matchMedia).mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}

const openSpy = vi.fn()

describe('CloudStorage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setDesktopViewport()
    Object.defineProperty(window, 'open', {
      configurable: true,
      value: openSpy,
      writable: true,
    })
    vi.mocked(rcloneAPI.getStatus).mockResolvedValue({
      data: { available: true, version: 'rclone v1.66.0' },
    } as AxiosResponse)
    vi.mocked(rcloneAPI.getProviders).mockResolvedValue({
      data: { providers },
    } as AxiosResponse)
    vi.mocked(rcloneAPI.startOAuthSession).mockResolvedValue({
      data: {
        session_id: 'oauth-1',
        provider: 'drive',
        status: 'awaiting_callback',
        authorization_url: 'http://127.0.0.1:53682/auth?state=abc',
        config: null,
        error: null,
      },
    } as AxiosResponse)
    vi.mocked(rcloneAPI.getOAuthSession).mockResolvedValue({
      data: {
        session_id: 'oauth-1',
        provider: 'drive',
        status: 'authorized',
        authorization_url: 'http://127.0.0.1:53682/auth?state=abc',
        config: {
          type: 'drive',
          token: '{"access_token":"real-access","refresh_token":"real-refresh"}',
        },
        error: null,
      },
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
    const user = userEvent.setup()
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    await screen.findByText('prod-s3')
    await user.click(await screen.findByRole('button', { name: /Add remote/i }))
    await user.clear(screen.getByLabelText(/Remote name/i))
    await user.type(screen.getByLabelText(/Remote name/i), 'local-test')
    await user.clear(screen.getByLabelText(/Config JSON/i))
    fireEvent.change(screen.getByLabelText(/Config JSON/i), {
      target: { value: '{"type":"local"}' },
    })
    await user.click(screen.getByRole('button', { name: /Create remote/i }))

    await waitFor(() => {
      expect(rcloneAPI.createRemote).toHaveBeenCalledWith({
        name: 'local-test',
        provider: 'local',
        config_source: 'managed',
        redacted_config: { type: 'local' },
      })
    })
  }, 60000)

  it('loads guided providers and creates a Google Drive remote from the template', async () => {
    const user = userEvent.setup()
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    await screen.findByText('prod-s3')
    await waitFor(() => expect(rcloneAPI.getProviders).toHaveBeenCalled())
    await user.click(screen.getByRole('button', { name: /Add remote/i }))
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /Provider/i }))
    expect(await screen.findByRole('option', { name: /Microsoft OneDrive/i })).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('option', { name: /Google Drive/i }))
    expect(screen.getByText(/OAuth token JSON/i)).toBeInTheDocument()

    await user.clear(screen.getByLabelText(/Remote name/i))
    await user.type(screen.getByLabelText(/Remote name/i), 'gdrive-prod')
    fireEvent.change(screen.getByLabelText(/Config JSON/i), {
      target: {
        value:
          '{"type":"drive","scope":"drive","token":"{\\"access_token\\":\\"redacted\\"}"}',
      },
    })
    await user.click(screen.getByRole('button', { name: /Create remote/i }))

    await waitFor(() => {
      expect(rcloneAPI.createRemote).toHaveBeenCalledWith({
        name: 'gdrive-prod',
        provider: 'drive',
        config_source: 'managed',
        redacted_config: {
          type: 'drive',
          scope: 'drive',
          token: '{"access_token":"redacted"}',
        },
      })
    })
  }, 60000)

  it('fills an OAuth provider config from the in-app browser authorization flow', async () => {
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    await screen.findByText('prod-s3')
    fireEvent.click(screen.getByRole('button', { name: /Add remote/i }))
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /Provider/i }))
    fireEvent.click(await screen.findByRole('option', { name: /Google Drive/i }))

    fireEvent.click(screen.getByRole('button', { name: /Start browser authorization/i }))

    await waitFor(() => {
      expect(rcloneAPI.startOAuthSession).toHaveBeenCalledWith({
        provider: 'drive',
        config: { type: 'drive', scope: 'drive', token: '' },
      })
    })
    await waitFor(() => {
      expect(openSpy).toHaveBeenCalledWith(
        'http://127.0.0.1:53682/auth?state=abc',
        '_blank',
        'noopener,noreferrer'
      )
    })

    fireEvent.click(screen.getByRole('button', { name: /Check authorization/i }))

    await waitFor(() => {
      expect((screen.getByLabelText(/Config JSON/i) as HTMLTextAreaElement).value).toContain(
        'real-refresh'
      )
    })

    fireEvent.change(screen.getByLabelText(/Remote name/i), {
      target: { value: 'gdrive-oauth' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Create remote/i }))

    await waitFor(() => {
      expect(rcloneAPI.createRemote).toHaveBeenCalledWith({
        name: 'gdrive-oauth',
        provider: 'drive',
        config_source: 'managed',
        redacted_config: {
          type: 'drive',
          scope: 'drive',
          token: '{"access_token":"real-access","refresh_token":"real-refresh"}',
        },
      })
    })
  }, 60000)

  it('keeps a custom backend path for unsupported rclone providers', async () => {
    const user = userEvent.setup()
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    await screen.findByText('prod-s3')
    await user.click(screen.getByRole('button', { name: /Add remote/i }))
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /Provider/i }))
    fireEvent.click(await screen.findByRole('option', { name: /Custom rclone backend/i }))

    await user.clear(screen.getByLabelText(/Remote name/i))
    await user.type(screen.getByLabelText(/Remote name/i), 'mega-archive')
    await user.type(screen.getByLabelText(/Custom provider type/i), 'mega')
    fireEvent.change(screen.getByLabelText(/Config JSON/i), {
      target: { value: '{"type":"mega","user":"archive@example.com"}' },
    })
    await user.click(screen.getByRole('button', { name: /Create remote/i }))

    await waitFor(() => {
      expect(rcloneAPI.createRemote).toHaveBeenCalledWith({
        name: 'mega-archive',
        provider: 'mega',
        config_source: 'managed',
        redacted_config: { type: 'mega', user: 'archive@example.com' },
      })
    })
  }, 60000)

  it('opens the add remote dialog as a bottom sheet on mobile', async () => {
    setMobileViewport()
    const user = userEvent.setup()
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    await screen.findByText('prod-s3')
    await user.click(screen.getByRole('button', { name: /Add remote/i }))

    expect(await screen.findByTestId('drag-handle')).toBeInTheDocument()
  })

  it('tests and browses a remote from the remote card', async () => {
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    const card = await screen.findByTestId('cloud-storage-remote-prod-s3')
    fireEvent.click(within(card).getByRole('button', { name: /Test connection/i }))

    await waitFor(() => {
      expect(rcloneAPI.testRemote).toHaveBeenCalledWith(10)
    })

    fireEvent.click(within(card).getByRole('button', { name: /Browse remote/i }))
    await waitFor(() => {
      expect(rcloneAPI.browseRemote).toHaveBeenCalledWith(10, '')
    })
    expect(await screen.findByRole('dialog', { name: /Browse prod-s3/i })).toBeInTheDocument()
    expect(screen.getByText('borg-ui')).toBeInTheDocument()
    expect(screen.getByText('README')).toBeInTheDocument()
  })

  it('edits a remote from the remote card', async () => {
    const user = userEvent.setup()
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    const card = await screen.findByTestId('cloud-storage-remote-prod-s3')
    fireEvent.click(within(card).getByRole('button', { name: /Edit remote/i }))
    expect(await screen.findByRole('dialog', { name: /Edit rclone remote/i })).toBeInTheDocument()

    await user.clear(screen.getByLabelText(/Remote name/i))
    await user.type(screen.getByLabelText(/Remote name/i), 'archive-b2')
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /^Provider/i }))
    fireEvent.click(await screen.findByRole('option', { name: /Backblaze B2/i }))
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
  }, 60000)

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

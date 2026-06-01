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

const { mockTrackSystem } = vi.hoisted(() => ({
  mockTrackSystem: vi.fn(),
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackSystem: mockTrackSystem,
    EventAction: {
      CREATE: 'Create',
      EDIT: 'Edit',
      DELETE: 'Delete',
      VIEW: 'View',
      START: 'Start',
      TEST: 'Test',
      SEARCH: 'Search',
      FILTER: 'Filter',
    },
  }),
}))

vi.mock('../../services/api', () => ({
  rcloneAPI: {
    getStatus: vi.fn(),
    getProviders: vi.fn(),
    updateOAuthCredentials: vi.fn(),
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

vi.mock('../../components/shared/CodeEditor', () => ({
  default: ({
    label,
    value,
    onChange,
  }: {
    label?: string
    value: string
    onChange: (value: string) => void
  }) => (
    <textarea aria-label={label} value={value} onChange={(event) => onChange(event.target.value)} />
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
    oauth_mode: 'borg_ui',
    oauth_configured: true,
    oauth_callback_url: 'https://backups.example.com/api/rclone/oauth/callback/drive',
    oauth_setup_key: null,
    oauth_credentials_source: 'environment',
    oauth_client_id_set: true,
    oauth_client_secret_set: true,
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
    oauth_mode: 'borg_ui',
    oauth_configured: true,
    oauth_callback_url: 'https://backups.example.com/api/rclone/oauth/callback/onedrive',
    oauth_setup_key: null,
    oauth_credentials_source: 'environment',
    oauth_client_id_set: true,
    oauth_client_secret_set: true,
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
    vi.resetAllMocks()
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
    vi.mocked(rcloneAPI.updateOAuthCredentials).mockResolvedValue({
      data: {
        ...providers[0],
        oauth_configured: true,
        oauth_credentials_source: 'database',
        oauth_client_id_set: true,
        oauth_client_secret_set: true,
      },
    } as AxiosResponse)
    vi.mocked(rcloneAPI.startOAuthSession).mockResolvedValue({
      data: {
        session_id: 'oauth-1',
        provider: 'drive',
        status: 'awaiting_callback',
        oauth_mode: 'borg_ui',
        authorization_url: '/rclone/oauth/sessions/oauth-1/authorize',
        local_authorization_url: null,
        config: null,
        error: null,
      },
    } as AxiosResponse)
    vi.mocked(rcloneAPI.getOAuthSession).mockResolvedValue({
      data: {
        session_id: 'oauth-1',
        provider: 'drive',
        status: 'authorized',
        oauth_mode: 'borg_ui',
        authorization_url: '/rclone/oauth/sessions/oauth-1/authorize',
        local_authorization_url: null,
        config: {
          type: 'drive',
          _borg_ui_oauth_provider: 'drive',
          _borg_ui_oauth_session_id: 'oauth-1',
        },
        token_status: {
          status: 'valid',
          expires_at: '2026-05-30T01:00:00Z',
          refresh_available: true,
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
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    await screen.findByText('prod-s3')
    fireEvent.click(await screen.findByRole('button', { name: /Add remote/i }))
    fireEvent.change(screen.getByLabelText(/Remote name/i), {
      target: { value: 'local-test' },
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

  it('tracks cloud storage remote workflow analytics', async () => {
    const user = userEvent.setup()
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    await screen.findByText('prod-s3')
    await user.click(screen.getByRole('button', { name: /Add remote/i }))

    expect(mockTrackSystem).toHaveBeenCalledWith('View', {
      section: 'cloud_storage',
      operation: 'open_create_remote_dialog',
    })

    fireEvent.mouseDown(screen.getByRole('combobox', { name: /Provider/i }))
    fireEvent.click(await screen.findByRole('option', { name: /Google Drive/i }))
    await user.click(screen.getByRole('button', { name: /Start Borg UI OAuth/i }))

    await waitFor(() => {
      expect(mockTrackSystem).toHaveBeenCalledWith(
        'Start',
        expect.objectContaining({
          section: 'cloud_storage',
          operation: 'start_oauth',
          provider: 'drive',
          mode: 'borg_ui',
          status: 'awaiting_callback',
        })
      )
    })

    await user.clear(screen.getByLabelText(/Remote name/i))
    await user.type(screen.getByLabelText(/Remote name/i), 'gdrive-prod')
    await user.click(screen.getByRole('button', { name: /Create remote/i }))

    await waitFor(() => {
      expect(mockTrackSystem).toHaveBeenCalledWith(
        'Create',
        expect.objectContaining({
          section: 'cloud_storage',
          operation: 'create_remote',
          provider: 'drive',
          config_source: 'managed',
        })
      )
    })
  }, 60000)

  it('tracks cloud storage search result counts with the submitted query', async () => {
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    await screen.findByText('prod-s3')
    fireEvent.change(screen.getByPlaceholderText(/Search cloud storage/i), {
      target: { value: 'missing' },
    })

    expect(mockTrackSystem).toHaveBeenCalledWith('Search', {
      section: 'cloud_storage',
      operation: 'search_remotes',
      query_length: 7,
      sort_by: 'name-asc',
      group_by: 'none',
      result_count: 0,
    })
  })

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
        value: '{"type":"drive","scope":"drive","token":"{\\"access_token\\":\\"redacted\\"}"}',
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

  it('saves Borg UI OAuth remotes with a server-side token marker instead of raw token JSON', async () => {
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    await screen.findByText('prod-s3')
    fireEvent.click(screen.getByRole('button', { name: /Add remote/i }))
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /Provider/i }))
    fireEvent.click(await screen.findByRole('option', { name: /Google Drive/i }))

    fireEvent.click(screen.getByRole('button', { name: /Start Borg UI OAuth/i }))

    await waitFor(() => {
      expect(rcloneAPI.startOAuthSession).toHaveBeenCalledWith({
        provider: 'drive',
        mode: 'borg_ui',
        config: { type: 'drive', scope: 'drive', token: '' },
      })
    })
    await waitFor(() => {
      expect(openSpy).toHaveBeenCalledWith(
        '/api/rclone/oauth/sessions/oauth-1/authorize',
        '_blank',
        'noopener,noreferrer'
      )
    })

    fireEvent.click(screen.getByRole('button', { name: /Check authorization/i }))

    await waitFor(() => {
      expect(screen.getByText(/Token ready to save/i)).toBeInTheDocument()
    })
    const visibleConfig = (screen.getByLabelText(/Config JSON/i) as HTMLTextAreaElement).value
    expect(visibleConfig).not.toContain('real-refresh')
    expect(visibleConfig).not.toContain('real-access')
    expect(visibleConfig).not.toContain('_borg_ui_oauth')
    expect(visibleConfig).toContain('"scope": "drive"')

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
          _borg_ui_oauth_provider: 'drive',
          _borg_ui_oauth_session_id: 'oauth-1',
        },
      })
    })
  }, 60000)

  it('saves provider OAuth app credentials from the guided setup panel', async () => {
    const missingOAuthProviders = providers.map((provider) =>
      provider.type === 'drive'
        ? {
            ...provider,
            oauth_configured: false,
            oauth_callback_url: null,
            oauth_setup_key: 'backend.errors.rclone.oauthProviderCredentialsRequired',
            oauth_credentials_source: 'unset',
            oauth_client_id_set: false,
            oauth_client_secret_set: false,
          }
        : provider
    )
    vi.mocked(rcloneAPI.getProviders).mockResolvedValue({
      data: { providers: missingOAuthProviders },
    } as AxiosResponse)
    const user = userEvent.setup()
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    await screen.findByText('prod-s3')
    await user.click(screen.getByRole('button', { name: /Add remote/i }))
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /Provider/i }))
    fireEvent.click(await screen.findByRole('option', { name: /Google Drive/i }))

    await user.type(screen.getByLabelText(/OAuth client ID/i), 'drive-client-id')
    await user.type(screen.getByLabelText(/OAuth client secret/i), 'drive-secret')
    await user.click(screen.getByRole('button', { name: /Save OAuth credentials/i }))

    await waitFor(() => {
      expect(rcloneAPI.updateOAuthCredentials).toHaveBeenCalledWith('drive', {
        client_id: 'drive-client-id',
        client_secret: 'drive-secret',
      })
    })
  }, 60000)

  it('shows a validation error when only one OAuth credential field is filled', async () => {
    const missingOAuthProviders = providers.map((provider) =>
      provider.type === 'drive'
        ? {
            ...provider,
            oauth_configured: false,
            oauth_callback_url: null,
            oauth_setup_key: 'backend.errors.rclone.oauthProviderCredentialsRequired',
            oauth_credentials_source: 'unset',
            oauth_client_id_set: false,
            oauth_client_secret_set: false,
          }
        : provider
    )
    vi.mocked(rcloneAPI.getProviders).mockResolvedValue({
      data: { providers: missingOAuthProviders },
    } as AxiosResponse)
    const user = userEvent.setup()
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    await screen.findByText('prod-s3')
    await user.click(screen.getByRole('button', { name: /Add remote/i }))
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /Provider/i }))
    fireEvent.click(await screen.findByRole('option', { name: /Google Drive/i }))

    await user.type(screen.getByLabelText(/OAuth client ID/i), 'drive-client-id')
    await user.click(screen.getByRole('button', { name: /Save OAuth credentials/i }))

    await waitFor(() => {
      expect(screen.getByText(/Enter both a client ID and client secret/i)).toBeInTheDocument()
    })
    expect(rcloneAPI.updateOAuthCredentials).not.toHaveBeenCalled()
  }, 60000)

  it('clears provider OAuth app credentials from the guided setup panel', async () => {
    const user = userEvent.setup()
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    await screen.findByText('prod-s3')
    await user.click(screen.getByRole('button', { name: /Add remote/i }))
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /Provider/i }))
    fireEvent.click(await screen.findByRole('option', { name: /Google Drive/i }))

    await user.click(await screen.findByRole('button', { name: /^Edit$/i }))
    await user.click(screen.getByRole('button', { name: /Save OAuth credentials/i }))

    await waitFor(() => {
      expect(rcloneAPI.updateOAuthCredentials).toHaveBeenCalledWith('drive', {
        client_id: null,
        client_secret: null,
      })
    })
  }, 60000)

  it('shows OAuth token expiry and refresh availability on managed OAuth remotes', async () => {
    vi.mocked(rcloneAPI.listRemotes).mockResolvedValue({
      data: {
        remotes: [
          {
            ...remote,
            id: 12,
            name: 'gdrive-prod',
            provider: 'drive',
            usage_count: 1,
            oauth_token: {
              status: 'valid',
              expires_at: '2026-05-30T01:00:00Z',
              refresh_available: true,
            },
          },
        ],
      },
    } as AxiosResponse)

    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    const card = await screen.findByTestId('cloud-storage-remote-gdrive-prod')
    expect(within(card).getByText(/OAuth token/i)).toBeInTheDocument()
    expect(within(card).getByText(/Valid until/i)).toBeInTheDocument()
    expect(within(card).getByText(/Refresh token stored/i)).toBeInTheDocument()
  })

  it('clears Borg UI OAuth metadata when loopback authorization replaces it', async () => {
    vi.mocked(rcloneAPI.startOAuthSession)
      .mockResolvedValueOnce({
        data: {
          session_id: 'oauth-borg-ui',
          provider: 'drive',
          status: 'awaiting_callback',
          oauth_mode: 'borg_ui',
          authorization_url: '/rclone/oauth/sessions/oauth-borg-ui/authorize',
          local_authorization_url: null,
          config: null,
          error: null,
        },
      } as AxiosResponse)
      .mockResolvedValueOnce({
        data: {
          session_id: 'oauth-loopback',
          provider: 'drive',
          status: 'awaiting_callback',
          oauth_mode: 'rclone_loopback',
          authorization_url: '/rclone/oauth/sessions/oauth-loopback/authorize',
          local_authorization_url: 'http://127.0.0.1:53682/auth?state=loopback',
          config: null,
          error: null,
        },
      } as AxiosResponse)
    vi.mocked(rcloneAPI.getOAuthSession)
      .mockResolvedValueOnce({
        data: {
          session_id: 'oauth-borg-ui',
          provider: 'drive',
          status: 'authorized',
          oauth_mode: 'borg_ui',
          authorization_url: '/rclone/oauth/sessions/oauth-borg-ui/authorize',
          local_authorization_url: null,
          config: {
            type: 'drive',
            _borg_ui_oauth_provider: 'drive',
            _borg_ui_oauth_session_id: 'oauth-borg-ui',
          },
          token_status: {
            status: 'valid',
            expires_at: '2026-05-30T01:00:00Z',
            refresh_available: true,
          },
          error: null,
        },
      } as AxiosResponse)
      .mockResolvedValueOnce({
        data: {
          session_id: 'oauth-loopback',
          provider: 'drive',
          status: 'authorized',
          oauth_mode: 'rclone_loopback',
          authorization_url: '/rclone/oauth/sessions/oauth-loopback/authorize',
          local_authorization_url: 'http://127.0.0.1:53682/auth?state=loopback',
          config: {
            type: 'drive',
            token: '{"access_token":"loopback-access","refresh_token":"loopback-refresh"}',
          },
          error: null,
        },
      } as AxiosResponse)
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    await screen.findByText('prod-s3')
    fireEvent.click(screen.getByRole('button', { name: /Add remote/i }))
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /Provider/i }))
    fireEvent.click(await screen.findByRole('option', { name: /Google Drive/i }))

    fireEvent.click(screen.getByRole('button', { name: /Start Borg UI OAuth/i }))
    await waitFor(() => {
      expect(rcloneAPI.startOAuthSession).toHaveBeenCalledWith({
        provider: 'drive',
        mode: 'borg_ui',
        config: { type: 'drive', scope: 'drive', token: '' },
      })
    })
    await waitFor(() => {
      expect(openSpy).toHaveBeenCalledWith(
        '/api/rclone/oauth/sessions/oauth-borg-ui/authorize',
        '_blank',
        'noopener,noreferrer'
      )
    })
    fireEvent.click(await screen.findByRole('button', { name: /Check authorization/i }))

    await waitFor(() => {
      expect(screen.getByText(/Token ready to save/i)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Use rclone loopback/i }))

    await waitFor(() => {
      expect(rcloneAPI.startOAuthSession).toHaveBeenLastCalledWith(
        expect.objectContaining({
          provider: 'drive',
          mode: 'rclone_loopback',
        })
      )
    })
    fireEvent.click(await screen.findByRole('button', { name: /Check authorization/i }))

    await waitFor(() => {
      expect((screen.getByLabelText(/Config JSON/i) as HTMLTextAreaElement).value).toContain(
        'loopback-refresh'
      )
    })

    fireEvent.change(screen.getByLabelText(/Remote name/i), {
      target: { value: 'gdrive-loopback' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Create remote/i }))

    await waitFor(() => {
      expect(rcloneAPI.createRemote).toHaveBeenCalledWith({
        name: 'gdrive-loopback',
        provider: 'drive',
        config_source: 'managed',
        redacted_config: {
          type: 'drive',
          scope: 'drive',
          token: '{"access_token":"loopback-access","refresh_token":"loopback-refresh"}',
        },
      })
    })
  }, 60000)

  it('clears stale Borg UI OAuth metadata when replacement authorization starts', async () => {
    vi.mocked(rcloneAPI.startOAuthSession)
      .mockResolvedValueOnce({
        data: {
          session_id: 'oauth-borg-ui',
          provider: 'drive',
          status: 'awaiting_callback',
          oauth_mode: 'borg_ui',
          authorization_url: '/rclone/oauth/sessions/oauth-borg-ui/authorize',
          local_authorization_url: null,
          config: null,
          error: null,
        },
      } as AxiosResponse)
      .mockResolvedValueOnce({
        data: {
          session_id: 'oauth-loopback',
          provider: 'drive',
          status: 'awaiting_callback',
          oauth_mode: 'rclone_loopback',
          authorization_url: '/rclone/oauth/sessions/oauth-loopback/authorize',
          local_authorization_url: 'http://127.0.0.1:53682/auth?state=loopback',
          config: null,
          error: null,
        },
      } as AxiosResponse)
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    await screen.findByText('prod-s3')
    fireEvent.click(screen.getByRole('button', { name: /Add remote/i }))
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /Provider/i }))
    fireEvent.click(await screen.findByRole('option', { name: /Google Drive/i }))

    fireEvent.click(screen.getByRole('button', { name: /Start Borg UI OAuth/i }))
    await waitFor(() => {
      expect(rcloneAPI.startOAuthSession).toHaveBeenCalledTimes(1)
    })
    await waitFor(() => {
      expect(openSpy).toHaveBeenCalledWith(
        '/api/rclone/oauth/sessions/oauth-borg-ui/authorize',
        '_blank',
        'noopener,noreferrer'
      )
    })
    fireEvent.click(await screen.findByRole('button', { name: /Check authorization/i }))

    await waitFor(() => {
      expect(screen.getByText(/Token ready to save/i)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Use rclone loopback/i }))

    await waitFor(() => {
      expect(rcloneAPI.startOAuthSession).toHaveBeenLastCalledWith(
        expect.objectContaining({
          provider: 'drive',
          mode: 'rclone_loopback',
        })
      )
    })

    fireEvent.change(screen.getByLabelText(/Remote name/i), {
      target: { value: 'gdrive-loopback' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Create remote/i }))

    await waitFor(() => {
      expect(rcloneAPI.createRemote).toHaveBeenCalledWith({
        name: 'gdrive-loopback',
        provider: 'drive',
        config_source: 'managed',
        redacted_config: {
          type: 'drive',
          scope: 'drive',
        },
      })
    })
  }, 60000)

  it('ignores stale OAuth responses after switching providers', async () => {
    let resolveStart!: (value: AxiosResponse) => void
    vi.mocked(rcloneAPI.startOAuthSession).mockReturnValue(
      new Promise<AxiosResponse>((resolve) => {
        resolveStart = resolve
      })
    )
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    await screen.findByText('prod-s3')
    fireEvent.click(screen.getByRole('button', { name: /Add remote/i }))
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /Provider/i }))
    fireEvent.click(await screen.findByRole('option', { name: /Google Drive/i }))
    fireEvent.click(screen.getByRole('button', { name: /Start Borg UI OAuth/i }))

    await waitFor(() => {
      expect(rcloneAPI.startOAuthSession).toHaveBeenCalledWith({
        provider: 'drive',
        mode: 'borg_ui',
        config: { type: 'drive', scope: 'drive', token: '' },
      })
    })

    fireEvent.mouseDown(screen.getByRole('combobox', { name: /Provider/i }))
    fireEvent.click(await screen.findByRole('option', { name: /Amazon S3/i }))
    await waitFor(() => {
      expect((screen.getByLabelText(/Config JSON/i) as HTMLTextAreaElement).value).toContain(
        '"type": "s3"'
      )
    })

    await act(async () => {
      resolveStart({
        data: {
          session_id: 'oauth-stale',
          provider: 'drive',
          status: 'authorized',
          oauth_mode: 'borg_ui',
          authorization_url: 'http://127.0.0.1:53682/auth?state=stale',
          config: {
            type: 'drive',
            token: '{"access_token":"stale-access","refresh_token":"stale-refresh"}',
            _borg_ui_oauth_provider: 'drive',
          },
          error: null,
        },
      } as AxiosResponse)
      await Promise.resolve()
    })

    const configValue = (screen.getByLabelText(/Config JSON/i) as HTMLTextAreaElement).value
    expect(configValue).toContain('"type": "s3"')
    expect(configValue).not.toContain('stale-refresh')
    expect(openSpy).not.toHaveBeenCalled()
  }, 60000)

  it('shows Borg UI-owned OAuth callback guidance for configured providers', async () => {
    const user = userEvent.setup()
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    await screen.findByText('prod-s3')
    await user.click(screen.getByRole('button', { name: /Add remote/i }))
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /Provider/i }))
    fireEvent.click(await screen.findByRole('option', { name: /Google Drive/i }))

    expect(screen.getAllByText(/Borg UI callback/i).length).toBeGreaterThan(0)
    expect(
      screen.getByText(/https:\/\/backups\.example\.com\/api\/rclone\/oauth\/callback\/drive/i)
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Use rclone loopback/i })).toBeInTheDocument()
  }, 60000)

  it('keeps rclone loopback authorization available when Borg UI OAuth is not configured', async () => {
    const missingOAuthProviders = providers.map((provider) =>
      provider.type === 'drive'
        ? {
            ...provider,
            oauth_configured: false,
            oauth_callback_url: null,
            oauth_setup_key: 'backend.errors.rclone.oauthPublicBaseUrlRequired',
          }
        : provider
    )
    vi.mocked(rcloneAPI.getProviders).mockResolvedValue({
      data: { providers: missingOAuthProviders },
    } as AxiosResponse)
    const user = userEvent.setup()
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    await screen.findByText('prod-s3')
    await user.click(screen.getByRole('button', { name: /Add remote/i }))
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /Provider/i }))
    fireEvent.click(await screen.findByRole('option', { name: /Google Drive/i }))

    expect(screen.getByText(/PUBLIC_BASE_URL is required/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Start Borg UI OAuth/i })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: /Use rclone loopback/i }))

    await waitFor(() => {
      expect(rcloneAPI.startOAuthSession).toHaveBeenCalledWith({
        provider: 'drive',
        mode: 'rclone_loopback',
        config: { type: 'drive', scope: 'drive', token: '' },
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

  it('surfaces provider catalog load failures', async () => {
    vi.mocked(rcloneAPI.getProviders).mockRejectedValue(new Error('provider catalog unavailable'))
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    expect(await screen.findByText('Failed to load cloud providers.')).toBeInTheDocument()
  })

  it('tests and browses a remote from the remote card', async () => {
    const user = userEvent.setup()
    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    const card = await screen.findByTestId('cloud-storage-remote-prod-s3')
    await user.click(within(card).getByRole('button', { name: /Test connection/i }))

    await waitFor(() => {
      expect(rcloneAPI.testRemote).toHaveBeenCalledWith(10)
    })

    await waitFor(() => {
      expect(rcloneAPI.listRemotes).toHaveBeenCalledTimes(2)
    })
    const refreshedCard = await screen.findByTestId('cloud-storage-remote-prod-s3')
    await user.click(within(refreshedCard).getByRole('button', { name: /Browse remote/i }))
    await waitFor(() => {
      expect(rcloneAPI.browseRemote).toHaveBeenCalledWith(10, '')
    })
    expect(await screen.findByRole('dialog', { name: /Browse prod-s3/i })).toBeInTheDocument()
    expect(screen.getByText('borg-ui')).toBeInTheDocument()
    expect(screen.getByText('README')).toBeInTheDocument()
  }, 60000)

  it('navigates folders in the reusable browse dialog', async () => {
    const user = userEvent.setup()
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
    await user.click(within(card).getByRole('button', { name: /Browse remote/i }))

    expect(await screen.findByRole('dialog', { name: /Browse prod-s3/i })).toBeInTheDocument()
    expect(await screen.findByText('borg-ui')).toBeInTheDocument()
    const folderButton = screen.getByRole('button', { name: /borg-ui/i })
    await user.click(folderButton)

    await waitFor(() => {
      expect(rcloneAPI.browseRemote).toHaveBeenCalledWith(10, 'borg-ui')
    })
    expect(await screen.findByText('archive.tar')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Root/i })).toBeInTheDocument()
  }, 60000)

  it('keeps nested rclone paths rooted under the current folder when API entries are relative', async () => {
    const user = userEvent.setup()
    vi.mocked(rcloneAPI.browseRemote).mockImplementation((_remoteId, path = '') => {
      return Promise.resolve({
        data: {
          remote_id: 10,
          path,
          entries:
            path === ''
              ? [{ name: 'borg-ui', path: 'borg-ui', is_dir: true, size: null, modified: null }]
              : path === 'borg-ui'
                ? [{ name: 'snapshots', path: 'snapshots', is_dir: true, size: -1, modified: null }]
                : [
                    {
                      name: 'manifest.json',
                      path: 'manifest.json',
                      is_dir: false,
                      size: 128,
                      modified: null,
                    },
                  ],
        },
      } as AxiosResponse)
    })

    renderWithProviders(<CloudStorage />, { initialRoute: '/cloud-storage' })

    const card = await screen.findByTestId('cloud-storage-remote-prod-s3')
    await user.click(within(card).getByRole('button', { name: /Browse remote/i }))
    await waitFor(() => {
      expect(rcloneAPI.browseRemote).toHaveBeenCalledWith(10, '')
    })
    await user.click(await screen.findByRole('button', { name: /borg-ui/i }, { timeout: 10000 }))

    const nestedFolder = await screen.findByRole(
      'button',
      { name: /snapshots/i },
      { timeout: 10000 }
    )
    await user.click(nestedFolder)

    await waitFor(() => {
      expect(rcloneAPI.browseRemote).toHaveBeenCalledWith(10, 'borg-ui/snapshots')
    })
  }, 60000)

  it('ignores stale browse responses after navigating away', async () => {
    const user = userEvent.setup()
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
    await user.click(within(card).getByRole('button', { name: /Browse remote/i }))
    await waitFor(() => {
      expect(rcloneAPI.browseRemote).toHaveBeenCalledWith(10, '')
    })
    await user.click(await screen.findByRole('button', { name: /borg-ui/i }, { timeout: 10000 }))

    await waitFor(() => {
      expect(rcloneAPI.browseRemote).toHaveBeenCalledWith(10, 'borg-ui')
    })
    const rootBreadcrumb = screen.getByRole('button', { name: /^Root$/i })
    await waitFor(() => {
      expect(rootBreadcrumb).toBeEnabled()
    })
    await user.click(rootBreadcrumb)

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

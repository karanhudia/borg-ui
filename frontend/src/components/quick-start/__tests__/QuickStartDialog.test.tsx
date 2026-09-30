import { beforeEach, describe, expect, it, vi } from 'vitest'

import { backupPlansAPI, scriptsAPI, sourceDiscoveryAPI } from '../../../services/api'
import { BorgApiClient } from '../../../services/borgApi'
import { renderWithProviders, screen, userEvent, waitFor } from '../../../test/test-utils'
import QuickStartDialog from '../QuickStartDialog'

vi.mock('../../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/api')>()
  return {
    ...actual,
    backupPlansAPI: { ...actual.backupPlansAPI, create: vi.fn(), run: vi.fn() },
    scriptsAPI: { ...actual.scriptsAPI, create: vi.fn() },
    sourceDiscoveryAPI: {
      ...actual.sourceDiscoveryAPI,
      appTemplates: vi.fn(),
      detectApps: vi.fn(),
      inspectApp: vi.fn(),
    },
  }
})

const immich = {
  id: 'immich',
  version: 1,
  name: 'Immich',
  description: 'Photos, videos and Immich database dumps.',
  docs_url: 'https://docs.immich.app/administration/backup-and-restore',
  verified: { app_version: 'v3.2.4', date: '2026-09-30', restore_tested: false },
  detect: { image_prefix: 'ghcr.io/immich-app/immich-server', mount_destination: '/data' },
  root_hint: 'UPLOAD_LOCATION in your Immich .env file',
  folders: [
    { path: 'upload', label: 'Uploads', description: '', role: 'data', stale_after_hours: null },
    {
      path: 'thumbs',
      label: 'Previews',
      description: '',
      role: 'rebuildable',
      stale_after_hours: null,
    },
    {
      path: 'encoded-video',
      label: 'Re-encoded videos',
      description: '',
      role: 'rebuildable',
      stale_after_hours: null,
    },
  ],
  pre_backup_script: {
    name: 'Check Immich database dump',
    description: 'check',
    content: 'APP_ROOT=__APP_ROOT__\n',
    timeout: 60,
  },
  schedule_cron: '0 3 * * *',
  notes: [],
}
vi.mock('../../../services/borgApi', () => ({
  BorgApiClient: { createRepository: vi.fn() },
}))

describe('QuickStartDialog', () => {
  beforeEach(() => {
    vi.mocked(BorgApiClient.createRepository).mockResolvedValue({ data: { id: 4 } } as never)
    vi.mocked(backupPlansAPI.create).mockResolvedValue({ data: { id: 9 } } as never)
    vi.mocked(scriptsAPI.create).mockResolvedValue({ data: { id: 12 } } as never)
    vi.mocked(sourceDiscoveryAPI.appTemplates).mockResolvedValue({
      data: { templates: [immich] },
    } as never)
    vi.mocked(sourceDiscoveryAPI.inspectApp).mockResolvedValue({
      data: { folders: [], warnings: [] },
    } as never)
    vi.mocked(sourceDiscoveryAPI.detectApps).mockResolvedValue({
      data: {
        detections: [
          {
            template_id: 'immich',
            container_name: 'immich_server',
            state: 'running',
            path: '/local/srv/immich',
            host_path: '/srv/immich',
            readable: true,
            extra_mounts: [
              {
                path: '/local/srv/photos',
                host_path: '/srv/photos',
                destination: '/mnt/photos',
                readable: true,
              },
            ],
          },
        ],
        warnings: [],
      },
    } as never)
  })

  it('walks a local setup and creates the repository and plan', async () => {
    const user = userEvent.setup()
    renderWithProviders(<QuickStartDialog open onClose={() => {}} />)

    const next = () => user.click(screen.getByRole('button', { name: 'Next' }))

    expect(screen.getByRole('radio', { name: /Something else/ })).toBeChecked()
    await next()

    expect(screen.getByRole('radio', { name: /Files on this server/ })).toBeChecked()
    await next()

    const nextButton = screen.getByRole('button', { name: 'Next' })
    expect(nextButton).toBeDisabled()
    await user.type(screen.getByLabelText('Folder'), '/local/home{Enter}')
    await next()

    // The name and location are suggested from the first folder.
    expect(screen.getByLabelText(/Backup location/)).toHaveValue('/local/borg-backups/home')
    await next()

    expect(screen.getByLabelText(/^Name/)).toHaveValue('home')
    await user.type(screen.getByLabelText(/^Passphrase/), 'correct horse')
    await user.type(screen.getByLabelText(/Repeat passphrase/), 'correct horse')
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
    await user.click(screen.getByLabelText(/I have saved my passphrase/))
    // Editing the passphrase afterwards asks for the confirmation again.
    await user.type(screen.getByLabelText(/^Passphrase/), '!')
    await user.type(screen.getByLabelText(/Repeat passphrase/), '!')
    expect(screen.getByLabelText(/I have saved my passphrase/)).not.toBeChecked()
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
    await user.click(screen.getByLabelText(/I have saved my passphrase/))
    await next()

    expect(screen.getByRole('radio', { name: /Every day/ })).toBeChecked()
    await next()

    expect(screen.getByText('Repository "home" and backup plan "home"')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Create backup' }))

    await waitFor(() => expect(screen.getByText('Your backup is ready')).toBeInTheDocument())
    expect(BorgApiClient.createRepository).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'home', path: '/local/borg-backups/home' })
    )
    expect(backupPlansAPI.create).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'home', schedule_enabled: true, run_prune_after: true })
    )
  })

  it('sets up Immich from its detected folder, with excludes and the dump check', async () => {
    const user = userEvent.setup()
    renderWithProviders(<QuickStartDialog open onClose={() => {}} />)
    const next = () => user.click(screen.getByRole('button', { name: 'Next' }))

    await user.click(screen.getByRole('radio', { name: /An app/ }))
    // No app picked yet, so there is nothing to go on with.
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
    await user.click(await screen.findByRole('combobox', { name: 'App' }))
    await user.click(screen.getByRole('option', { name: /Immich/ }))
    await next()
    await next() // files on this server

    expect(await screen.findByText(/Found Immich \(container immich_server\)/)).toBeInTheDocument()
    // Shown in the found message and, once filled in, as the folder chip.
    await waitFor(() => expect(screen.getAllByText('/local/srv/immich')).toHaveLength(2))
    await next()
    await next()

    expect(screen.getByLabelText(/^Name/)).toHaveValue('Immich')
    await user.type(screen.getByLabelText(/^Passphrase/), 'correct horse')
    await user.type(screen.getByLabelText(/Repeat passphrase/), 'correct horse')
    await user.click(screen.getByLabelText(/I have saved my passphrase/))
    await next()
    await next()

    expect(screen.getByText('thumbs/, encoded-video/')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Create backup' }))

    await waitFor(() => expect(screen.getByText('Your backup is ready')).toBeInTheDocument())
    expect(scriptsAPI.create).toHaveBeenCalledWith(
      expect.objectContaining({ content: "APP_ROOT='/local/srv/immich'\n" })
    )
    expect(backupPlansAPI.create).toHaveBeenCalledWith(
      expect.objectContaining({
        // The external library rides along; excludes stay under Immich's folder.
        source_directories: ['/local/srv/immich', '/local/srv/photos'],
        exclude_patterns: ['/local/srv/immich/thumbs', '/local/srv/immich/encoded-video'],
        cron_expression: '0 3 * * *',
        pre_backup_script_id: 12,
      })
    )
  })
})

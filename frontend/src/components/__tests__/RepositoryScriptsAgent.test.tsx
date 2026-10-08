import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { renderWithProviders } from '../../test/test-utils'
import api from '../../services/api'
import RepositoryScriptsSection from '../RepositoryScriptsSection'

vi.mock('../../services/api', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}))

const agentHook = {
  id: 11,
  script_id: null,
  agent_script_name: 'backup-postgres',
  is_agent_script: true,
  script_name: 'backup-postgres',
  script_description: null,
  execution_order: 1,
  enabled: true,
  custom_timeout: null,
  custom_run_on: null,
  continue_on_error: false,
  skip_on_failure: false,
  default_timeout: 300,
  default_run_on: 'always',
  parameters: [],
  parameter_values: null,
}

const libraryHook = {
  ...agentHook,
  id: 12,
  script_id: 4,
  agent_script_name: null,
  is_agent_script: false,
  script_name: 'start-database',
}

const renderSection = (props = {}) =>
  renderWithProviders(
    <RepositoryScriptsSection
      repositoryId={7}
      preBackupScript=""
      postBackupScript=""
      onPreBackupScriptChange={vi.fn()}
      onPostBackupScriptChange={vi.fn()}
      onOpenPreScriptDialog={vi.fn()}
      onOpenPostScriptDialog={vi.fn()}
      {...props}
    />
  )

describe('RepositoryScriptsSection for an agent repository', () => {
  // what the repository's agent answers, per test
  let agentScripts: { scripts: { name: string; description?: string }[]; agent_online: boolean }

  beforeEach(() => {
    vi.clearAllMocks()
    agentScripts = {
      scripts: [{ name: 'backup-postgres' }, { name: 'stop-app', description: 'Stops it' }],
      agent_online: true,
    }
    ;(api.get as Mock).mockImplementation((url: string) =>
      Promise.resolve({
        data:
          url === '/repositories/7/scripts'
            ? { pre_backup: [agentHook], post_backup: [libraryHook] }
            : url === '/repositories/7/agent-scripts'
              ? agentScripts
              : [],
      })
    )
  })

  it('offers no inline script and flags one stored from before', async () => {
    const user = userEvent.setup()
    const onPreBackupScriptChange = vi.fn()
    renderSection({
      agentRepository: true,
      preBackupScript: 'systemctl stop postgresql',
      onPreBackupScriptChange,
    })

    expect(screen.queryByText('Inline Script')).not.toBeInTheDocument()
    const alert = screen.getByText(/This inline script never runs/i).closest('[role="alert"]')
    await user.click(within(alert as HTMLElement).getByRole('button', { name: 'Remove' }))
    expect(onPreBackupScriptChange).toHaveBeenCalledWith('')
  })

  it('marks agent hooks and library hooks that never run', async () => {
    renderSection({ agentRepository: true })

    expect(await screen.findByText('backup-postgres')).toBeInTheDocument()
    expect(screen.getByText('Agent')).toBeInTheDocument()
    expect(await screen.findByText('Never runs')).toBeInTheDocument()
    // a library script can be tested on the server, an agent script cannot
    expect(screen.getAllByLabelText(/test/i)).toHaveLength(1)
  })

  it('assigns a script the agent publishes', async () => {
    const user = userEvent.setup()
    ;(api.post as Mock).mockResolvedValue({ data: { success: true, id: 13 } })
    renderSection({ agentRepository: true })
    await screen.findByText('backup-postgres')

    await user.click(screen.getAllByRole('button', { name: 'Add' })[0])
    await user.click(await screen.findByRole('combobox', { name: 'Agent script' }))
    // already assigned to this hook: not offered again
    const listbox = await screen.findByRole('listbox')
    expect(within(listbox).queryByText('backup-postgres')).not.toBeInTheDocument()
    await user.click(within(listbox).getByText('stop-app'))
    await user.type(screen.getByLabelText('Timeout (seconds)'), '1800')
    await user.click(screen.getByRole('button', { name: 'Assign Script' }))

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/repositories/7/scripts',
        expect.objectContaining({
          agent_script_name: 'stop-app',
          custom_timeout: 1800,
          hook_type: 'pre-backup',
        })
      )
    )
    // the saved repository's agent, through a route its operators may use
    expect(api.get).toHaveBeenCalledWith('/repositories/7/agent-scripts')
    expect((api.post as Mock).mock.calls[0][1]).not.toHaveProperty('script_id')
  })

  it('says when the agent is offline', async () => {
    const user = userEvent.setup()
    agentScripts = { scripts: [], agent_online: false }
    renderSection({ agentRepository: true })
    await screen.findByText('backup-postgres')

    await user.click(screen.getAllByRole('button', { name: 'Add' })[0])

    expect(await screen.findByText(/The agent is offline/i)).toBeInTheDocument()

    // the agent connects; the next open asks it again
    agentScripts = { scripts: [{ name: 'stop-app' }], agent_online: true }
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await user.click(screen.getAllByRole('button', { name: 'Add' })[0])
    await user.click(await screen.findByRole('combobox', { name: 'Agent script' }))
    expect(await screen.findByRole('option', { name: 'stop-app' })).toBeInTheDocument()
  })

  it('keeps the inline script and the library for a server repository', async () => {
    renderSection()

    expect(screen.getAllByText('Inline Script')).toHaveLength(2)
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/scripts'))
    expect(api.get).not.toHaveBeenCalledWith('/repositories/7/agent-scripts')
  })
})

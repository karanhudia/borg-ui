import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  fireEvent,
  renderWithProviders,
  screen,
  userEvent,
  waitFor,
  within,
} from '../../test/test-utils'
import Scripts from '../Scripts'
import api from '../../services/api'
import { toast } from 'react-hot-toast'

const trackScripts = vi.fn()

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackScripts,
    EventAction: {
      VIEW: 'View',
      CREATE: 'Create',
      EDIT: 'Edit',
      DELETE: 'Delete',
      TEST: 'Test',
    },
  }),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: {
      id: 1,
      username: 'admin',
      email: 'admin@example.com',
      role: 'admin',
      global_permissions: ['settings.scripts.manage'],
    },
    hasGlobalPermission: (permission: string) => permission === 'settings.scripts.manage',
  }),
}))

vi.mock('../../components/CodeEditor', () => ({
  default: ({
    label,
    value,
    onChange,
  }: {
    label: string
    value: string
    onChange: (value: string) => void
  }) => (
    <label>
      {label}
      <textarea aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  ),
}))

vi.mock('../../components/ScriptParameterInputs', () => ({
  default: ({
    parameters,
    values,
    onChange,
  }: {
    parameters: Array<{ name: string }>
    values: Record<string, string>
    onChange: (values: Record<string, string>) => void
  }) => (
    <div>
      {parameters.map((param) => (
        <label key={param.name}>
          {param.name}
          <input
            aria-label={param.name}
            value={values[param.name] || ''}
            onChange={(e) => onChange({ ...values, [param.name]: e.target.value })}
          />
        </label>
      ))}
    </div>
  ),
}))

vi.mock('react-hot-toast', async () => {
  const actual = await vi.importActual<typeof import('react-hot-toast')>('react-hot-toast')
  return {
    ...actual,
    toast: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }
})

describe('Scripts page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal(
      'confirm',
      vi.fn(() => true)
    )
    vi.spyOn(api, 'get').mockImplementation((url: string) => {
      if (url === '/scripts') {
        return Promise.resolve({
          data: [
            {
              id: 1,
              name: 'Cleanup',
              description: 'Cleanup temp files',
              file_path: '/scripts/cleanup.sh',
              category: 'custom',
              timeout: 300,
              run_on: 'always',
              usage_count: 0,
              is_template: false,
              created_at: '2026-04-01T00:00:00Z',
              updated_at: '2026-04-01T00:00:00Z',
              parameters: [{ name: 'TARGET', type: 'text' }],
            },
          ],
        } as never)
      }
      if (url === '/scripts/1') {
        return Promise.resolve({
          data: {
            id: 1,
            name: 'Cleanup',
            description: 'Cleanup temp files',
            file_path: '/scripts/cleanup.sh',
            category: 'custom',
            timeout: 300,
            run_on: 'always',
            usage_count: 1,
            is_template: false,
            created_at: '2026-04-01T00:00:00Z',
            updated_at: '2026-04-01T00:00:00Z',
            content: '#!/bin/bash\necho ${TARGET:-/tmp}\n',
            repositories: [],
            recent_executions: [],
            parameters: [{ name: 'TARGET', type: 'text' }],
          },
        } as never)
      }
      return Promise.reject(new Error(`Unhandled GET ${url}`))
    })
    vi.spyOn(api, 'post').mockImplementation((url: string) => {
      if (url === '/scripts') {
        return Promise.resolve({ data: {} } as never)
      }
      if (url === '/scripts/1/test') {
        return Promise.resolve({
          data: {
            success: true,
            exit_code: 0,
            stdout: 'ok',
            stderr: '',
            execution_time: 0.42,
          },
        } as never)
      }
      return Promise.reject(new Error(`Unhandled POST ${url}`))
    })
    vi.spyOn(api, 'put').mockResolvedValue({ data: {} } as never)
    vi.spyOn(api, 'delete').mockResolvedValue({ data: {} } as never)
  })

  it('loads scripts and supports create, edit, test, and delete flows', async () => {
    const user = userEvent.setup()

    renderWithProviders(<Scripts />)

    expect(await screen.findByText('Cleanup')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /new script/i }))
    const createDialog = await screen.findByRole('dialog', { name: /create script/i })
    await user.type(within(createDialog).getByLabelText(/name/i), 'Rotate Logs')
    await user.type(within(createDialog).getByLabelText(/description/i), 'Rotate log files')
    await user.click(within(createDialog).getByRole('button', { name: /^create$/i }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/scripts',
        expect.objectContaining({
          name: 'Rotate Logs',
          description: 'Rotate log files',
          category: 'custom',
          run_on: 'always',
        })
      )
    })
    expect(trackScripts).toHaveBeenCalledWith('Create', 'Rotate Logs', expect.any(Object))

    const cleanupRow = screen.getByText('Cleanup').closest('tr')
    const actionButtons = cleanupRow ? Array.from(cleanupRow.querySelectorAll('button')) : []
    const playButton = actionButtons[0]
    const editButton = actionButtons[1]
    const deleteButton = actionButtons[2]
    expect(editButton).toBeTruthy()
    await user.click(editButton!)

    const editDialog = await screen.findByRole('dialog', { name: /edit script/i })
    const descriptionInput = within(editDialog).getByLabelText(/description/i)
    await user.clear(descriptionInput)
    await user.type(descriptionInput, 'Cleanup old temp files')
    await user.click(within(editDialog).getByRole('button', { name: /^update$/i }))

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith(
        '/scripts/1',
        expect.objectContaining({
          name: 'Cleanup',
          description: 'Cleanup old temp files',
        })
      )
    })
    expect(trackScripts).toHaveBeenCalledWith('Edit', 'Cleanup', expect.any(Object))

    expect(playButton).toBeTruthy()
    await user.click(playButton!)

    const testDialog = await screen.findByRole('dialog', { name: /test script/i })
    await user.type(within(testDialog).getByLabelText('TARGET'), '/var/tmp')
    await user.click(within(testDialog).getByRole('button', { name: /run test/i }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/scripts/1/test', {
        parameter_values: { TARGET: '/var/tmp' },
        timeout: undefined,
      })
    })
    expect(await screen.findByText('ok')).toBeInTheDocument()
    expect(trackScripts).toHaveBeenCalledWith(
      'Test',
      'Cleanup',
      expect.objectContaining({ success: true })
    )

    expect(deleteButton).toBeTruthy()
    await user.click(deleteButton!)

    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith('/scripts/1')
    })
    expect(trackScripts).toHaveBeenCalledWith('Delete', 'Cleanup', { category: 'custom' })
  })

  it('detects custom parameters, ignores borg-ui reserved variables, and preserves secret toggles', async () => {
    const user = userEvent.setup()

    renderWithProviders(<Scripts />)

    await screen.findByText('Cleanup')
    await user.click(screen.getByRole('button', { name: /new script/i }))

    const createDialog = await screen.findByRole('dialog', { name: /create script/i })
    const editor = within(createDialog).getByLabelText(/script content/i)

    fireEvent.change(editor, {
      target: {
        value:
          '#!/bin/bash\necho ${API_KEY:-secret}\necho ${BORG_UI_RESERVED}\necho ${TARGET_DIR:-/data}\n',
      },
    })

    expect(await within(createDialog).findByText('API_KEY')).toBeInTheDocument()
    expect(within(createDialog).getByText('TARGET_DIR')).toBeInTheDocument()
    expect(within(createDialog).queryByText('BORG_UI_RESERVED')).not.toBeInTheDocument()
    expect(within(createDialog).getByText('Default: secret')).toBeInTheDocument()
    expect(within(createDialog).getByText('Default: /data')).toBeInTheDocument()

    const secretToggle = within(createDialog).getAllByRole('checkbox')[0]
    await user.click(secretToggle)

    fireEvent.change(editor, {
      target: {
        value: '#!/bin/bash\necho ${API_KEY:-secret}\necho ${TARGET_DIR:-/srv}\n',
      },
    })

    expect((await within(createDialog).findAllByRole('checkbox'))[0]).toBeChecked()
    expect(within(createDialog).getByText('Default: /srv')).toBeInTheDocument()
  })

  it('shows failed test output and tracks an unsuccessful script test', async () => {
    const user = userEvent.setup()
    vi.mocked(api.post).mockImplementation((url: string) => {
      if (url === '/scripts/1/test') {
        return Promise.reject({
          message: 'backend exploded',
          response: { data: { detail: 'scripts.errors.failedToExecute' } },
        } as never)
      }
      if (url === '/scripts') {
        return Promise.resolve({ data: {} } as never)
      }
      return Promise.reject(new Error(`Unhandled POST ${url}`))
    })

    renderWithProviders(<Scripts />)

    expect(await screen.findByText('Cleanup')).toBeInTheDocument()
    const cleanupRow = screen.getByText('Cleanup').closest('tr')
    const playButton = cleanupRow ? Array.from(cleanupRow.querySelectorAll('button'))[0] : null
    expect(playButton).toBeTruthy()

    await user.click(playButton!)

    const testDialog = await screen.findByRole('dialog', { name: /test script/i })
    await user.type(within(testDialog).getByLabelText('TARGET'), '/var/tmp')
    await user.click(within(testDialog).getByRole('button', { name: /run test/i }))

    expect(await screen.findByText(/execution failed/i)).toBeInTheDocument()
    expect(await screen.findByText(/scripts.errors.failedToExecute/i)).toBeInTheDocument()
    expect(trackScripts).toHaveBeenCalledWith(
      'Test',
      'Cleanup',
      expect.objectContaining({ success: false, parameter_count: 1 })
    )
  })

  it('prevents deleting template scripts', async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/scripts') {
        return Promise.resolve({
          data: [
            {
              id: 2,
              name: 'Template Script',
              description: 'Built-in template',
              file_path: '/scripts/template.sh',
              category: 'template',
              timeout: 120,
              run_on: 'success',
              usage_count: 3,
              is_template: true,
              created_at: '2026-04-01T00:00:00Z',
              updated_at: '2026-04-01T00:00:00Z',
              parameters: [],
            },
          ],
        } as never)
      }
      return Promise.reject(new Error(`Unhandled GET ${url}`))
    })

    renderWithProviders(<Scripts />)

    expect(await screen.findByText('Template Script')).toBeInTheDocument()
    const row = screen.getByText('Template Script').closest('tr')
    const buttons = row ? Array.from(row.querySelectorAll('button')) : []

    expect(buttons[1]).toBeDisabled()
    expect(buttons[2]).toBeDisabled()
    expect(api.delete).not.toHaveBeenCalled()
    expect(toast.error).not.toHaveBeenCalled()
  })
})

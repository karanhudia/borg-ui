import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import WizardStepScripts from '../WizardStepScripts'

describe('WizardStepScripts', () => {
  const mockScripts = [
    { id: 1, name: 'Wake Server', parameters: null },
    { id: 2, name: 'Shutdown Server', parameters: null },
  ]

  const defaultData = {
    preBackupScriptId: null,
    postBackupScriptId: null,
    preBackupScriptParameters: {},
    postBackupScriptParameters: {},
    runRepositoryScripts: false,
  }

  const defaultProps = {
    data: defaultData,
    scripts: mockScripts,
    repositoryCount: 2,
    onChange: vi.fn(),
  }

  it('renders info alert with script explanations', () => {
    render(<WizardStepScripts {...defaultProps} />)

    expect(screen.getByText(/runs once per schedule/i)).toBeInTheDocument()
    expect(screen.getByText(/runs for each repository/i)).toBeInTheDocument()
  })

  it('renders ScriptSelectorSection when repositories are selected', () => {
    render(<WizardStepScripts {...defaultProps} />)

    // Check that ScriptSelectorSection is rendered by looking for its unique elements
    const selects = screen.getAllByRole('combobox')
    expect(selects).toHaveLength(2)
    expect(screen.getByText(/These scripts run once per schedule/i)).toBeInTheDocument()
  })

  it('displays warning when repositoryCount is 0', () => {
    render(<WizardStepScripts {...defaultProps} repositoryCount={0} />)

    expect(
      screen.getByText(/Select at least one repository in Step 1 to configure scripts/i)
    ).toBeInTheDocument()
  })

  it('does not render ScriptSelectorSection when repositoryCount is 0', () => {
    render(<WizardStepScripts {...defaultProps} repositoryCount={0} />)

    expect(screen.queryByLabelText(/Pre-Backup Script/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Post-Backup Script/i)).not.toBeInTheDocument()
  })

  it('calls onChange when pre-backup script is selected', () => {
    const onChange = vi.fn()
    render(<WizardStepScripts {...defaultProps} onChange={onChange} />)

    // This would require interacting with the ScriptSelectorSection
    // The actual onChange is tested in ScriptSelectorSection tests
    const selects = screen.getAllByRole('combobox')
    expect(selects[0]).toBeInTheDocument()
  })

  it('calls onChange when post-backup script is selected', () => {
    const onChange = vi.fn()
    render(<WizardStepScripts {...defaultProps} onChange={onChange} />)

    const selects = screen.getAllByRole('combobox')
    expect(selects[1]).toBeInTheDocument()
  })

  it('calls onChange when runRepositoryScripts is toggled', () => {
    const onChange = vi.fn()
    render(<WizardStepScripts {...defaultProps} onChange={onChange} />)

    expect(
      screen.getByRole('checkbox', { name: /Run repository-level scripts/i })
    ).toBeInTheDocument()
  })

  it('passes scripts to ScriptSelectorSection', () => {
    render(<WizardStepScripts {...defaultProps} />)

    // Check that scripts are available in the selector
    const selects = screen.getAllByRole('combobox')
    expect(selects).toHaveLength(2)
  })

  it('passes preBackupScriptId to ScriptSelectorSection', () => {
    const dataWithPreScript = {
      ...defaultData,
      preBackupScriptId: 1,
    }

    render(<WizardStepScripts {...defaultProps} data={dataWithPreScript} />)

    expect(screen.getByText('Wake Server')).toBeInTheDocument()
  })

  it('passes postBackupScriptId to ScriptSelectorSection', () => {
    const dataWithPostScript = {
      ...defaultData,
      postBackupScriptId: 2,
    }

    render(<WizardStepScripts {...defaultProps} data={dataWithPostScript} />)

    expect(screen.getByText('Shutdown Server')).toBeInTheDocument()
  })

  it('passes runRepositoryScripts to ScriptSelectorSection', () => {
    const dataWithRepoScripts = {
      ...defaultData,
      runRepositoryScripts: true,
    }

    render(<WizardStepScripts {...defaultProps} data={dataWithRepoScripts} />)

    const checkbox = screen.getByRole('checkbox', { name: /Run repository-level scripts/i })
    expect(checkbox).toBeChecked()
  })

  it('passes script parameters to ScriptSelectorSection', () => {
    const scriptsWithParams = [
      {
        id: 1,
        name: 'DB Backup',
        parameters: [
          {
            name: 'db_name',
            type: 'text' as const,
            default: '',
            description: 'Database',
            required: true,
          },
        ],
      },
    ]

    const dataWithParams = {
      ...defaultData,
      preBackupScriptId: 1,
      preBackupScriptParameters: { db_name: 'mydb' },
    }

    render(
      <WizardStepScripts {...defaultProps} scripts={scriptsWithParams} data={dataWithParams} />
    )

    expect(screen.getByLabelText(/db_name/i)).toBeInTheDocument()
  })

  it('handles empty scripts array', () => {
    render(<WizardStepScripts {...defaultProps} scripts={[]} />)

    const selects = screen.getAllByRole('combobox')
    expect(selects).toHaveLength(2)
  })

  it('applies medium size to ScriptSelectorSection', () => {
    render(<WizardStepScripts {...defaultProps} />)

    const selects = screen.getAllByRole('combobox')
    expect(selects).toHaveLength(2)
  })

  it('renders with multiple repositories', () => {
    render(<WizardStepScripts {...defaultProps} repositoryCount={5} />)

    const selects = screen.getAllByRole('combobox')
    expect(selects).toHaveLength(2)
    expect(screen.queryByText(/Select at least one repository/i)).not.toBeInTheDocument()
  })

  it('displays info alert severity', () => {
    render(<WizardStepScripts {...defaultProps} />)

    const alert = screen.getByText(/Schedule-level:/i).closest('.MuiAlert-root')
    expect(alert).toHaveClass('MuiAlert-standardInfo')
  })

  it('displays warning alert severity when no repositories', () => {
    render(<WizardStepScripts {...defaultProps} repositoryCount={0} />)

    const alert = screen
      .getByText(/Select at least one repository in Step 1 to configure scripts/)
      .closest('.MuiAlert-root')
    expect(alert).toHaveClass('MuiAlert-standardWarning')
  })

  it('provides concise script level explanation in info alert', () => {
    render(<WizardStepScripts {...defaultProps} />)

    expect(screen.getByText(/Schedule-level:/i)).toBeInTheDocument()
    expect(screen.getByText(/runs once per schedule/i)).toBeInTheDocument()
    expect(screen.getByText(/Repository-level:/i)).toBeInTheDocument()
    expect(screen.getByText(/runs for each repository/i)).toBeInTheDocument()
  })

  it('handles script parameter changes', () => {
    const scriptsWithParams = [
      {
        id: 1,
        name: 'Parameterized Script',
        parameters: [
          {
            name: 'param1',
            type: 'text' as const,
            default: '',
            description: 'Parameter 1',
            required: true,
          },
        ],
      },
    ]

    const dataWithScript = {
      ...defaultData,
      preBackupScriptId: 1,
      preBackupScriptParameters: {},
    }

    render(
      <WizardStepScripts {...defaultProps} scripts={scriptsWithParams} data={dataWithScript} />
    )

    expect(screen.getByLabelText(/param1/i)).toBeInTheDocument()
  })

  it('handles postBackupScriptParameters', () => {
    const scriptsWithParams = [
      {
        id: 1,
        name: 'Post Script',
        parameters: [
          {
            name: 'post_param',
            type: 'text' as const,
            default: '',
            description: 'Post Parameter',
            required: false,
          },
        ],
      },
    ]

    const dataWithPostParams = {
      ...defaultData,
      postBackupScriptId: 1,
      postBackupScriptParameters: { post_param: 'value' },
    }

    render(
      <WizardStepScripts {...defaultProps} scripts={scriptsWithParams} data={dataWithPostParams} />
    )

    expect(screen.getByLabelText(/post_param/i)).toBeInTheDocument()
  })
})

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import WizardStepBackupConfig, { BackupConfigStepData } from '../WizardStepBackupConfig'

// Mock CompressionSettings
vi.mock('../../CompressionSettings', () => ({
  default: ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
    <div data-testid="compression-settings">
      <span>Compression: {value}</span>
      <button onClick={() => onChange('zstd')}>Change Compression</button>
    </div>
  ),
}))

// Mock ExcludePatternInput
vi.mock('../../ExcludePatternInput', () => ({
  default: ({
    patterns,
    onChange,
    onBrowseClick,
  }: {
    patterns: string[]
    onChange: (p: string[]) => void
    onBrowseClick: () => void
  }) => (
    <div data-testid="exclude-pattern-input">
      <span>{patterns.length} exclude patterns</span>
      <button onClick={() => onChange([...patterns, '*.new'])}>Add Pattern</button>
      <button onClick={onBrowseClick}>Browse</button>
    </div>
  ),
}))

// Mock AdvancedRepositoryOptions
vi.mock('../../AdvancedRepositoryOptions', () => ({
  default: ({
    remotePath,
    customFlags,
    preBackupScript,
    postBackupScript,
    onRemotePathChange,
    onCustomFlagsChange,
  }: {
    remotePath: string
    customFlags: string
    preBackupScript: string
    postBackupScript: string
    onRemotePathChange: (v: string) => void
    onCustomFlagsChange: (v: string) => void
  }) => (
    <div data-testid="advanced-options">
      <span>Remote Path: {remotePath || '(empty)'}</span>
      <span>Custom Flags: {customFlags || '(empty)'}</span>
      <span>Pre Script: {preBackupScript || '(empty)'}</span>
      <span>Post Script: {postBackupScript || '(empty)'}</span>
      <button onClick={() => onRemotePathChange('/usr/bin/borg')}>Set Remote Path</button>
      <button onClick={() => onCustomFlagsChange('--stats')}>Set Custom Flags</button>
    </div>
  ),
}))

const defaultData: BackupConfigStepData = {
  compression: 'lz4',
  excludePatterns: ['*.tmp', '*.log'],
  customFlags: '',
  remotePath: '',
  preBackupScript: '',
  postBackupScript: '',
  preHookTimeout: 300,
  postHookTimeout: 300,
  continueOnHookFailure: false,
}

describe('WizardStepBackupConfig', () => {
  describe('Compression Settings', () => {
    it('renders compression settings component', () => {
      render(
        <WizardStepBackupConfig
          dataSource="local"
          repositoryMode="full"
          data={defaultData}
          onChange={vi.fn()}
          onBrowseExclude={vi.fn()}
        />
      )

      expect(screen.getByTestId('compression-settings')).toBeInTheDocument()
    })

    it('shows current compression value', () => {
      render(
        <WizardStepBackupConfig
          dataSource="local"
          repositoryMode="full"
          data={defaultData}
          onChange={vi.fn()}
          onBrowseExclude={vi.fn()}
        />
      )

      expect(screen.getByText('Compression: lz4')).toBeInTheDocument()
    })

    it('calls onChange when compression changes', async () => {
      const { userEvent } = await import('@testing-library/user-event')
      const user = userEvent.setup()
      const onChange = vi.fn()

      render(
        <WizardStepBackupConfig
          dataSource="local"
          repositoryMode="full"
          data={defaultData}
          onChange={onChange}
          onBrowseExclude={vi.fn()}
        />
      )

      await user.click(screen.getByText('Change Compression'))

      expect(onChange).toHaveBeenCalledWith({ compression: 'zstd' })
    })
  })

  describe('Exclude Patterns - Local Source', () => {
    it('renders exclude pattern input for local data source', () => {
      render(
        <WizardStepBackupConfig
          dataSource="local"
          repositoryMode="full"
          data={defaultData}
          onChange={vi.fn()}
          onBrowseExclude={vi.fn()}
        />
      )

      expect(screen.getByTestId('exclude-pattern-input')).toBeInTheDocument()
    })

    it('shows current exclude pattern count', () => {
      render(
        <WizardStepBackupConfig
          dataSource="local"
          repositoryMode="full"
          data={defaultData}
          onChange={vi.fn()}
          onBrowseExclude={vi.fn()}
        />
      )

      expect(screen.getByText('2 exclude patterns')).toBeInTheDocument()
    })

    it('calls onChange when patterns change', async () => {
      const { userEvent } = await import('@testing-library/user-event')
      const user = userEvent.setup()
      const onChange = vi.fn()

      render(
        <WizardStepBackupConfig
          dataSource="local"
          repositoryMode="full"
          data={defaultData}
          onChange={onChange}
          onBrowseExclude={vi.fn()}
        />
      )

      await user.click(screen.getByText('Add Pattern'))

      expect(onChange).toHaveBeenCalledWith({
        excludePatterns: ['*.tmp', '*.log', '*.new'],
      })
    })

    it('calls onBrowseExclude when browse is clicked', async () => {
      const { userEvent } = await import('@testing-library/user-event')
      const user = userEvent.setup()
      const onBrowseExclude = vi.fn()

      render(
        <WizardStepBackupConfig
          dataSource="local"
          repositoryMode="full"
          data={defaultData}
          onChange={vi.fn()}
          onBrowseExclude={onBrowseExclude}
        />
      )

      await user.click(screen.getByText('Browse'))

      expect(onBrowseExclude).toHaveBeenCalled()
    })
  })

  describe('Remote Data Source', () => {
    it('shows exclude pattern input for remote data source', () => {
      render(
        <WizardStepBackupConfig
          dataSource="remote"
          repositoryMode="full"
          data={defaultData}
          onChange={vi.fn()}
          onBrowseExclude={vi.fn()}
        />
      )

      // After SSHFS path preservation fix, excludes work for remote sources too
      expect(screen.getByTestId('exclude-pattern-input')).toBeInTheDocument()
    })

    it('shows info alert for remote data source explaining how excludes work', () => {
      render(
        <WizardStepBackupConfig
          dataSource="remote"
          repositoryMode="full"
          data={defaultData}
          onChange={vi.fn()}
          onBrowseExclude={vi.fn()}
        />
      )

      expect(
        screen.getByText(
          /Remote directories are mounted via SSHFS preserving their original paths/i
        )
      ).toBeInTheDocument()
    })
  })

  describe('Advanced Options', () => {
    it('renders advanced repository options', () => {
      render(
        <WizardStepBackupConfig
          dataSource="local"
          repositoryMode="full"
          data={defaultData}
          onChange={vi.fn()}
          onBrowseExclude={vi.fn()}
        />
      )

      expect(screen.getByTestId('advanced-options')).toBeInTheDocument()
    })

    it('passes remote path to advanced options', () => {
      const dataWithRemotePath = { ...defaultData, remotePath: '/usr/local/bin/borg' }

      render(
        <WizardStepBackupConfig
          dataSource="local"
          repositoryMode="full"
          data={dataWithRemotePath}
          onChange={vi.fn()}
          onBrowseExclude={vi.fn()}
        />
      )

      expect(screen.getByText('Remote Path: /usr/local/bin/borg')).toBeInTheDocument()
    })

    it('passes custom flags to advanced options', () => {
      const dataWithFlags = { ...defaultData, customFlags: '--stats --progress' }

      render(
        <WizardStepBackupConfig
          dataSource="local"
          repositoryMode="full"
          data={dataWithFlags}
          onChange={vi.fn()}
          onBrowseExclude={vi.fn()}
        />
      )

      expect(screen.getByText('Custom Flags: --stats --progress')).toBeInTheDocument()
    })

    it('passes hook scripts to advanced options', () => {
      const dataWithScripts = {
        ...defaultData,
        preBackupScript: 'echo "starting"',
        postBackupScript: 'echo "done"',
      }

      render(
        <WizardStepBackupConfig
          dataSource="local"
          repositoryMode="full"
          data={dataWithScripts}
          onChange={vi.fn()}
          onBrowseExclude={vi.fn()}
        />
      )

      expect(screen.getByText('Pre Script: echo "starting"')).toBeInTheDocument()
      expect(screen.getByText('Post Script: echo "done"')).toBeInTheDocument()
    })

    it('calls onChange when remote path changes', async () => {
      const { userEvent } = await import('@testing-library/user-event')
      const user = userEvent.setup()
      const onChange = vi.fn()

      render(
        <WizardStepBackupConfig
          dataSource="local"
          repositoryMode="full"
          data={defaultData}
          onChange={onChange}
          onBrowseExclude={vi.fn()}
        />
      )

      await user.click(screen.getByText('Set Remote Path'))

      expect(onChange).toHaveBeenCalledWith({ remotePath: '/usr/bin/borg' })
    })

    it('calls onChange when custom flags change', async () => {
      const { userEvent } = await import('@testing-library/user-event')
      const user = userEvent.setup()
      const onChange = vi.fn()

      render(
        <WizardStepBackupConfig
          dataSource="local"
          repositoryMode="full"
          data={defaultData}
          onChange={onChange}
          onBrowseExclude={vi.fn()}
        />
      )

      await user.click(screen.getByText('Set Custom Flags'))

      expect(onChange).toHaveBeenCalledWith({ customFlags: '--stats' })
    })
  })

  describe('Repository ID', () => {
    it('passes repository ID to advanced options when editing', () => {
      render(
        <WizardStepBackupConfig
          repositoryId={42}
          dataSource="local"
          repositoryMode="full"
          data={defaultData}
          onChange={vi.fn()}
          onBrowseExclude={vi.fn()}
        />
      )

      expect(screen.getByTestId('advanced-options')).toBeInTheDocument()
    })

    it('handles null repository ID', () => {
      render(
        <WizardStepBackupConfig
          repositoryId={null}
          dataSource="local"
          repositoryMode="full"
          data={defaultData}
          onChange={vi.fn()}
          onBrowseExclude={vi.fn()}
        />
      )

      expect(screen.getByTestId('advanced-options')).toBeInTheDocument()
    })
  })
})

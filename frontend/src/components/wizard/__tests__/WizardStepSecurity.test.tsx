import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import WizardStepSecurity from '../WizardStepSecurity'

const defaultData = {
  encryption: 'repokey',
  passphrase: '',
  remotePath: '',
  selectedKeyfile: null as File | null,
}

describe('WizardStepSecurity', () => {
  describe('Create Mode', () => {
    it('renders encryption method dropdown', () => {
      render(<WizardStepSecurity mode="create" data={defaultData} onChange={vi.fn()} />)

      expect(screen.getByText('Repokey (Recommended)')).toBeInTheDocument()
    })

    it('renders passphrase input', () => {
      render(<WizardStepSecurity mode="create" data={defaultData} onChange={vi.fn()} />)

      expect(screen.getByPlaceholderText(/Enter passphrase/i)).toBeInTheDocument()
    })

    it('renders remote borg path input', () => {
      render(<WizardStepSecurity mode="create" data={defaultData} onChange={vi.fn()} />)

      expect(screen.getByLabelText(/Remote Borg Path/i)).toBeInTheDocument()
    })

    it('calls onChange when passphrase is entered', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()

      render(<WizardStepSecurity mode="create" data={defaultData} onChange={onChange} />)

      await user.type(screen.getByPlaceholderText(/Enter passphrase/i), 'mysecret')

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          passphrase: expect.any(String),
        })
      )
    })

    it('shows security warning when no encryption is selected', () => {
      const noEncryptionData = { ...defaultData, encryption: 'none' }

      render(<WizardStepSecurity mode="create" data={noEncryptionData} onChange={vi.fn()} />)

      expect(screen.getByText(/Security Warning/i)).toBeInTheDocument()
      expect(screen.getByText(/stored without encryption/i)).toBeInTheDocument()
    })

    it('hides passphrase input when encryption is none', () => {
      const noEncryptionData = { ...defaultData, encryption: 'none' }

      render(<WizardStepSecurity mode="create" data={noEncryptionData} onChange={vi.fn()} />)

      expect(screen.queryByPlaceholderText(/Enter passphrase/i)).not.toBeInTheDocument()
    })

    it('does NOT show encryption warning in create mode', () => {
      render(<WizardStepSecurity mode="create" data={defaultData} onChange={vi.fn()} />)

      expect(screen.queryByText(/Encryption settings cannot be changed/i)).not.toBeInTheDocument()
    })
  })

  describe('Edit Mode', () => {
    it('does NOT render encryption method dropdown', () => {
      render(<WizardStepSecurity mode="edit" data={defaultData} onChange={vi.fn()} />)

      // In edit mode, encryption dropdown should not be shown
      expect(screen.queryByLabelText(/Encryption Method/i)).not.toBeInTheDocument()
    })

    it('shows encryption info alert', () => {
      render(<WizardStepSecurity mode="edit" data={defaultData} onChange={vi.fn()} />)

      expect(screen.getByText(/Encryption settings cannot be changed/i)).toBeInTheDocument()
    })

    it('shows passphrase as optional', () => {
      render(<WizardStepSecurity mode="edit" data={defaultData} onChange={vi.fn()} />)

      expect(
        screen.getByPlaceholderText(/Leave blank to keep last saved passphrase/i)
      ).toBeInTheDocument()
    })

    it('shows helper text about keeping existing passphrase', () => {
      render(<WizardStepSecurity mode="edit" data={defaultData} onChange={vi.fn()} />)

      expect(screen.getByText(/leave blank to keep last saved passphrase/i)).toBeInTheDocument()
    })
  })

  describe('Import Mode', () => {
    it('does NOT render encryption method dropdown', () => {
      render(<WizardStepSecurity mode="import" data={defaultData} onChange={vi.fn()} />)

      expect(screen.queryByLabelText(/Encryption Method/i)).not.toBeInTheDocument()
    })

    it('does NOT show encryption settings warning', () => {
      render(<WizardStepSecurity mode="import" data={defaultData} onChange={vi.fn()} />)

      // Import mode should not show the "cannot change encryption" warning
      expect(screen.queryByText(/Encryption settings cannot be changed/i)).not.toBeInTheDocument()
    })

    it('renders keyfile upload option', () => {
      render(<WizardStepSecurity mode="import" data={defaultData} onChange={vi.fn()} />)

      expect(screen.getByText(/Borg Keyfile \(Optional\)/i)).toBeInTheDocument()
      expect(screen.getByText(/Choose Keyfile/i)).toBeInTheDocument()
    })

    it('shows selected keyfile name', () => {
      const dataWithKeyfile = {
        ...defaultData,
        selectedKeyfile: new File([''], 'my-key.key', { type: 'application/octet-stream' }),
      }

      render(<WizardStepSecurity mode="import" data={dataWithKeyfile} onChange={vi.fn()} />)

      expect(screen.getByText(/Selected: my-key.key/i)).toBeInTheDocument()
    })

    it('shows success message when keyfile is selected', () => {
      const dataWithKeyfile = {
        ...defaultData,
        selectedKeyfile: new File([''], 'my-key.key', { type: 'application/octet-stream' }),
      }

      render(<WizardStepSecurity mode="import" data={dataWithKeyfile} onChange={vi.fn()} />)

      expect(screen.getByText(/Keyfile will be uploaded after import/i)).toBeInTheDocument()
    })
  })

  describe('Encryption Selection', () => {
    it('can select keyfile encryption', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()

      render(<WizardStepSecurity mode="create" data={defaultData} onChange={onChange} />)

      // Click on the select to open dropdown
      const selectButton = screen.getByText('Repokey (Recommended)')
      await user.click(selectButton)

      // Find and click keyfile option in the listbox
      const listbox = await screen.findByRole('listbox')
      const keyfileOption = within(listbox).getByText('Keyfile')
      await user.click(keyfileOption)

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          encryption: 'keyfile',
        })
      )
    })

    it('can select no encryption', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()

      render(<WizardStepSecurity mode="create" data={defaultData} onChange={onChange} />)

      // Click on the select to open dropdown
      const selectButton = screen.getByText('Repokey (Recommended)')
      await user.click(selectButton)

      // Find and click none option in the listbox
      const listbox = await screen.findByRole('listbox')
      const noneOption = within(listbox).getByText('None (Unencrypted)')
      await user.click(noneOption)

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          encryption: 'none',
        })
      )
    })
  })

  describe('Remote Borg Path', () => {
    it('calls onChange when remote path is entered', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()

      render(<WizardStepSecurity mode="create" data={defaultData} onChange={onChange} />)

      await user.type(screen.getByLabelText(/Remote Borg Path/i), '/usr/local/bin/borg')

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          remotePath: expect.any(String),
        })
      )
    })

    it('shows placeholder for remote borg path', () => {
      render(<WizardStepSecurity mode="create" data={defaultData} onChange={vi.fn()} />)

      expect(screen.getByPlaceholderText(/\/usr\/local\/bin\/borg/i)).toBeInTheDocument()
    })
  })
})

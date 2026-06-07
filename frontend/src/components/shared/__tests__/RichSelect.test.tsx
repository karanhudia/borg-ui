import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HardDrive } from 'lucide-react'
import { describe, expect, it, vi } from 'vitest'

import RichSelect, { type RichSelectOption } from '../RichSelect'

const options: RichSelectOption[] = [
  {
    value: 'drive',
    primary: 'Google Drive',
    secondary: 'drive',
    icon: <HardDrive size={16} />,
    group: 'Browser OAuth',
  },
  {
    value: 's3',
    primary: 'Amazon S3 compatible storage providers',
    secondary: 's3',
    icon: <HardDrive size={16} />,
    group: 'Access keys',
  },
]

describe('RichSelect', () => {
  it('renders the selected option as display content without a search input', () => {
    render(<RichSelect value="drive" onChange={vi.fn()} options={options} label="Provider" />)

    const combobox = screen.getByRole('combobox', { name: /Provider/i })
    expect(combobox).toHaveTextContent('Google Drive')
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('renders search as the first menu control when enabled and filters options', async () => {
    const user = userEvent.setup()

    render(
      <RichSelect
        value="drive"
        onChange={vi.fn()}
        options={options}
        label="Provider"
        searchEnabled
        searchPlaceholder="Search providers"
      />
    )

    await user.click(screen.getByRole('combobox', { name: /Provider/i }))
    const searchInput = screen.getByPlaceholderText('Search providers')
    expect(searchInput).toBeInTheDocument()

    await user.type(searchInput, 's3')

    const listbox = await screen.findByRole('listbox')
    expect(within(listbox).getByRole('option', { name: /Amazon S3/i })).toBeInTheDocument()
    expect(within(listbox).queryByRole('option', { name: /Google Drive/i })).not.toBeInTheDocument()
  })

  it('calls onChange with the selected option value', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(<RichSelect value="drive" onChange={onChange} options={options} label="Provider" />)

    await user.click(screen.getByRole('combobox', { name: /Provider/i }))
    const listbox = await screen.findByRole('listbox')
    await user.click(within(listbox).getByRole('option', { name: /Amazon S3/i }))

    expect(onChange).toHaveBeenCalledWith('s3')
  })
})

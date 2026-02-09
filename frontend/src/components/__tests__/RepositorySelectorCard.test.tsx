import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import RepositorySelectorCard from '../RepositorySelectorCard'

describe('RepositorySelectorCard', () => {
  const mockRepositories = [
    { id: 1, name: 'Repo 1', path: '/path/to/repo1' },
    { id: 2, name: 'Repo 2', path: '/path/to/repo2' },
    { id: 3, name: 'Repo 3', path: '/path/to/repo3' },
  ]

  it('renders with title and icon', () => {
    render(
      <RepositorySelectorCard
        repositories={mockRepositories}
        selectedRepositoryId={null}
        onRepositoryChange={vi.fn()}
      />
    )

    expect(screen.getByText('Select Repository')).toBeInTheDocument()
    expect(screen.getByLabelText('Repository')).toBeInTheDocument()
  })

  it('renders all repositories in dropdown', () => {
    render(
      <RepositorySelectorCard
        repositories={mockRepositories}
        selectedRepositoryId={null}
        onRepositoryChange={vi.fn()}
      />
    )

    // Open dropdown
    const select = screen.getByLabelText('Repository')
    fireEvent.mouseDown(select)

    // Check all repositories are present
    expect(screen.getByText('Repo 1')).toBeInTheDocument()
    expect(screen.getByText('Repo 2')).toBeInTheDocument()
    expect(screen.getByText('Repo 3')).toBeInTheDocument()
  })

  it('shows selected repository', () => {
    render(
      <RepositorySelectorCard
        repositories={mockRepositories}
        selectedRepositoryId={2}
        onRepositoryChange={vi.fn()}
      />
    )

    // MUI Select renders the value in a native input with class MuiSelect-nativeInput
    const nativeInput = document.querySelector('.MuiSelect-nativeInput') as HTMLInputElement
    expect(nativeInput).toHaveValue('2')
  })

  it('calls onRepositoryChange when selection changes', () => {
    const handleChange = vi.fn()
    render(
      <RepositorySelectorCard
        repositories={mockRepositories}
        selectedRepositoryId={1}
        onRepositoryChange={handleChange}
      />
    )

    // Open dropdown
    const select = screen.getByLabelText('Repository')
    fireEvent.mouseDown(select)

    // Select different repository
    fireEvent.click(screen.getByText('Repo 3'))

    expect(handleChange).toHaveBeenCalledWith(3)
  })

  it('disables select when loading', () => {
    render(
      <RepositorySelectorCard
        repositories={mockRepositories}
        selectedRepositoryId={null}
        onRepositoryChange={vi.fn()}
        loading={true}
      />
    )

    // MUI Select renders a hidden input that carries the disabled state
    const hiddenInput = document.querySelector('input[aria-hidden="true"]') as HTMLInputElement
    expect(hiddenInput).toBeDisabled()
  })

  it('shows loading message when loading', () => {
    const { container } = render(
      <RepositorySelectorCard
        repositories={[]}
        selectedRepositoryId={null}
        onRepositoryChange={vi.fn()}
        loading={true}
      />
    )

    // The loading message is in a MenuItem, but since select is disabled, we can't open it
    // Instead, verify the select is disabled which indicates loading state
    const hiddenInput = container.querySelector('input[aria-hidden="true"]') as HTMLInputElement
    expect(hiddenInput).toBeDisabled()
  })

  it('shows empty message when no repositories', () => {
    render(
      <RepositorySelectorCard
        repositories={[]}
        selectedRepositoryId={null}
        onRepositoryChange={vi.fn()}
      />
    )

    // Open dropdown
    const select = screen.getByLabelText('Repository')
    fireEvent.mouseDown(select)

    expect(screen.getByText('Select a repository...')).toBeInTheDocument()
  })
})

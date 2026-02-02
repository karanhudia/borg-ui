import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { MultiRepositorySelector } from '../MultiRepositorySelector'
import { Repository } from '@/types'

const mockRepositories: Repository[] = [
  { id: 1, name: 'Repo A', path: '/path/to/a' } as Repository,
  { id: 2, name: 'Repo B', path: '/path/to/b' } as Repository,
  { id: 3, name: 'Repo C', path: '/path/to/c' } as Repository,
]

// Mock MUI Autocomplete to control the onChange event directly
vi.mock('@mui/material', async (importOriginal) => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const actual = await importOriginal<any>()
  return {
    ...actual,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    Autocomplete: (props: any) => {
      const { onChange, value, options } = props
      return (
        <div data-testid="mock-autocomplete">
          <button
            data-testid="add-duplicate"
            onClick={() => {
              // Simulate adding the first option again (duplicate)
              onChange(null, [...value, options[0]])
            }}
          >
            Add Duplicate
          </button>
          <button
            data-testid="select-distinct"
            onClick={() => {
              // Simulate selecting Repo B (index 1) which is not in [1]
              onChange(null, [...value, options[1]])
            }}
          >
            Select Distinct
          </button>
        </div>
      )
    },
  }
})

describe('MultiRepositorySelector Uniqueness', () => {
  it('should dedup repositories when duplicate is added', () => {
    const onChange = vi.fn()
    // Start with Repo A (id: 1) selected
    render(
      <MultiRepositorySelector
        repositories={mockRepositories}
        selectedIds={[1]}
        onChange={onChange}
        allowReorder={true}
      />
    )

    // Verify initial render interactions (optional, but good sanity check)
    // The "Add Duplicate" button is from our mock
    expect(screen.getByTestId('add-duplicate')).toBeInTheDocument()

    // Trigger duplicate addition
    // The mock simulates adding options[0] (Repo A) to the existing value [Repo A]
    // Resulting value passed to local onChange: [RepoA, RepoA]
    fireEvent.click(screen.getByTestId('add-duplicate'))

    // Expectation: The component deduplicates key IDs
    // [1, 1] -> [1]
    expect(onChange).toHaveBeenCalledWith([1])
  })

  it('should allow adding distinct repositories', () => {
    const onChange = vi.fn()
    // Start with Repo A (id: 1)
    render(
      <MultiRepositorySelector
        repositories={mockRepositories}
        selectedIds={[1]}
        onChange={onChange}
        allowReorder={true}
      />
    )

    // Trigger distinct addition (Repo B)
    fireEvent.click(screen.getByTestId('select-distinct'))

    // Expectation: [1, 2]
    expect(onChange).toHaveBeenCalledWith([1, 2])
  })
})

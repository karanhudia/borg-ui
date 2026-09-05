import { describe, it, expect, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import RepositoryScopeSelect from '../RepositoryScopeSelect'
import { repositoriesAPI } from '../../../services/api'

const navigate = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>
  return { ...actual, useNavigate: () => navigate }
})
vi.mock('../../../services/api', () => ({ repositoriesAPI: { getRepositories: vi.fn() } }))

describe('RepositoryScopeSelect', () => {
  it('navigates to the chosen repository and back to all', async () => {
    ;(repositoriesAPI.getRepositories as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { repositories: [{ id: 1, name: 'nas', path: '/mnt/nas' }] },
    })
    renderWithProviders(<RepositoryScopeSelect value={null} />)
    const combo = await screen.findByRole('combobox', { name: /repository/i })
    await screen.findByText(/all repositories/i)
    fireEvent.mouseDown(combo)
    fireEvent.click(await screen.findByRole('option', { name: /nas/ }))
    expect(navigate).toHaveBeenCalledWith('/activity?repository_id=1')
  })
})

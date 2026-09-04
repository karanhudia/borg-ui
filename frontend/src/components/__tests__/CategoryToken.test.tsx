import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import CategoryToken from '../CategoryToken'

describe('CategoryToken', () => {
  it('renders the label for each known category', () => {
    const categories: Array<[string, string]> = [
      ['backup', 'Backup'],
      ['maintenance', 'Maintenance'],
      ['index', 'Index'],
      ['mirror', 'Mirror'],
      ['restore', 'Restore'],
      ['import', 'Import'],
      ['system', 'System'],
    ]
    categories.forEach(([category, label]) => {
      const { unmount } = render(<CategoryToken category={category as never} />)
      expect(screen.getByText(label)).toBeInTheDocument()
      unmount()
    })
  })
})

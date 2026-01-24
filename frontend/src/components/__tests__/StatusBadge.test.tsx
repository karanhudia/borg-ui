import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import StatusBadge from '../StatusBadge'

describe('StatusBadge', () => {
    it('renders correct label and color for "completed"', () => {
        render(<StatusBadge status="completed" />)
        const chip = screen.getByText('Completed')
        expect(chip).toBeInTheDocument()
    })

    it('renders correct label for "completed_with_warnings"', () => {
        render(<StatusBadge status="completed_with_warnings" />)
        expect(screen.getByText('Completed with Warnings')).toBeInTheDocument()
    })

    it('renders correct label for "failed"', () => {
        render(<StatusBadge status="failed" />)
        expect(screen.getByText('Failed')).toBeInTheDocument()
    })

    it('renders correct label for "running"', () => {
        render(<StatusBadge status="running" />)
        expect(screen.getByText('Running')).toBeInTheDocument()
    })

    it('renders correct label for unknown status', () => {
        render(<StatusBadge status="custom_status" />)
        expect(screen.getByText('Custom_status')).toBeInTheDocument()
    })

    it('renders with small size by default', () => {
        const { container } = render(<StatusBadge status="completed" />)
        const chip = container.firstChild as HTMLElement
        // MUI Chip small size usually has a specific class or height, checking class
        expect(chip.className).toContain('MuiChip-sizeSmall')
    })

    it('renders with medium size when specified', () => {
        const { container } = render(<StatusBadge status="completed" size="medium" />)
        const chip = container.firstChild as HTMLElement
        expect(chip.className).toContain('MuiChip-sizeMedium')
    })
})

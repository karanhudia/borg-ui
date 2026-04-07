import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useMediaQuery } from '@mui/material'
import ResponsiveDialog from '../ResponsiveDialog'

vi.mock('@mui/material', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@mui/material')>()
  return { ...actual, useMediaQuery: vi.fn() }
})

const mockUseMediaQuery = vi.mocked(useMediaQuery)

describe('ResponsiveDialog', () => {
  const onClose = vi.fn()

  beforeEach(() => {
    onClose.mockClear()
  })

  describe('desktop (md+)', () => {
    beforeEach(() => {
      mockUseMediaQuery.mockReturnValue(false)
    })

    it('renders a Dialog (role=dialog) when open', () => {
      render(
        <ResponsiveDialog open={true} onClose={onClose}>
          <div>content</div>
        </ResponsiveDialog>
      )
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('does not render when open is false', () => {
      render(
        <ResponsiveDialog open={false} onClose={onClose}>
          <div>content</div>
        </ResponsiveDialog>
      )
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('renders children', () => {
      render(
        <ResponsiveDialog open={true} onClose={onClose}>
          <div>hello world</div>
        </ResponsiveDialog>
      )
      expect(screen.getByText('hello world')).toBeInTheDocument()
    })
  })

  describe('mobile (< md)', () => {
    beforeEach(() => {
      mockUseMediaQuery.mockReturnValue(true)
    })

    it('renders a presentation role element (SwipeableDrawer) when open', () => {
      render(
        <ResponsiveDialog open={true} onClose={onClose}>
          <div>content</div>
        </ResponsiveDialog>
      )
      // SwipeableDrawer renders with role="presentation"
      expect(screen.getByRole('presentation', { hidden: true })).toBeInTheDocument()
    })

    it('renders the drag handle', () => {
      const { container } = render(
        <ResponsiveDialog open={true} onClose={onClose}>
          <div>content</div>
        </ResponsiveDialog>
      )
      // Drag handle is a box with specific dimensions — check it exists in the paper
      const handle = container.querySelector('[data-testid="drag-handle"]')
      expect(handle).toBeInTheDocument()
    })

    it('renders children', () => {
      render(
        <ResponsiveDialog open={true} onClose={onClose}>
          <div>mobile content</div>
        </ResponsiveDialog>
      )
      expect(screen.getByText('mobile content')).toBeInTheDocument()
    })

    it('does not render content when open is false', () => {
      render(
        <ResponsiveDialog open={false} onClose={onClose}>
          <div>hidden</div>
        </ResponsiveDialog>
      )
      expect(screen.queryByText('hidden')).not.toBeInTheDocument()
    })
  })
})

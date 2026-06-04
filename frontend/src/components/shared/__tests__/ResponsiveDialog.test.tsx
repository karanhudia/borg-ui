import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
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

    it('renders the drag handle when open', () => {
      render(
        <ResponsiveDialog open={true} onClose={onClose}>
          <div>content</div>
        </ResponsiveDialog>
      )
      // screen queries search the entire document including portals
      expect(screen.getByTestId('drag-handle')).toBeInTheDocument()
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

  describe('footer prop — mobile', () => {
    beforeEach(() => {
      mockUseMediaQuery.mockReturnValue(true)
    })

    it('renders footer outside the scrollable area when provided', () => {
      render(
        <ResponsiveDialog
          open={true}
          onClose={onClose}
          footer={<div data-testid="test-footer">Actions</div>}
        >
          <div>content</div>
        </ResponsiveDialog>
      )
      expect(screen.getByTestId('test-footer')).toBeInTheDocument()
      expect(screen.getByTestId('responsive-dialog-footer')).toBeInTheDocument()
    })

    it('does not render footer container when footer is not provided', () => {
      render(
        <ResponsiveDialog open={true} onClose={onClose}>
          <div>content</div>
        </ResponsiveDialog>
      )
      expect(screen.queryByTestId('responsive-dialog-footer')).not.toBeInTheDocument()
    })
  })

  describe('footer prop — desktop', () => {
    beforeEach(() => {
      mockUseMediaQuery.mockReturnValue(false)
    })

    it('renders footer as part of dialog children when provided', () => {
      render(
        <ResponsiveDialog
          open={true}
          onClose={onClose}
          footer={<div data-testid="test-footer">Actions</div>}
        >
          <div>content</div>
        </ResponsiveDialog>
      )
      expect(screen.getByTestId('test-footer')).toBeInTheDocument()
    })
  })
})

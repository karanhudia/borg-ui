import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import i18n from '../../i18n'
import * as errorReporting from '../../utils/errorReporting'
import { AppErrorBoundary } from '../AppErrorBoundary'

const Boom = () => {
  throw new TypeError('render boom')
}

describe('AppErrorBoundary', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('renders children when nothing throws', () => {
    render(
      <AppErrorBoundary>
        <p>fine</p>
      </AppErrorBoundary>
    )
    expect(screen.getByText('fine')).toBeInTheDocument()
  })

  it('shows the crash screen and reports a render error once', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const spy = vi.spyOn(errorReporting, 'reportError').mockImplementation(() => {})
    render(
      <AppErrorBoundary>
        <Boom />
      </AppErrorBoundary>
    )
    expect(screen.getByRole('button', { name: /reload/i })).toBeInTheDocument()
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(spy).toHaveBeenCalledTimes(1)
    expect(spy).toHaveBeenCalledWith(
      expect.any(TypeError),
      expect.objectContaining({ kind: 'render', component: 'Boom' })
    )
  })

  it('reloads the page from the Reload button', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(errorReporting, 'reportError').mockImplementation(() => {})
    const reload = vi.fn()
    vi.stubGlobal('location', { ...window.location, reload })
    render(
      <AppErrorBoundary>
        <Boom />
      </AppErrorBoundary>
    )
    fireEvent.click(screen.getByRole('button', { name: /reload/i }))
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('falls back to English when i18n throws', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(errorReporting, 'reportError').mockImplementation(() => {})
    vi.spyOn(i18n, 't').mockImplementation(() => {
      throw new Error('i18n broken')
    })
    render(
      <AppErrorBoundary>
        <Boom />
      </AppErrorBoundary>
    )
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument()
  })
})

import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import * as errorReporting from '../../utils/errorReporting'
import { AppErrorBoundary } from '../AppErrorBoundary'

const Boom = () => {
  throw new TypeError('render boom')
}

describe('AppErrorBoundary', () => {
  afterEach(() => vi.restoreAllMocks())

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
})

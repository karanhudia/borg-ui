import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import DiagnosticsTcpTargetFields from '../DiagnosticsTcpTargetFields'

const labels = {
  summary: 'Advanced: test another service',
  description:
    'Checks whether this machine can reach a separate service. Leave blank for normal diagnostics.',
  host: 'Service host',
  hostPlaceholder: 'postgres.internal',
  hostHelper: 'Optional service to test from this machine',
  port: 'Service port',
  portPlaceholder: '5432',
  timeout: 'Timeout',
  timeoutHelper: 'Seconds',
}

function renderTargetFields() {
  render(
    <DiagnosticsTcpTargetFields
      targetHost=""
      targetPort=""
      targetTimeout="3"
      onTargetHostChange={vi.fn()}
      onTargetPortChange={vi.fn()}
      onTargetTimeoutChange={vi.fn()}
      hasTarget={false}
      portInvalid={false}
      timeoutInvalid={false}
      timeoutInputProps={{ min: 0.5, max: 15, step: 0.5 }}
      labels={labels}
    />
  )
}

describe('DiagnosticsTcpTargetFields', () => {
  it('keeps details mounted after collapsing so the accordion can animate smoothly', async () => {
    const user = userEvent.setup()
    renderTargetFields()

    expect(screen.queryByLabelText(/service host/i)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /advanced: test another service/i }))
    expect(screen.getByLabelText(/service host/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/service host/i)).toHaveAttribute(
      'placeholder',
      'postgres.internal'
    )
    expect(screen.getByLabelText(/service port/i)).toHaveAttribute('placeholder', '5432')

    await user.click(screen.getByRole('button', { name: /advanced: test another service/i }))
    expect(screen.getByLabelText(/service host/i)).toBeInTheDocument()
  })
})

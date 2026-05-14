import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import BackupPlanScheduleBadge from '../BackupPlanScheduleBadge'

describe('BackupPlanScheduleBadge', () => {
  it('shows the next scheduled run as a compact chip', () => {
    render(
      <BackupPlanScheduleBadge
        scheduleEnabled
        nextRun="2026-05-13T21:00:00Z"
        cronExpression="0 21 * * *"
        timezone="UTC"
      />
    )

    expect(screen.getByText(/next/i)).toBeInTheDocument()
  })

  it('does not render for manual-only plans', () => {
    const { container } = render(
      <BackupPlanScheduleBadge scheduleEnabled={false} cronExpression="0 21 * * *" timezone="UTC" />
    )

    expect(container).toBeEmptyDOMElement()
  })
})

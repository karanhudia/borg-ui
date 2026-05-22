import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '../../test/test-utils'
import { waitFor } from '@testing-library/react'
import { TerminalLogViewer } from '../TerminalLogViewer'

describe('TerminalLogViewer', () => {
  it('renders Unicode escape sequences in JSON strings as readable characters', async () => {
    const escapedGreekPath = 'local/2026/\\u0391\\u03af\\u03b3\\u03b9\\u03bd\\u03b1.MP4'
    const decodedGreekPath = 'local/2026/\u0391\u03af\u03b3\u03b9\u03bd\u03b1.MP4'
    const content = `{"type":"archive_progress","path":"${escapedGreekPath}"}`
    const onFetchLogs = vi.fn().mockResolvedValue({
      lines: [
        {
          line_number: 1,
          content,
        },
      ],
      total_lines: 1,
      has_more: false,
    })

    render(
      <TerminalLogViewer
        jobId="42"
        status="completed"
        showHeader={false}
        onFetchLogs={onFetchLogs}
      />
    )

    await waitFor(() => {
      expect(screen.getByText(`"${decodedGreekPath}"`)).toBeInTheDocument()
    })
    expect(screen.queryByText(`"${escapedGreekPath}"`)).not.toBeInTheDocument()
  })
})

import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '../../test/test-utils'
import { waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

  it('uses the job type in downloaded log filenames', async () => {
    const user = userEvent.setup()
    const originalCreateObjectURL = URL.createObjectURL
    const originalRevokeObjectURL = URL.revokeObjectURL
    const createObjectURL = vi.fn(() => 'blob:logs')
    const revokeObjectURL = vi.fn()
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const onFetchLogs = vi.fn().mockResolvedValue({
      lines: [
        {
          line_number: 1,
          content: 'downloadable log',
        },
      ],
      total_lines: 1,
      has_more: false,
    })

    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: createObjectURL,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: revokeObjectURL,
    })

    try {
      render(
        <TerminalLogViewer
          jobId="42"
          status="completed"
          jobType="managed agent"
          onFetchLogs={onFetchLogs}
        />
      )

      expect(await screen.findByText('downloadable log')).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: /download/i }))

      expect(createObjectURL).toHaveBeenCalled()
      expect(clickSpy).toHaveBeenCalled()
      expect((clickSpy.mock.contexts[0] as HTMLAnchorElement).download).toBe(
        'managed_agent_42_logs.txt'
      )
      expect(revokeObjectURL).toHaveBeenCalledWith('blob:logs')
    } finally {
      Object.defineProperty(URL, 'createObjectURL', {
        configurable: true,
        value: originalCreateObjectURL,
      })
      Object.defineProperty(URL, 'revokeObjectURL', {
        configurable: true,
        value: originalRevokeObjectURL,
      })
      clickSpy.mockRestore()
    }
  })
})

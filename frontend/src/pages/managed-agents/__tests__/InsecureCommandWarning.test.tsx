import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import AgentInstallCommand from '../AgentInstallCommand'
import InsecureCommandWarning from '../InsecureCommandWarning'
import { isInsecureCommandUrl } from '../agentServerUrl'

describe('isInsecureCommandUrl', () => {
  it.each([
    ['http://borg-ui.example.com', true],
    ['http://192.168.1.82:8083', true],
    ['https://borg-ui.example.com', false],
    ['http://localhost:8083', false],
    ['http://127.0.0.1:8083', false],
    ['http://[::1]:8083', false],
    ['https://[::1]:8083', false],
    ['http://[2001:db8::1]:8083', true],
    ['not a url', false],
  ])('%s -> %s', (url, expected) => {
    expect(isInsecureCommandUrl(url)).toBe(expected)
  })
})

describe('InsecureCommandWarning', () => {
  it('warns when the script would be fetched over plain HTTP', () => {
    render(<InsecureCommandWarning serverUrl="http://192.168.1.82:8083" />)
    expect(screen.getByText(/runs it as root/i)).toBeInTheDocument()
  })

  it('stays out of the way on HTTPS', () => {
    const { container } = render(<InsecureCommandWarning serverUrl="https://borg-ui.example.com" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('stays out of the way on loopback, where there is no network path', () => {
    const { container } = render(<InsecureCommandWarning serverUrl="http://localhost:8083" />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('the surfaces that render a curl-to-sudo command', () => {
  it('warns on the enrollment command, which is the one every operator runs', () => {
    render(
      <AgentInstallCommand
        serverUrl="http://192.168.1.82:8083"
        token="enrollment-token"
        agentName="db-01"
        onCopy={() => {}}
      />
    )
    expect(screen.getByText(/runs it as root/i)).toBeInTheDocument()
  })

  it('leaves the enrollment command alone on HTTPS', () => {
    render(
      <AgentInstallCommand
        serverUrl="https://borg-ui.example.com"
        token="enrollment-token"
        agentName="db-01"
        onCopy={() => {}}
      />
    )
    expect(screen.queryByText(/runs it as root/i)).not.toBeInTheDocument()
  })
})

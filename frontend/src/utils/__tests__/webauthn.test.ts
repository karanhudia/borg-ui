import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createPasskeyCredential,
  getConditionalPasskeyAssertion,
  getPasskeyAssertion,
  isConditionalMediationAvailable,
  isWebAuthnSupported,
} from '../webauthn'

const registrationOptions = { challenge: 'AQ', user: { id: 'Ag' } }
const authenticationOptions = { challenge: 'AQ' }
const unsupportedMessage = 'Passkeys require a secure context and a browser with WebAuthn support'

function credential() {
  return {
    id: 'passkey',
    type: 'public-key',
    rawId: new Uint8Array([1]).buffer,
    response: { clientDataJSON: new Uint8Array([2]).buffer },
    getClientExtensionResults: () => ({}),
    authenticatorAttachment: 'platform',
  }
}

describe('WebAuthn capability', () => {
  const create = vi.fn()
  const get = vi.fn()

  beforeEach(() => {
    vi.stubGlobal('isSecureContext', true)
    vi.stubGlobal('PublicKeyCredential', class {})
    vi.spyOn(navigator, 'credentials', 'get').mockReturnValue({
      create,
      get,
    } as unknown as CredentialsContainer)
    create.mockReset().mockResolvedValue(credential())
    get.mockReset().mockResolvedValue(credential())
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('supports secure contexts without imposing an HTTPS-only URL check', () => {
    expect(window.location.protocol).toBe('http:')
    expect(isWebAuthnSupported()).toBe(true)
  })

  it.each([
    ['insecure context', () => vi.stubGlobal('isSecureContext', false)],
    ['missing constructor', () => vi.stubGlobal('PublicKeyCredential', undefined)],
    [
      'missing credentials',
      () =>
        vi
          .spyOn(navigator, 'credentials', 'get')
          .mockReturnValue(undefined as unknown as CredentialsContainer),
    ],
    [
      'missing creation API',
      () => {
        create.mockReset()
        vi.spyOn(navigator, 'credentials', 'get').mockReturnValue({
          get,
        } as unknown as CredentialsContainer)
      },
    ],
    [
      'missing assertion API',
      () =>
        vi
          .spyOn(navigator, 'credentials', 'get')
          .mockReturnValue({ create } as unknown as CredentialsContainer),
    ],
  ])(
    'rejects an unsupported %s before parsing options or invoking credentials',
    async (_name, disable) => {
      disable()

      expect(isWebAuthnSupported()).toBe(false)
      await expect(createPasskeyCredential({})).rejects.toThrow(unsupportedMessage)
      await expect(getPasskeyAssertion({})).rejects.toThrow(unsupportedMessage)
      await expect(getConditionalPasskeyAssertion({})).rejects.toThrow(unsupportedMessage)
      await expect(isConditionalMediationAvailable()).resolves.toBe(false)
      expect(create).not.toHaveBeenCalled()
      expect(get).not.toHaveBeenCalled()
    }
  )

  it('creates and serializes a credential in a supported environment', async () => {
    await expect(createPasskeyCredential(registrationOptions)).resolves.toMatchObject({
      id: 'passkey',
      rawId: 'AQ',
      response: { clientDataJSON: 'Ag' },
    })
    expect(create).toHaveBeenCalledWith({
      publicKey: expect.objectContaining({
        challenge: new Uint8Array([1]).buffer,
        user: { id: new Uint8Array([2]).buffer },
      }),
    })
  })

  it('authenticates with explicit and conditional assertions', async () => {
    const controller = new AbortController()
    await expect(getPasskeyAssertion(authenticationOptions)).resolves.toMatchObject({
      id: 'passkey',
    })
    await expect(
      getConditionalPasskeyAssertion(authenticationOptions, controller.signal)
    ).resolves.toMatchObject({ id: 'passkey' })
    expect(get).toHaveBeenNthCalledWith(1, {
      publicKey: expect.objectContaining({ challenge: new Uint8Array([1]).buffer }),
    })
    expect(get).toHaveBeenNthCalledWith(2, {
      publicKey: expect.objectContaining({ challenge: new Uint8Array([1]).buffer }),
      mediation: 'conditional',
      signal: controller.signal,
    })
  })

  it('retains cancellation errors from supported credential operations', async () => {
    create.mockResolvedValue(null)
    get.mockResolvedValue(null)
    await expect(createPasskeyCredential(registrationOptions)).rejects.toThrow(
      'Passkey creation was cancelled'
    )
    await expect(getPasskeyAssertion(authenticationOptions)).rejects.toThrow(
      'Passkey authentication was cancelled'
    )
    await expect(getConditionalPasskeyAssertion(authenticationOptions)).rejects.toThrow(
      'Passkey authentication was cancelled'
    )
  })

  it('detects optional conditional mediation only in a supported environment', async () => {
    await expect(isConditionalMediationAvailable()).resolves.toBe(false)
    const conditionalCheck = vi.fn().mockResolvedValue(true)
    vi.stubGlobal(
      'PublicKeyCredential',
      class {
        static isConditionalMediationAvailable = conditionalCheck
      }
    )
    await expect(isConditionalMediationAvailable()).resolves.toBe(true)
    vi.stubGlobal('isSecureContext', false)
    await expect(isConditionalMediationAvailable()).resolves.toBe(false)
    expect(conditionalCheck).toHaveBeenCalledTimes(1)
  })
})
